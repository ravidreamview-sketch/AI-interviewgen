from fastapi import Request, HTTPException, Depends, status
from sqlalchemy.orm import Session
from typing import Optional, List, Dict
import time
import os
import uuid

from app.database import get_db
from app.db_models import UserAccount, AuditLog
from app.security import decode_access_token


def get_client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "127.0.0.1"


def is_request_https(request: Request) -> bool:
    """
    Determines if current request is HTTPS or running in production deployment.
    """
    if os.environ.get("ENV", "").lower() in ["production", "prod"]:
        return True
    if os.environ.get("VERCEL"):
        return True
    if request.headers.get("x-forwarded-proto") == "https":
        return True
    return request.url.scheme == "https"


# ------------------------------------------------------------------------------
# IN-MEMORY RATE LIMITER FOR LOGIN (DEV / PER-INSTANCE)
# ------------------------------------------------------------------------------
# Tracks failed attempts: key -> list of failure timestamps
FAILED_LOGIN_ATTEMPTS: Dict[str, List[float]] = {}
RATE_LIMIT_WINDOW_SECONDS = 300  # 5 minutes
MAX_FAILED_ATTEMPTS = 5


def check_login_rate_limit(request: Request, email: str) -> None:
    """
    Checks if client IP or target email has exceeded failed login threshold.
    Raises 429 Too Many Requests if rate limit is exceeded.
    """
    now = time.time()
    ip = get_client_ip(request)
    keys = [f"ip:{ip}", f"email:{email.strip().lower()}"]
    
    for key in keys:
        attempts = FAILED_LOGIN_ATTEMPTS.get(key, [])
        # Filter attempts within sliding window
        valid_attempts = [t for t in attempts if now - t < RATE_LIMIT_WINDOW_SECONDS]
        FAILED_LOGIN_ATTEMPTS[key] = valid_attempts
        
        if len(valid_attempts) >= MAX_FAILED_ATTEMPTS:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many failed login attempts. Please wait 5 minutes before trying again."
            )


def record_failed_login_attempt(request: Request, email: str) -> None:
    """
    Records a failed login attempt for both IP and email.
    """
    now = time.time()
    ip = get_client_ip(request)
    for key in [f"ip:{ip}", f"email:{email.strip().lower()}"]:
        if key not in FAILED_LOGIN_ATTEMPTS:
            FAILED_LOGIN_ATTEMPTS[key] = []
        FAILED_LOGIN_ATTEMPTS[key].append(now)


def clear_failed_login_attempts(request: Request, email: str) -> None:
    """
    Clears failed attempt tracking upon successful authentication.
    """
    ip = get_client_ip(request)
    FAILED_LOGIN_ATTEMPTS.pop(f"ip:{ip}", None)
    FAILED_LOGIN_ATTEMPTS.pop(f"email:{email.strip().lower()}", None)


# ------------------------------------------------------------------------------
# CSRF DEFENSE-IN-DEPTH CHECK FOR MUTATING ADMIN ACTIONS
# ------------------------------------------------------------------------------
def verify_csrf_protection(request: Request) -> None:
    """
    Verifies that state-changing admin requests (POST, PATCH, DELETE) carry anti-CSRF proof:
    1. Authorization: Bearer header, OR
    2. Custom request header (X-Requested-With, X-Admin-CSRF)
    """
    if request.method in ["GET", "HEAD", "OPTIONS"]:
        return
    
    # Check for Authorization header (not subject to ambient browser CSRF)
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        return
    
    # Check custom request header (cannot be set cross-origin without preflight CORS approval)
    has_custom_header = bool(
        request.headers.get("x-requested-with") or
        request.headers.get("x-admin-csrf") or
        request.headers.get("x-custom-action")
    )
    
    if not has_custom_header:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="CSRF Protection: Missing required request header (X-Requested-With or X-Admin-CSRF)."
        )


# ------------------------------------------------------------------------------
# AUTHENTICATION & RBAC GUARDS
# ------------------------------------------------------------------------------
def get_current_user(
    request: Request,
    db: Session = Depends(get_db)
) -> UserAccount:
    """
    Extracts and validates the authentication token from either:
    1. Authorization: Bearer <token> header
    2. admin_session HttpOnly cookie
    """
    token = None
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header.split(" ", 1)[1].strip()
    
    if not token:
        token = request.cookies.get("admin_session")
    if not token:
        token = request.cookies.get("candidate_session")
    
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required. Please log in.",
            headers={"WWW-Authenticate": "Bearer"}
        )
    
    payload = decode_access_token(token)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session has expired or token is invalid. Please log in again.",
            headers={"WWW-Authenticate": "Bearer"}
        )
    
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload."
        )
    
    user = db.query(UserAccount).filter(UserAccount.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account no longer exists."
        )
    
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This account has been deactivated. Contact Super Admin."
        )
    
    return user


def require_admin(
    request: Request,
    current_user: UserAccount = Depends(get_current_user)
) -> UserAccount:
    """
    Role check: Allows 'admin' and 'super_admin'.
    Also enforces CSRF defense-in-depth on state-changing methods.
    """
    verify_csrf_protection(request)
    if current_user.role not in ["admin", "super_admin"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access forbidden: Admin privileges required."
        )
    return current_user


def require_super_admin(
    request: Request,
    current_user: UserAccount = Depends(get_current_user)
) -> UserAccount:
    """
    Role check: Strictly allows 'super_admin' only.
    Also enforces CSRF defense-in-depth on state-changing methods.
    """
    verify_csrf_protection(request)
    if current_user.role != "super_admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access forbidden: Super Admin privileges required."
        )
    return current_user


def require_candidate(
    request: Request,
    current_user: UserAccount = Depends(get_current_user)
) -> UserAccount:
    """
    Role check: Allows authenticated candidates, admins, or super admins.
    """
    if not current_user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required. Please log in."
        )
    return current_user


def record_audit_log(
    db: Session,
    admin_user: Optional[UserAccount],
    action: str,
    resource: str,
    previous_value: Optional[str] = None,
    new_value: Optional[str] = None,
    ip_address: Optional[str] = None,
    request_id: Optional[str] = None
) -> Optional[AuditLog]:
    """
    Creates an immutable audit log entry for administrative actions.
    """
    try:
        log_entry = AuditLog(
            user_id=admin_user.id if admin_user else None,
            admin_email=admin_user.email if admin_user else "system",
            action=action,
            resource=resource,
            previous_value=previous_value,
            new_value=new_value,
            ip_address=ip_address,
            request_id=request_id or str(uuid.uuid4())[:8]
        )
        db.add(log_entry)
        db.commit()
        db.refresh(log_entry)
        return log_entry
    except Exception as e:
        db.rollback()
        print(f"[AuditLog] Failed to record audit log: {e}")
        return None
