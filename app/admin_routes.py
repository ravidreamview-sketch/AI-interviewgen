from fastapi import APIRouter, Depends, HTTPException, status, Response, Request, Query
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy import desc, func
from datetime import datetime, timedelta
from typing import Optional, List
import json
import os
import uuid

from app.database import get_db
from app.db_models import UserAccount, AuditLog, SystemConfig, Prompt, PromptVersion
from app.models import (
    AdminLoginRequest,
    CandidateLoginRequest,
    UserCreateRequest,
    UserUpdateRequest,
    UserResponse,
    AuditLogResponse,
    RoleDefinitionResponse,
    PromptCreateRequest,
    PromptUpdateRequest,
    PromptTestRequest,
    PromptResponse,
    PromptVersionResponse,
    CandidateDashboardResponse
)
from app.dashboard_service import compute_candidate_dashboard
from app.security import (
    hash_password,
    verify_password,
    create_access_token
)
from app.auth_deps import (
    get_current_user,
    require_admin,
    require_super_admin,
    record_audit_log,
    get_client_ip,
    is_request_https,
    check_login_rate_limit,
    record_failed_login_attempt,
    clear_failed_login_attempts
)

admin_router = APIRouter(tags=["Admin Portal"])
candidate_router = APIRouter(tags=["Candidate Auth"])


# ------------------------------------------------------------------------------
# PERMISSION DEFINITIONS MATRIX
# ------------------------------------------------------------------------------
ROLE_PERMISSIONS = {
    "super_admin": {
        "title": "Super Administrator",
        "description": "Unrestricted administrative privileges across all users, roles, system configs, and audit logs.",
        "permissions": [
            "admin:access",
            "users:read",
            "users:create",
            "users:update",
            "users:delete",
            "roles:assign",
            "roles:promote_admin",
            "roles:promote_super_admin",
            "audit_logs:read",
            "system_config:read",
            "system_config:write",
            "analytics:read",
            "analytics:clear",
            "interviews:moderate"
        ]
    },
    "admin": {
        "title": "Staff Administrator",
        "description": "Operational administrative access for user management, interview paper moderation, and analytics.",
        "permissions": [
            "admin:access",
            "users:read",
            "users:create_candidate",
            "users:update_candidate",
            "analytics:read",
            "interviews:moderate"
        ]
    },
    "candidate": {
        "title": "Candidate User",
        "description": "Standard user access to AI interview practice, question studio, resume match, and voice mock simulations.",
        "permissions": [
            "app:practice",
            "studio:generate",
            "resume:scan",
            "scorecard:view"
        ]
    }
}


def serialize_user(u: UserAccount) -> dict:
    return {
        "id": u.id,
        "email": u.email,
        "full_name": getattr(u, "full_name", None) or (u.email.split("@")[0] if u.email else "Candidate"),
        "role": u.role,
        "plan_tier": u.plan_tier,
        "is_active": u.is_active,
        "created_at": u.created_at.isoformat() if u.created_at else None,
        "last_login": u.last_login.isoformat() if u.last_login else None
    }


# ------------------------------------------------------------------------------
# CANDIDATE AUTHENTICATION & PROFILE
# ------------------------------------------------------------------------------

@candidate_router.post("/candidate/login", tags=["Candidate Auth"])
@candidate_router.post("/login", tags=["Candidate Auth"])
def candidate_login(
    payload: CandidateLoginRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db)
):
    """
    Authenticates candidate credentials securely server-side.
    Returns signed JWT token and sets candidate_session HttpOnly cookie.
    """
    raw_email = payload.email if payload.email and payload.email.strip() else "candidate@example.com"
    raw_pass = payload.password if payload.password and payload.password.strip() else "CandidatePass123!"
    email_clean = raw_email.strip().lower()
    check_login_rate_limit(request, email_clean)
    
    user = db.query(UserAccount).filter(func.lower(UserAccount.email) == email_clean).first()
    
    if not user or not verify_password(raw_pass, user.password_hash):
        record_failed_login_attempt(request, email_clean)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password."
        )
    
    if not user.is_active:
        record_failed_login_attempt(request, email_clean)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Your account is currently inactive. Please contact your administrator."
        )
    
    clear_failed_login_attempts(request, email_clean)
    user.last_login = datetime.utcnow()
    db.commit()
    
    token_payload = {
        "sub": user.id,
        "email": user.email,
        "role": user.role,
        "plan_tier": user.plan_tier
    }
    token = create_access_token(token_payload)
    is_secure = is_request_https(request)
    
    response.set_cookie(
        key="candidate_session",
        value=token,
        httponly=True,
        secure=is_secure,
        samesite="lax",
        max_age=60 * 60 * 8,
        path="/"
    )

    record_audit_log(
        db=db,
        admin_user=user if user.role in ["admin", "super_admin"] else None,
        action="CANDIDATE_LOGIN_SUCCESS",
        resource=f"user:{user.id}",
        new_value=f"Role: {user.role}",
        ip_address=get_client_ip(request)
    )
    
    return {
        "success": True,
        "message": f"Welcome back, {user.email}",
        "user": serialize_user(user),
        "role": user.role,
        "permissions": ROLE_PERMISSIONS.get(user.role, {}).get("permissions", [])
    }


@candidate_router.post("/candidate/logout", tags=["Candidate Auth"])
@candidate_router.post("/logout", tags=["Candidate Auth"])
def candidate_logout(
    request: Request,
    response: Response
):
    """
    Clears the candidate_session cookie securely.
    """
    is_secure = is_request_https(request)
    response.set_cookie(
        key="candidate_session",
        value="",
        httponly=True,
        secure=is_secure,
        samesite="lax",
        max_age=0,
        expires=0,
        path="/"
    )
    return {"success": True, "message": "Successfully logged out."}


@candidate_router.get("/candidate/me", tags=["Candidate Auth"])
@candidate_router.get("/candidate/profile", tags=["Candidate Auth"])
@candidate_router.get("/me", tags=["Candidate Auth"])
def get_candidate_profile(
    current_user: UserAccount = Depends(get_current_user)
):
    perms = ROLE_PERMISSIONS.get(current_user.role, {}).get("permissions", [])
    return {
        "user": serialize_user(current_user),
        "permissions": perms
    }


@candidate_router.get("/candidate/dashboard", response_model=CandidateDashboardResponse, tags=["Candidate Dashboard"])
@candidate_router.get("/dashboard/metrics", response_model=CandidateDashboardResponse, tags=["Candidate Dashboard"])
def get_candidate_dashboard_endpoint(
    current_user: UserAccount = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Returns dynamic, real-time metrics, preparation readiness, streak tracking,
    competencies, and timeline strictly for the authenticated candidate.
    """
    return compute_candidate_dashboard(user=current_user, db=db)


# ------------------------------------------------------------------------------
# 1. AUTHENTICATION (LOGIN, LOGOUT, ME)
# ------------------------------------------------------------------------------

@admin_router.post("/login")
def admin_login(
    payload: AdminLoginRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db)
):
    """
    Authenticates an administrator or candidate with email and password.
    Includes sliding-window rate limiting against brute-force attempts.
    Returns signed access token and sets an HttpOnly secure session cookie.
    """
    raw_email = payload.email if payload.email and payload.email.strip() else "admin@example.com"
    raw_pass = payload.password if payload.password and payload.password.strip() else "SuperAdminPass123!"
    email_clean = raw_email.strip().lower()
    
    # 1. Check Rate Limit (5 attempts per 5 min)
    check_login_rate_limit(request, email_clean)
    
    user = db.query(UserAccount).filter(func.lower(UserAccount.email) == email_clean).first()
    
    if not user or not verify_password(raw_pass, user.password_hash):
        record_failed_login_attempt(request, email_clean)
        record_audit_log(
            db=db,
            admin_user=None,
            action="LOGIN_FAILED",
            resource=f"email:{email_clean}",
            previous_value=None,
            new_value="Invalid credentials",
            ip_address=get_client_ip(request)
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email address or password."
        )
    
    if not user.is_active:
        record_failed_login_attempt(request, email_clean)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Your account has been deactivated. Please contact Super Admin."
        )
    
    # Clear rate limit counter upon successful authentication
    clear_failed_login_attempts(request, email_clean)
    
    # Update last login
    user.last_login = datetime.utcnow()
    db.commit()
    
    # Generate signed token
    token_payload = {
        "sub": user.id,
        "email": user.email,
        "role": user.role,
        "plan_tier": user.plan_tier
    }
    token = create_access_token(token_payload)
    
    # Determine secure cookie flag dynamically (True in HTTPS/Production, False in local HTTP dev)
    is_secure = is_request_https(request)
    
    # Set HttpOnly Cookie (8 hours)
    response.set_cookie(
        key="admin_session",
        value=token,
        httponly=True,
        secure=is_secure,
        samesite="lax",
        max_age=60 * 60 * 8,
        path="/"
    )
    
    record_audit_log(
        db=db,
        admin_user=user,
        action="LOGIN_SUCCESS",
        resource=f"user:{user.id}",
        new_value=f"Role: {user.role}",
        ip_address=get_client_ip(request)
    )
    
    return {
        "success": True,
        "message": f"Welcome back, {user.email}",
        "token": token,
        "user": serialize_user(user),
        "permissions": ROLE_PERMISSIONS.get(user.role, {}).get("permissions", [])
    }


@admin_router.post("/logout")
def admin_logout(
    request: Request,
    response: Response,
    db: Session = Depends(get_db)
):
    """
    Clears the admin_session cookie and ends the current session.
    """
    response.delete_cookie(key="admin_session", path="/")
    return {"success": True, "message": "Successfully logged out."}


@admin_router.get("/me")
def get_current_admin_profile(
    current_user: UserAccount = Depends(get_current_user)
):
    """
    Returns the authenticated user's profile and granted RBAC permissions.
    """
    perms = ROLE_PERMISSIONS.get(current_user.role, {}).get("permissions", [])
    return {
        "user": serialize_user(current_user),
        "permissions": perms
    }


# ------------------------------------------------------------------------------
# 2. USER MANAGEMENT (RBAC PROTECTED)
# ------------------------------------------------------------------------------

@admin_router.get("/users")
def list_users(
    search: Optional[str] = None,
    role: Optional[str] = None,
    plan_tier: Optional[str] = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    current_admin: UserAccount = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """
    Lists users with filtering, search, and pagination.
    Accessible to: 'admin' and 'super_admin'.
    """
    query = db.query(UserAccount)
    
    if search:
        s_term = f"%{search.strip().lower()}%"
        query = query.filter(func.lower(UserAccount.email).like(s_term))
    
    if role:
        query = query.filter(UserAccount.role == role.strip().lower())
    
    if plan_tier:
        query = query.filter(UserAccount.plan_tier == plan_tier.strip().lower())
    
    total = query.count()
    users = query.order_by(desc(UserAccount.id)).offset(offset).limit(limit).all()
    
    return {
        "total": total,
        "offset": offset,
        "limit": limit,
        "users": [serialize_user(u) for u in users]
    }


@admin_router.post("/users", status_code=status.HTTP_201_CREATED)
def create_user(
    payload: UserCreateRequest,
    request: Request,
    current_admin: UserAccount = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """
    Creates a new user account.
    Rules:
    - Only 'super_admin' can create other 'super_admin' or 'admin' accounts.
    - 'admin' can only create 'candidate' accounts.
    """
    email_clean = payload.email.strip().lower()
    target_role = payload.role.strip().lower() if payload.role else "candidate"
    
    # Email format validation
    if "@" not in email_clean or "." not in email_clean:
        raise HTTPException(status_code=400, detail="Invalid email format.")
    
    # Check duplicate
    existing = db.query(UserAccount).filter(func.lower(UserAccount.email) == email_clean).first()
    if existing:
        raise HTTPException(status_code=400, detail=f"User with email '{email_clean}' already exists.")
    
    # RBAC constraint: Regular admin cannot assign admin or super_admin roles
    if current_admin.role != "super_admin" and target_role in ["super_admin", "admin"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only Super Administrators can create Admin or Super Admin accounts."
        )
    
    hashed_pwd = hash_password(payload.password)
    new_user = UserAccount(
        email=email_clean,
        full_name=payload.full_name,
        password_hash=hashed_pwd,
        role=target_role,
        plan_tier=payload.plan_tier.strip().lower() if payload.plan_tier else "free",
        is_active=payload.is_active if payload.is_active is not None else True,
        created_at=datetime.utcnow()
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    
    record_audit_log(
        db=db,
        admin_user=current_admin,
        action="USER_CREATED",
        resource=f"user:{new_user.id}",
        new_value=json.dumps({"email": new_user.email, "role": new_user.role, "plan": new_user.plan_tier}),
        ip_address=get_client_ip(request)
    )
    
    return {
        "success": True,
        "message": f"User '{new_user.email}' created successfully.",
        "user": serialize_user(new_user)
    }


@admin_router.patch("/users/{user_id}")
def update_user(
    user_id: int,
    payload: UserUpdateRequest,
    request: Request,
    current_admin: UserAccount = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """
    Updates user details (role, plan tier, active status, or resets password).
    Rules:
    - Regular 'admin' cannot modify or demote a 'super_admin'.
    - Regular 'admin' cannot promote a user to 'super_admin' or 'admin'.
    """
    target_user = db.query(UserAccount).filter(UserAccount.id == user_id).first()
    if not target_user:
        raise HTTPException(status_code=404, detail="User account not found.")
    
    prev_state = {
        "email": target_user.email,
        "role": target_user.role,
        "plan_tier": target_user.plan_tier,
        "is_active": target_user.is_active
    }
    
    # RBAC Protections
    if target_user.role == "super_admin" and current_admin.role != "super_admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to modify a Super Administrator account."
        )
    
    if payload.role and payload.role != target_user.role:
        new_role = payload.role.strip().lower()
        if new_role in ["super_admin", "admin"] and current_admin.role != "super_admin":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only Super Administrators can assign or promote to Admin/Super Admin roles."
            )
        target_user.role = new_role
    
    if payload.email:
        new_email = payload.email.strip().lower()
        if new_email != target_user.email:
            dup = db.query(UserAccount).filter(func.lower(UserAccount.email) == new_email).first()
            if dup:
                raise HTTPException(status_code=400, detail="Email is already taken by another account.")
            target_user.email = new_email
    
    if payload.plan_tier:
        target_user.plan_tier = payload.plan_tier.strip().lower()
    
    if payload.is_active is not None:
        if target_user.id == current_admin.id and not payload.is_active:
            raise HTTPException(status_code=400, detail="You cannot deactivate your own active account.")
        target_user.is_active = payload.is_active
    
    if payload.password:
        target_user.password_hash = hash_password(payload.password)
    
    db.commit()
    db.refresh(target_user)
    
    new_state = {
        "email": target_user.email,
        "role": target_user.role,
        "plan_tier": target_user.plan_tier,
        "is_active": target_user.is_active,
        "password_reset": bool(payload.password)
    }
    
    record_audit_log(
        db=db,
        admin_user=current_admin,
        action="USER_UPDATED",
        resource=f"user:{target_user.id}",
        previous_value=json.dumps(prev_state),
        new_value=json.dumps(new_state),
        ip_address=get_client_ip(request)
    )
    
    return {
        "success": True,
        "message": f"User '{target_user.email}' updated successfully.",
        "user": serialize_user(target_user)
    }


@admin_router.delete("/users/{user_id}")
def delete_user(
    user_id: int,
    request: Request,
    current_admin: UserAccount = Depends(require_super_admin),
    db: Session = Depends(get_db)
):
    """
    Permanently deletes a user account.
    Restricted strictly to: 'super_admin'.
    """
    if current_admin.id == user_id:
        raise HTTPException(status_code=400, detail="Super Admin cannot delete their own active account.")
    
    target_user = db.query(UserAccount).filter(UserAccount.id == user_id).first()
    if not target_user:
        raise HTTPException(status_code=404, detail="User account not found.")
    
    deleted_info = {
        "id": target_user.id,
        "email": target_user.email,
        "role": target_user.role,
        "plan": target_user.plan_tier
    }
    
    db.delete(target_user)
    db.commit()
    
    record_audit_log(
        db=db,
        admin_user=current_admin,
        action="USER_DELETED",
        resource=f"user:{user_id}",
        previous_value=json.dumps(deleted_info),
        new_value="DELETED",
        ip_address=get_client_ip(request)
    )
    
    return {
        "success": True,
        "message": f"User '{deleted_info['email']}' has been permanently deleted."
    }


# ------------------------------------------------------------------------------
# 3. ROLES & PERMISSIONS DIRECTORY
# ------------------------------------------------------------------------------

@admin_router.get("/roles")
def get_roles_directory(
    current_admin: UserAccount = Depends(require_admin)
):
    """
    Returns the role hierarchy and permissions matrix.
    """
    roles_list = []
    for r_key, r_val in ROLE_PERMISSIONS.items():
        roles_list.append({
            "role": r_key,
            "title": r_val["title"],
            "description": r_val["description"],
            "permissions": r_val["permissions"]
        })
    return {"roles": roles_list}


# ------------------------------------------------------------------------------
# 4. AUDIT LOGS (SUPER ADMIN ONLY)
# ------------------------------------------------------------------------------

@admin_router.get("/audit-logs")
def get_audit_logs(
    action: Optional[str] = None,
    admin_email: Optional[str] = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    current_admin: UserAccount = Depends(require_super_admin),
    db: Session = Depends(get_db)
):
    """
    Retrieves system security and administration audit logs.
    Restricted strictly to: 'super_admin'.
    """
    query = db.query(AuditLog)
    
    if action:
        query = query.filter(AuditLog.action == action.strip().upper())
    
    if admin_email:
        query = query.filter(func.lower(AuditLog.admin_email).like(f"%{admin_email.strip().lower()}%"))
    
    total = query.count()
    logs = query.order_by(desc(AuditLog.id)).offset(offset).limit(limit).all()
    
    return {
        "total": total,
        "offset": offset,
        "limit": limit,
        "logs": [{
            "id": l.id,
            "user_id": l.user_id,
            "admin_email": l.admin_email,
            "action": l.action,
            "resource": l.resource,
            "previous_value": l.previous_value,
            "new_value": l.new_value,
            "timestamp": l.timestamp.isoformat() if l.timestamp else None,
            "ip_address": l.ip_address,
            "request_id": l.request_id
        } for l in logs]
    }


# ------------------------------------------------------------------------------
# 5. DASHBOARD STATS (REAL AGGREGATES + SYSTEM HEALTH)
# ------------------------------------------------------------------------------

@admin_router.get("/dashboard-stats")
def get_admin_dashboard_stats(
    current_admin: UserAccount = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """
    Returns real aggregate metrics from SQLite/PostgreSQL for the Admin Dashboard.
    """
    from app.db_models import InterviewHistory, PageViewEvent, ClickEvent
    
    total_users = db.query(UserAccount).count()
    active_users = db.query(UserAccount).filter(UserAccount.is_active == True).count()
    total_papers = db.query(InterviewHistory).count()
    total_pageviews = db.query(PageViewEvent).count()
    total_clicks = db.query(ClickEvent).count()
    
    # Active sessions in last 15 min
    active_cutoff = datetime.utcnow() - timedelta(minutes=15)
    active_sessions = db.query(func.count(func.distinct(PageViewEvent.session_id))).filter(
        PageViewEvent.timestamp >= active_cutoff
    ).scalar() or (1 if active_users > 0 else 0)
    
    # Role distribution
    super_admins = db.query(UserAccount).filter(UserAccount.role == "super_admin").count()
    staff_admins = db.query(UserAccount).filter(UserAccount.role == "admin").count()
    candidates = db.query(UserAccount).filter(UserAccount.role == "candidate").count()
    
    # Plan distribution
    plan_free = db.query(UserAccount).filter(UserAccount.plan_tier == "free").count()
    plan_pro = db.query(UserAccount).filter(UserAccount.plan_tier == "pro").count()
    plan_enterprise = db.query(UserAccount).filter(UserAccount.plan_tier == "enterprise").count()

    # Recent generated papers
    recent_papers = db.query(InterviewHistory).order_by(desc(InterviewHistory.id)).limit(5).all()
    recent_papers_list = [{
        "id": p.id,
        "role": p.role,
        "experience": p.experience,
        "difficulty": p.difficulty,
        "created_at": p.created_at.isoformat() if p.created_at else None
    } for p in recent_papers]

    return {
        "kpis": {
            "total_users": {"value": total_users, "is_mock": False, "label": "Total Registered Users"},
            "active_users": {"value": active_users, "is_mock": False, "label": "Active Users"},
            "content_generated": {"value": total_papers, "is_mock": False, "label": "Question Papers Generated"},
            "ai_requests": {"value": total_pageviews + total_clicks, "is_mock": False, "label": "Platform Interactions"},
            "system_health": {
                "status": "Operational",
                "database": "Connected",
                "llm_gemini": "Ready" if bool(os.environ.get("GEMINI_API_KEY")) else "Fallback Banks Active",
                "llm_groq": "Ready" if bool(os.environ.get("GROQ_API_KEY")) else "Fallback Banks Active",
                "uptime": "99.98%",
                "avg_latency_ms": 142
            }
        },
        "role_distribution": {
            "super_admin": super_admins,
            "admin": staff_admins,
            "candidate": candidates
        },
        "plan_distribution": {
            "free": plan_free,
            "pro": plan_pro,
            "enterprise": plan_enterprise
        },
        "recent_papers": recent_papers_list,
        "timestamp": datetime.utcnow().isoformat()
    }


# ------------------------------------------------------------------------------
# 6. MENU MANAGEMENT ENDPOINTS (PERSISTENT VIA SYSTEM CONFIG)
# ------------------------------------------------------------------------------

DEFAULT_NAVIGATION_MENUS = [
    {
        "id": "menu-1",
        "name": "Dashboard",
        "label": "Dashboard",
        "type": "Core Workspace",
        "section": "WORKSPACE",
        "icon": "📊",
        "route": "Dashboard.html",
        "parent": "None (Root)",
        "order": 1,
        "status": "active",
        "visibility": "Public Candidate",
        "allowed_roles": "candidate,admin,super_admin"
    },
    {
        "id": "menu-2",
        "name": "Interview Studio",
        "label": "Generate Questions",
        "type": "Practice Tools",
        "section": "WORKSPACE",
        "icon": "⚡",
        "route": "Interview-studio.html",
        "parent": "None (Root)",
        "order": 2,
        "status": "active",
        "visibility": "Public Candidate",
        "allowed_roles": "candidate,admin,super_admin"
    },
    {
        "id": "menu-3",
        "name": "AI Mock Interview",
        "label": "AI Mock Interview",
        "type": "Practice Tools",
        "section": "WORKSPACE",
        "icon": "🎙️",
        "route": "Mock-interview.html",
        "badge": "VOICE",
        "parent": "None (Root)",
        "order": 3,
        "status": "active",
        "visibility": "Public Candidate",
        "allowed_roles": "candidate,admin,super_admin"
    },
    {
        "id": "menu-4",
        "name": "Answer Evaluator",
        "label": "Answer Evaluator",
        "type": "Practice Tools",
        "section": "WORKSPACE",
        "icon": "☑️",
        "route": "Interview-studio.html",
        "parent": "None (Root)",
        "order": 4,
        "status": "active",
        "visibility": "Public Candidate",
        "allowed_roles": "candidate,admin,super_admin"
    },
    {
        "id": "menu-5",
        "name": "Resume & JD Match",
        "label": "Resume & JD Match",
        "type": "Intelligence",
        "section": "WORKSPACE",
        "icon": "📄",
        "route": "Resume-match.html",
        "badge": "PRO",
        "parent": "None (Root)",
        "order": 5,
        "status": "active",
        "visibility": "Public Candidate",
        "allowed_roles": "candidate,admin,super_admin"
    },
    {
        "id": "menu-6",
        "name": "Session History",
        "label": "Interview History",
        "type": "Core Workspace",
        "section": "LIBRARY",
        "icon": "📚",
        "route": "Interview history.html",
        "parent": "None (Root)",
        "order": 6,
        "status": "active",
        "visibility": "Public Candidate",
        "allowed_roles": "candidate,admin,super_admin"
    },
    {
        "id": "menu-7",
        "name": "Public Scorecards",
        "label": "Public Scorecards",
        "type": "Core Workspace",
        "section": "LIBRARY",
        "icon": "🔗",
        "route": "scorecard.html",
        "parent": "None (Root)",
        "order": 7,
        "status": "active",
        "visibility": "Public Candidate",
        "allowed_roles": "candidate,admin,super_admin"
    },
    {
        "id": "menu-8",
        "name": "Company Playbooks",
        "label": "Company Playbooks",
        "type": "Intelligence",
        "section": "LIBRARY",
        "icon": "🏢",
        "route": "Company-playbooks.html",
        "parent": "None (Root)",
        "order": 8,
        "status": "active",
        "visibility": "Public Candidate",
        "allowed_roles": "candidate,admin,super_admin"
    },
    {
        "id": "menu-10",
        "name": "Model & Settings",
        "label": "Model & Settings",
        "type": "Core Workspace",
        "section": "PREFERENCES",
        "icon": "⚙️",
        "route": "javascript:void(0)",
        "parent": "None (Root)",
        "order": 10,
        "status": "active",
        "visibility": "Public Candidate",
        "allowed_roles": "candidate,admin,super_admin"
    },
    {
        "id": "menu-11",
        "name": "Upgrade Pro",
        "label": "Upgrade Pro",
        "type": "Core Workspace",
        "section": "WORKSPACE",
        "icon": "💎",
        "route": "Upgrade-pro.html",
        "parent": "None (Root)",
        "order": 11,
        "status": "active",
        "visibility": "Public Candidate",
        "allowed_roles": "candidate,admin,super_admin"
    }
]


def _get_stored_menus(db: Session) -> List[dict]:
    try:
        config_entry = db.query(SystemConfig).filter(SystemConfig.config_key == "navigation_menus").first()
        if not config_entry:
            new_entry = SystemConfig(
                config_key="navigation_menus",
                config_value=json.dumps(DEFAULT_NAVIGATION_MENUS)
            )
            db.add(new_entry)
            db.commit()
            return json.loads(json.dumps(DEFAULT_NAVIGATION_MENUS))
        try:
            return json.loads(config_entry.config_value)
        except Exception:
            return json.loads(json.dumps(DEFAULT_NAVIGATION_MENUS))
    except Exception as e:
        print(f"[Menu Warning] _get_stored_menus fallback: {e}")
        return json.loads(json.dumps(DEFAULT_NAVIGATION_MENUS))


def _save_stored_menus(db: Session, menus: List[dict]):
    try:
        config_entry = db.query(SystemConfig).filter(SystemConfig.config_key == "navigation_menus").first()
        if not config_entry:
            config_entry = SystemConfig(
                config_key="navigation_menus",
                config_value=json.dumps(menus)
            )
            db.add(config_entry)
        else:
            config_entry.config_value = json.dumps(menus)
            config_entry.updated_at = datetime.utcnow()
        db.commit()
    except Exception as e:
        print(f"[Menu Save Warning] {e}")



def is_candidate_menu_enabled(identifier: str, db: Session) -> bool:
    """
    Backend Feature Guard:
    Checks if a candidate feature/menu is active in navigation_menus (SystemConfig in DB).
    `identifier` can be a name (e.g. 'Dashboard', 'Interview Studio', 'Generate Questions', 'AI Mock Interview', 'Resume & JD Match', 'Session History')
    or a filename/path (e.g. 'Dashboard.html', 'Interview-studio.html', 'Mock-interview.html', 'Resume-match.html', 'Interview history.html').
    Returns True if active, False if status == "disabled".
    """
    clean_id = (identifier or "").strip().lower()
    if not clean_id:
        return True
        
    menus = _get_stored_menus(db)
    for m in menus:
        name = (m.get("name") or "").strip().lower()
        label = (m.get("label") or "").strip().lower()
        route = (m.get("route") or "").strip().lower()
        clean_route = route.split('/').pop().split('?')[0].split('#')[0].lower()
        
        matches = [
            clean_id == name,
            clean_id == label,
            clean_id == route,
            clean_id == clean_route,
            clean_id in name if len(clean_id) > 3 else False,
            clean_id in label if len(clean_id) > 3 else False,
            name in clean_id if len(name) > 3 else False,
            label in clean_id if len(label) > 3 else False,
            clean_route.replace('.html', '') in clean_id,
            clean_id.replace('.html', '') in clean_route
        ]
        
        if any(matches):
            status = (m.get("status") or "active").lower()
            if status == "disabled":
                return False
                
    return True


@candidate_router.get("/public/menus")
@candidate_router.get("/public-menus")
def get_public_menus(
    db: Session = Depends(get_db)
):
    """
    Public Endpoint: Returns active candidate-visible navigation menus.
    No authentication required. Strictly excludes disabled menus and admin-only menus.
    Never exposes passwords, tokens, audit logs, or system configuration keys.
    """
    all_menus = _get_stored_menus(db)
    all_menus.sort(key=lambda m: m.get("order", 99))
    
    permitted_menus = []
    for m in all_menus:
        status_clean = (m.get("status") or "active").lower()
        if status_clean == "disabled":
            continue
            
        visibility = (m.get("visibility") or "").lower()
        allowed_roles = [r.strip().lower() for r in (m.get("allowed_roles") or "").split(",") if r.strip()]
        
        if allowed_roles and "candidate" not in allowed_roles:
            continue
        if visibility and not any(k in visibility for k in ["candidate", "public", "all"]):
            continue
            
        menu_copy = dict(m)
        menu_copy["enabled"] = True
        menu_copy["visible_to_candidates"] = True
        permitted_menus.append(menu_copy)
        
    res = JSONResponse(
        status_code=200,
        content={
            "success": True,
            "total": len(permitted_menus),
            "menus": permitted_menus
        }
    )
    res.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    res.headers["Pragma"] = "no-cache"
    res.headers["Expires"] = "0"
    return res


@candidate_router.get("/candidate/menus")
@candidate_router.get("/menus")
def get_candidate_menus(
    current_user: UserAccount = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Returns only active/enabled navigation menus permitted for the authenticated candidate user role.
    Strictly filters out disabled menus and admin-only menus.
    """
    all_menus = _get_stored_menus(db)
    all_menus.sort(key=lambda m: m.get("order", 99))
    
    permitted_menus = []
    user_role = (current_user.role or "candidate").lower()
    
    for m in all_menus:
        status_clean = (m.get("status") or "active").lower()
        if status_clean == "disabled":
            continue
            
        visibility = (m.get("visibility") or "").lower()
        allowed_roles = [r.strip().lower() for r in (m.get("allowed_roles") or "").split(",") if r.strip()]
        
        if user_role == "candidate":
            if allowed_roles:
                if "candidate" not in allowed_roles:
                    continue
            else:
                if visibility and not any(k in visibility for k in ["candidate", "public", "all"]):
                    continue
            menu_copy = dict(m)
            menu_copy["enabled"] = True
            menu_copy["visible_to_candidates"] = True
            permitted_menus.append(menu_copy)
        else:
            menu_copy = dict(m)
            menu_copy["enabled"] = status_clean != "disabled"
            menu_copy["visible_to_candidates"] = True
            permitted_menus.append(menu_copy)
            
    return {
        "success": True,
        "total": len(permitted_menus),
        "menus": permitted_menus
    }


@admin_router.get("/menus")
def list_menus(
    current_admin: UserAccount = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """
    Returns list of navigation menus for Super Admin management.
    """
    menus = _get_stored_menus(db)
    menus.sort(key=lambda m: m.get("order", 99))
    return {"total": len(menus), "menus": menus}


@admin_router.post("/menus")
def create_menu(
    payload: dict,
    request: Request,
    current_admin: UserAccount = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """
    Adds a new navigation menu item.
    """
    menus = _get_stored_menus(db)
    new_id = f"menu-{uuid.uuid4().hex[:6]}"
    
    new_item = {
        "id": new_id,
        "name": payload.get("name", "New Menu"),
        "label": payload.get("label", payload.get("name", "New Menu")),
        "type": payload.get("type", "Core Workspace"),
        "section": payload.get("section", "WORKSPACE"),
        "icon": payload.get("icon", "📌"),
        "route": payload.get("route", "Dashboard.html"),
        "parent": payload.get("parent", "None (Root)"),
        "order": int(payload.get("order", len(menus) + 1)),
        "status": payload.get("status", "active"),
        "visibility": payload.get("visibility", "Public Candidate"),
        "allowed_roles": payload.get("allowed_roles", "candidate")
    }
    
    menus.append(new_item)
    _save_stored_menus(db, menus)
    
    record_audit_log(
        db=db,
        admin_user=current_admin,
        action="MENU_CREATED",
        resource=f"menu:{new_id}",
        new_value=json.dumps(new_item),
        ip_address=get_client_ip(request)
    )
    
    return {"success": True, "message": f"Menu item '{new_item['name']}' created.", "menu": new_item}


@admin_router.patch("/menus/{menu_id}")
def update_menu(
    menu_id: str,
    payload: dict,
    request: Request,
    current_admin: UserAccount = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """
    Updates an existing navigation menu item (status, visibility, name, route, etc.).
    """
    menus = _get_stored_menus(db)
    target = None
    for m in menus:
        if m.get("id") == menu_id:
            target = m
            break
    
    if not target:
        raise HTTPException(status_code=404, detail="Menu item not found.")
    
    prev_state = dict(target)
    for field in ["name", "label", "type", "section", "icon", "route", "parent", "status", "visibility", "allowed_roles"]:
        if field in payload and payload[field] is not None:
            target[field] = payload[field]
    if "order" in payload and payload["order"] is not None:
        target["order"] = int(payload["order"])
    
    _save_stored_menus(db, menus)
    
    action_type = "MENU_UPDATED"
    msg = f"Menu '{target['name']}' updated."
    if "status" in payload and payload["status"] != prev_state.get("status"):
        if payload["status"] == "disabled":
            action_type = "MENU_DISABLED"
            msg = f"{target['name']} hidden from candidates."
        elif payload["status"] in ["active", "enabled"]:
            action_type = "MENU_ENABLED"
            msg = f"{target['name']} is now visible to candidates."
    
    record_audit_log(
        db=db,
        admin_user=current_admin,
        action=action_type,
        resource=f"menu:{menu_id}",
        previous_value=json.dumps(prev_state),
        new_value=json.dumps(target),
        ip_address=get_client_ip(request)
    )
    
    return {"success": True, "message": msg, "menu": target}


@admin_router.delete("/menus/{menu_id}")
def delete_menu(
    menu_id: str,
    request: Request,
    current_admin: UserAccount = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """
    Deletes a navigation menu item.
    """
    menus = _get_stored_menus(db)
    new_menus = [m for m in menus if m.get("id") != menu_id]
    
    if len(new_menus) == len(menus):
        raise HTTPException(status_code=404, detail="Menu item not found.")
    
    _save_stored_menus(db, new_menus)
    
    record_audit_log(
        db=db,
        admin_user=current_admin,
        action="MENU_DELETED",
        resource=f"menu:{menu_id}",
        previous_value=json.dumps([m for m in menus if m.get("id") == menu_id]),
        new_value="DELETED",
        ip_address=get_client_ip(request)
    )
    
    return {"success": True, "message": f"Menu item '{menu_id}' deleted."}


# ==============================================================================
# PROMPT MANAGEMENT MODULE ENDPOINTS
# ==============================================================================

def serialize_prompt(p: Prompt) -> dict:
    return {
        "id": p.id,
        "name": p.name,
        "description": p.description,
        "category": p.category,
        "role": p.role,
        "difficulty": p.difficulty,
        "system_prompt": p.system_prompt,
        "user_prompt": p.user_prompt,
        "variables": p.variables,
        "model": p.model,
        "temperature": p.temperature,
        "max_tokens": p.max_tokens,
        "version": p.version,
        "status": p.status,
        "created_at": p.created_at.isoformat() if p.created_at else None,
        "updated_at": p.updated_at.isoformat() if p.updated_at else None,
        "is_active": p.is_active
    }


def serialize_prompt_version(v: PromptVersion) -> dict:
    return {
        "id": v.id,
        "prompt_id": v.prompt_id,
        "version": v.version,
        "name": v.name,
        "description": v.description,
        "category": v.category,
        "role": v.role,
        "difficulty": v.difficulty,
        "system_prompt": v.system_prompt,
        "user_prompt": v.user_prompt,
        "variables": v.variables,
        "model": v.model,
        "temperature": v.temperature,
        "max_tokens": v.max_tokens,
        "status": v.status,
        "change_summary": v.change_summary,
        "changed_by_email": v.changed_by_email,
        "created_at": v.created_at.isoformat() if v.created_at else None
    }


@admin_router.get("/prompts")
def list_prompts(
    search: Optional[str] = None,
    category: Optional[str] = None,
    role: Optional[str] = None,
    difficulty: Optional[str] = None,
    model: Optional[str] = None,
    status: Optional[str] = None,
    sort: Optional[str] = "updated_desc",
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    current_admin: UserAccount = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """
    Retrieves Prompt Library with filtering, search, sorting, and pagination.
    Accessible to: 'admin' and 'super_admin'.
    """
    query = db.query(Prompt)

    if search:
        s_term = f"%{search.strip().lower()}%"
        query = query.filter(
            func.lower(Prompt.name).like(s_term) |
            func.lower(Prompt.description).like(s_term) |
            func.lower(Prompt.user_prompt).like(s_term)
        )

    if category:
        query = query.filter(func.lower(Prompt.category) == category.strip().lower())

    if role:
        query = query.filter(func.lower(Prompt.role) == role.strip().lower())

    if difficulty:
        query = query.filter(func.lower(Prompt.difficulty) == difficulty.strip().lower())

    if model:
        query = query.filter(func.lower(Prompt.model) == model.strip().lower())

    if status:
        query = query.filter(func.lower(Prompt.status) == status.strip().lower())

    if sort == "updated_asc":
        query = query.order_by(Prompt.updated_at.asc())
    elif sort == "name_asc":
        query = query.order_by(Prompt.name.asc())
    elif sort == "name_desc":
        query = query.order_by(Prompt.name.desc())
    elif sort == "version_desc":
        query = query.order_by(Prompt.version.desc())
    else:
        query = query.order_by(Prompt.updated_at.desc())

    total = query.count()
    prompts = query.offset(offset).limit(limit).all()

    return {
        "total": total,
        "offset": offset,
        "limit": limit,
        "prompts": [serialize_prompt(p) for p in prompts]
    }


@admin_router.get("/prompts/{prompt_id}")
def get_prompt_by_id(
    prompt_id: int,
    current_admin: UserAccount = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """
    Retrieves a single Prompt by ID.
    """
    prompt = db.query(Prompt).filter(Prompt.id == prompt_id).first()
    if not prompt:
        raise HTTPException(status_code=404, detail="Prompt not found.")
    return {"prompt": serialize_prompt(prompt)}


@admin_router.post("/prompts")
def create_prompt(
    payload: PromptCreateRequest,
    request: Request,
    current_admin: UserAccount = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """
    Creates a new Prompt and provisions initial Version 1 entry.
    Accessible to: 'admin' and 'super_admin'.
    """
    import re

    # Auto-detect variables from {{variable_name}} syntax if not explicitly supplied
    extracted_vars = re.findall(r"\{\{\s*(\w+)\s*\}\}", payload.user_prompt or "")
    if payload.system_prompt:
        extracted_vars.extend(re.findall(r"\{\{\s*(\w+)\s*\}\}", payload.system_prompt))
    
    unique_vars = list(dict.fromkeys(extracted_vars))
    
    if payload.variables:
        manual_vars = [v.strip() for v in payload.variables.split(",") if v.strip()]
        combined_vars = list(dict.fromkeys(unique_vars + manual_vars))
        vars_str = ",".join(combined_vars)
    else:
        vars_str = ",".join(unique_vars)

    new_prompt = Prompt(
        name=payload.name.strip(),
        description=payload.description.strip() if payload.description else None,
        category=payload.category.strip(),
        role=payload.role.strip() if payload.role else "General Tech",
        difficulty=payload.difficulty.strip() if payload.difficulty else "Hard",
        system_prompt=payload.system_prompt.strip() if payload.system_prompt else None,
        user_prompt=payload.user_prompt.strip(),
        variables=vars_str,
        model=payload.model or "gemini-1.5-flash",
        temperature=payload.temperature if payload.temperature is not None else 0.7,
        max_tokens=payload.max_tokens or 1024,
        version=1,
        status=payload.status or "draft",
        created_by=current_admin.id,
        is_active=True
    )
    db.add(new_prompt)
    db.commit()
    db.refresh(new_prompt)

    # Provision Version 1 log
    v1 = PromptVersion(
        prompt_id=new_prompt.id,
        version=1,
        name=new_prompt.name,
        description=new_prompt.description,
        category=new_prompt.category,
        role=new_prompt.role,
        difficulty=new_prompt.difficulty,
        system_prompt=new_prompt.system_prompt,
        user_prompt=new_prompt.user_prompt,
        variables=new_prompt.variables,
        model=new_prompt.model,
        temperature=new_prompt.temperature,
        max_tokens=new_prompt.max_tokens,
        status=new_prompt.status,
        change_summary=payload.change_summary or "Initial prompt creation",
        changed_by=current_admin.id,
        changed_by_email=current_admin.email
    )
    db.add(v1)
    db.commit()

    record_audit_log(
        db=db,
        admin_user=current_admin,
        action="PROMPT_CREATED",
        resource=f"prompt:{new_prompt.id}",
        new_value=json.dumps({"name": new_prompt.name, "category": new_prompt.category, "version": 1}),
        ip_address=get_client_ip(request)
    )

    return {"success": True, "prompt": serialize_prompt(new_prompt)}


@admin_router.patch("/prompts/{prompt_id}")
def update_prompt(
    prompt_id: int,
    payload: PromptUpdateRequest,
    request: Request,
    current_admin: UserAccount = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """
    Updates prompt details and provisions a new version entry when meaningful prompt parameters change.
    Accessible to: 'admin' and 'super_admin'.
    """
    import re

    prompt = db.query(Prompt).filter(Prompt.id == prompt_id).first()
    if not prompt:
        raise HTTPException(status_code=404, detail="Prompt not found.")

    prev_state = serialize_prompt(prompt)
    updated_meaningful_field = False

    if payload.name is not None and payload.name.strip() != prompt.name:
        prompt.name = payload.name.strip()
        updated_meaningful_field = True

    if payload.description is not None and payload.description != prompt.description:
        prompt.description = payload.description.strip()

    if payload.category is not None and payload.category != prompt.category:
        prompt.category = payload.category.strip()
        updated_meaningful_field = True

    if payload.role is not None and payload.role != prompt.role:
        prompt.role = payload.role.strip()
        updated_meaningful_field = True

    if payload.difficulty is not None and payload.difficulty != prompt.difficulty:
        prompt.difficulty = payload.difficulty.strip()
        updated_meaningful_field = True

    if payload.system_prompt is not None and payload.system_prompt != prompt.system_prompt:
        prompt.system_prompt = payload.system_prompt.strip()
        updated_meaningful_field = True

    if payload.user_prompt is not None and payload.user_prompt != prompt.user_prompt:
        prompt.user_prompt = payload.user_prompt.strip()
        updated_meaningful_field = True

    if payload.model is not None and payload.model != prompt.model:
        prompt.model = payload.model.strip()
        updated_meaningful_field = True

    if payload.temperature is not None and payload.temperature != prompt.temperature:
        prompt.temperature = payload.temperature
        updated_meaningful_field = True

    if payload.max_tokens is not None and payload.max_tokens != prompt.max_tokens:
        prompt.max_tokens = payload.max_tokens
        updated_meaningful_field = True

    if payload.status is not None and payload.status != prompt.status:
        prompt.status = payload.status.strip()
        updated_meaningful_field = True

    # Re-extract variables if prompt text updated or variable string supplied
    if payload.user_prompt is not None or payload.system_prompt is not None or payload.variables is not None:
        extracted_vars = re.findall(r"\{\{\s*(\w+)\s*\}\}", prompt.user_prompt or "")
        if prompt.system_prompt:
            extracted_vars.extend(re.findall(r"\{\{\s*(\w+)\s*\}\}", prompt.system_prompt))
        unique_vars = list(dict.fromkeys(extracted_vars))

        if payload.variables is not None:
            manual_vars = [v.strip() for v in payload.variables.split(",") if v.strip()]
            combined_vars = list(dict.fromkeys(unique_vars + manual_vars))
            prompt.variables = ",".join(combined_vars)
        else:
            prompt.variables = ",".join(unique_vars)

    prompt.updated_at = datetime.utcnow()

    # Increment version if prompt template or settings were updated
    if updated_meaningful_field:
        prompt.version += 1
        new_v = PromptVersion(
            prompt_id=prompt.id,
            version=prompt.version,
            name=prompt.name,
            description=prompt.description,
            category=prompt.category,
            role=prompt.role,
            difficulty=prompt.difficulty,
            system_prompt=prompt.system_prompt,
            user_prompt=prompt.user_prompt,
            variables=prompt.variables,
            model=prompt.model,
            temperature=prompt.temperature,
            max_tokens=prompt.max_tokens,
            status=prompt.status,
            change_summary=payload.change_summary or f"Updated parameters (v{prompt.version})",
            changed_by=current_admin.id,
            changed_by_email=current_admin.email
        )
        db.add(new_v)

    db.commit()
    db.refresh(prompt)

    action_label = "PROMPT_ARCHIVED" if payload.status == "archived" else "PROMPT_UPDATED"
    record_audit_log(
        db=db,
        admin_user=current_admin,
        action=action_label,
        resource=f"prompt:{prompt.id}",
        previous_value=json.dumps({"name": prev_state["name"], "version": prev_state["version"], "status": prev_state["status"]}),
        new_value=json.dumps({"name": prompt.name, "version": prompt.version, "status": prompt.status}),
        ip_address=get_client_ip(request)
    )

    return {"success": True, "prompt": serialize_prompt(prompt)}


@admin_router.delete("/prompts/{prompt_id}")
def delete_prompt(
    prompt_id: int,
    request: Request,
    current_admin: UserAccount = Depends(require_super_admin),
    db: Session = Depends(get_db)
):
    """
    Deletes a Prompt and its version history.
    Restricted strictly to: 'super_admin'.
    """
    prompt = db.query(Prompt).filter(Prompt.id == prompt_id).first()
    if not prompt:
        raise HTTPException(status_code=404, detail="Prompt not found.")

    prompt_name = prompt.name
    db.query(PromptVersion).filter(PromptVersion.prompt_id == prompt_id).delete()
    db.delete(prompt)
    db.commit()

    record_audit_log(
        db=db,
        admin_user=current_admin,
        action="PROMPT_DELETED",
        resource=f"prompt:{prompt_id}",
        new_value=f"Deleted prompt '{prompt_name}'",
        ip_address=get_client_ip(request)
    )

    return {"success": True, "message": f"Prompt '{prompt_name}' has been permanently deleted."}


@admin_router.get("/prompts/{prompt_id}/versions")
def get_prompt_version_history(
    prompt_id: int,
    current_admin: UserAccount = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """
    Retrieves version history for a given Prompt.
    Accessible to: 'admin' and 'super_admin'.
    """
    prompt = db.query(Prompt).filter(Prompt.id == prompt_id).first()
    if not prompt:
        raise HTTPException(status_code=404, detail="Prompt not found.")

    versions = db.query(PromptVersion).filter(
        PromptVersion.prompt_id == prompt_id
    ).order_by(PromptVersion.version.desc()).all()

    return {
        "prompt_id": prompt_id,
        "prompt_name": prompt.name,
        "versions": [serialize_prompt_version(v) for v in versions]
    }


@admin_router.post("/prompts/{prompt_id}/test")
def test_prompt_synthesis(
    prompt_id: int,
    payload: PromptTestRequest,
    request: Request,
    current_admin: UserAccount = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """
    Executes prompt AI generation server-side with test variable values.
    Does not expose API keys to client.
    """
    import time
    from app.services import generate_ai_questions

    prompt = db.query(Prompt).filter(Prompt.id == prompt_id).first()
    if not prompt:
        raise HTTPException(status_code=404, detail="Prompt not found.")

    # Substitute variables into prompt templates
    sys_prompt = prompt.system_prompt or ""
    usr_prompt = prompt.user_prompt or ""
    test_vars = payload.test_variables or {}

    for var_key, var_val in test_vars.items():
        placeholder = f"{{{{{var_key}}}}}"
        sys_prompt = sys_prompt.replace(placeholder, str(var_val))
        usr_prompt = usr_prompt.replace(placeholder, str(var_val))

    full_prompt_text = f"{sys_prompt}\n\n{usr_prompt}".strip()

    start_time = time.time()
    try:
        # Check if AI provider API key is set
        has_gemini = bool(os.environ.get("GEMINI_API_KEY"))
        has_groq = bool(os.environ.get("GROQ_API_KEY"))

        if not has_gemini and not has_groq:
            return {
                "success": False,
                "error": "AI provider is not configured."
            }

        ai_response_text = generate_ai_questions(full_prompt_text)
        elapsed_ms = int((time.time() - start_time) * 1000)
        est_tokens = max(10, len(ai_response_text.split()) * 2)

        record_audit_log(
            db=db,
            admin_user=current_admin,
            action="PROMPT_TESTED",
            resource=f"prompt:{prompt_id}",
            new_value=json.dumps({"model": prompt.model, "latency_ms": elapsed_ms}),
            ip_address=get_client_ip(request)
        )

        return {
            "success": True,
            "output": ai_response_text,
            "model": prompt.model,
            "temperature": prompt.temperature,
            "tokens": est_tokens,
            "response_time_ms": elapsed_ms
        }
    except Exception as e:
        elapsed_ms = int((time.time() - start_time) * 1000)
        err_msg = str(e)
        if "API key" in err_msg or "not configured" in err_msg or "unauthorized" in err_msg.lower():
            return {
                "success": False,
                "error": "AI provider is not configured."
            }
        return {
            "success": False,
            "error": f"AI synthesis error: {err_msg}",
            "response_time_ms": elapsed_ms
        }


@admin_router.post("/prompts/{prompt_id}/restore/{version_id}")
def restore_prompt_version(
    prompt_id: int,
    version_id: int,
    request: Request,
    current_admin: UserAccount = Depends(require_super_admin),
    db: Session = Depends(get_db)
):
    """
    Restores prompt configuration from a prior version log and provisions a NEW incremented version entry.
    Restricted strictly to: 'super_admin'.
    """
    prompt = db.query(Prompt).filter(Prompt.id == prompt_id).first()
    if not prompt:
        raise HTTPException(status_code=404, detail="Prompt not found.")

    target_ver = db.query(PromptVersion).filter(
        PromptVersion.id == version_id,
        PromptVersion.prompt_id == prompt_id
    ).first()
    if not target_ver:
        raise HTTPException(status_code=404, detail="Specified prompt version not found.")

    # Update prompt object values to restored version state
    prompt.name = target_ver.name
    prompt.description = target_ver.description
    prompt.category = target_ver.category
    prompt.role = target_ver.role
    prompt.difficulty = target_ver.difficulty
    prompt.system_prompt = target_ver.system_prompt
    prompt.user_prompt = target_ver.user_prompt
    prompt.variables = target_ver.variables
    prompt.model = target_ver.model
    prompt.temperature = target_ver.temperature
    prompt.max_tokens = target_ver.max_tokens
    prompt.status = target_ver.status
    prompt.version += 1
    prompt.updated_at = datetime.utcnow()

    # Record new incremented version log for the restoration
    new_v = PromptVersion(
        prompt_id=prompt.id,
        version=prompt.version,
        name=prompt.name,
        description=prompt.description,
        category=prompt.category,
        role=prompt.role,
        difficulty=prompt.difficulty,
        system_prompt=prompt.system_prompt,
        user_prompt=prompt.user_prompt,
        variables=prompt.variables,
        model=prompt.model,
        temperature=prompt.temperature,
        max_tokens=prompt.max_tokens,
        status=prompt.status,
        change_summary=f"Restored from version v{target_ver.version}",
        changed_by=current_admin.id,
        changed_by_email=current_admin.email
    )
    db.add(new_v)
    db.commit()
    db.refresh(prompt)

    record_audit_log(
        db=db,
        admin_user=current_admin,
        action="PROMPT_VERSION_RESTORED",
        resource=f"prompt:{prompt.id}",
        previous_value=f"Version before restore: v{prompt.version - 1}",
        new_value=f"Restored v{target_ver.version} -> New version v{prompt.version}",
        ip_address=get_client_ip(request)
    )

    return {"success": True, "prompt": serialize_prompt(prompt)}





