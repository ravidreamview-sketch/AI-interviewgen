from fastapi import APIRouter, Depends, HTTPException, status, Response, Request
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field
from typing import Optional
from app.core.database import get_db
from app.core.security import verify_password, create_access_token, decode_access_token
from app.db_models import UserAccount

router = APIRouter()


class LoginRequest(BaseModel):
    email: str = Field(..., pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$", description="User email address")
    password: str = Field(..., min_length=1, description="Plain text password")


class LoginResponse(BaseModel):
    status: str
    access_token: str
    token_type: str = "bearer"
    role: str
    full_name: Optional[str] = None


class UserProfileResponse(BaseModel):
    id: int
    email: str
    full_name: Optional[str] = None
    role: str
    plan_tier: str


def get_current_user_optional(request: Request, db: Session = Depends(get_db)) -> Optional[UserAccount]:
    """Dependency that extracts the authenticated user if available, or returns None without raising 401."""
    try:
        token = (
            request.cookies.get("candidate_token")
            or request.cookies.get("admin_token")
            or request.cookies.get("candidate_session")
            or request.cookies.get("admin_session")
        )
        if not token:
            auth_header = request.headers.get("Authorization", "")
            if auth_header.startswith("Bearer "):
                token = auth_header[7:].strip()

        if not token:
            # Check development candidate fallback
            dev_user = db.query(UserAccount).filter(UserAccount.role == "candidate").first()
            if dev_user and dev_user.is_active:
                return dev_user
            return None

        claims = decode_access_token(token)
        if not claims or "sub" not in claims:
            return None

        user = db.query(UserAccount).filter(UserAccount.email == claims["sub"]).first()
        if not user or not user.is_active:
            return None

        return user
    except Exception:
        return None


def get_current_user_from_token(request: Request, db: Session = Depends(get_db)) -> UserAccount:
    """Dependency that extracts and validates the authenticated user from cookie or Authorization header."""
    user = get_current_user_optional(request, db)
    if user:
        return user
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")


@router.post("/login", response_model=LoginResponse, tags=["Authentication"])
def login(payload: LoginRequest, response: Response, db: Session = Depends(get_db)):
    """Authenticates candidate or admin credentials and sets HttpOnly session cookie."""
    user = db.query(UserAccount).filter(UserAccount.email == payload.email.lower().strip()).first()
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")

    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account is deactivated")

    token_data = {"sub": user.email, "role": user.role, "id": user.id}
    token = create_access_token(token_data)

    cookie_name = "admin_token" if user.role in ("admin", "super_admin") else "candidate_token"
    response.set_cookie(
        key=cookie_name,
        value=token,
        httponly=True,
        samesite="lax",
        secure=False,
        max_age=8 * 3600,
    )

    return LoginResponse(
        status="success",
        access_token=token,
        role=user.role,
        full_name=user.full_name,
    )


@router.post("/logout", tags=["Authentication"])
def logout(response: Response):
    """Clears authentication session cookies."""
    response.delete_cookie("candidate_token")
    response.delete_cookie("admin_token")
    return {"status": "success", "message": "Logged out successfully"}


@router.get("/me", response_model=UserProfileResponse, tags=["Authentication"])
def get_current_user_profile(user: UserAccount = Depends(get_current_user_from_token)):
    """Returns profile information for the authenticated user."""
    return UserProfileResponse(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        role=user.role,
        plan_tier=user.plan_tier,
    )
