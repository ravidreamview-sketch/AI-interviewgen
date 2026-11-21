from fastapi import APIRouter, Depends, HTTPException, status
from typing import List, Dict, Any
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.api.v1.auth import get_current_user_from_token
from app.db_models import UserAccount, AuditLog

router = APIRouter()


def require_admin(user: UserAccount = Depends(get_current_user_from_token)) -> UserAccount:
    """Enforces administrative Role-Based Access Control (RBAC)."""
    if user.role not in ("admin", "super_admin"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Administrative privileges required")
    return user


@router.get("/users", tags=["Administration"])
def list_users(
    admin: UserAccount = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """Lists registered user accounts with role and tier information."""
    users = db.query(UserAccount).limit(50).all()
    return [
        {
            "id": u.id,
            "email": u.email,
            "full_name": u.full_name,
            "role": u.role,
            "plan_tier": u.plan_tier,
            "is_active": u.is_active,
            "created_at": str(u.created_at)
        }
        for u in users
    ]


@router.get("/audit-logs", tags=["Administration"])
def list_audit_logs(
    admin: UserAccount = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """Retrieves system and administrative audit records."""
    logs = db.query(AuditLog).order_by(AuditLog.timestamp.desc()).limit(50).all()
    return [
        {
            "id": l.id,
            "action": l.action,
            "resource": l.resource,
            "admin_email": l.admin_email,
            "timestamp": str(l.timestamp),
            "ip_address": l.ip_address
        }
        for l in logs
    ]

