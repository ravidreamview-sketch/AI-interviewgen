"""Administrator subscription operations and candidate entitlement status."""

from datetime import timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.auth_deps import (
    require_admin,
    require_authenticated_candidate,
    require_super_admin,
)
from app.database import get_db
from app.db_models import PaymentVerification, Subscription, SubscriptionPlan, UserAccount
from app.models import (
    SubscriptionActionRequest,
    SubscriptionAssignmentRequest,
    SubscriptionPaymentStatusRequest,
    SubscriptionPlanCreateRequest,
    SubscriptionRenewalRequest,
)
from app import subscription_service as service

subscription_admin_router = APIRouter(tags=["Admin Subscriptions"])
subscription_candidate_router = APIRouter(tags=["Candidate Subscription"])


def _iso(value):
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()


def _plan_payload(plan: SubscriptionPlan) -> dict:
    return {
        "id": plan.id,
        "code": plan.code,
        "name": plan.name,
        "description": plan.description,
        "duration_days": plan.duration_days,
        "price_minor": plan.price_minor,
        "currency": plan.currency,
        "is_active": plan.is_active,
    }


def _subscription_payload(subscription: Subscription) -> dict:
    payment = subscription.payment_verification
    return {
        "id": subscription.id,
        "user_id": subscription.user_id,
        "plan_id": subscription.plan_id,
        "plan_code": subscription.plan_code_snapshot,
        "plan_name": subscription.plan_name_snapshot,
        "status": subscription.status,
        "starts_at": _iso(subscription.starts_at),
        "ends_at": _iso(subscription.ends_at),
        "amount_minor": subscription.amount_minor_snapshot,
        "currency": subscription.currency_snapshot,
        "renewal_of_id": subscription.renewal_of_id,
        "approved_by_id": subscription.approved_by_id,
        "approved_at": _iso(subscription.approved_at),
        "suspended_at": _iso(subscription.suspended_at),
        "revoked_at": _iso(subscription.revoked_at),
        "payment": {
            "status": payment.status,
            "provider": payment.provider,
            "provider_reference": payment.provider_reference,
            "amount_minor": payment.amount_minor,
            "currency": payment.currency,
            "verified_by_id": payment.verified_by_id,
            "verified_at": _iso(payment.verified_at),
            "status_changed_at": _iso(payment.status_changed_at),
            "status_reason": payment.status_reason,
        } if payment else None,
    }


@subscription_admin_router.get("/subscription-plans")
def list_subscription_plans(
    _: UserAccount = Depends(require_admin),
    db: Session = Depends(get_db),
):
    plans = db.query(SubscriptionPlan).order_by(SubscriptionPlan.id.asc()).all()
    return {"plans": [_plan_payload(plan) for plan in plans]}


@subscription_admin_router.post("/subscription-plans", status_code=status.HTTP_201_CREATED)
def create_subscription_plan(
    payload: SubscriptionPlanCreateRequest,
    actor: UserAccount = Depends(require_super_admin),
    db: Session = Depends(get_db),
):
    plan = service.create_plan(
        db,
        actor,
        code=payload.code,
        name=payload.name,
        description=payload.description,
        price_minor=payload.price_minor,
        currency=payload.currency,
    )
    return {"plan": _plan_payload(plan)}


@subscription_admin_router.get("/subscriptions")
def list_subscriptions(
    user_id: int | None = None,
    _: UserAccount = Depends(require_admin),
    db: Session = Depends(get_db),
):
    query = db.query(Subscription)
    if user_id is not None:
        query = query.filter(Subscription.user_id == user_id)
    rows = query.order_by(Subscription.created_at.desc(), Subscription.id.desc()).limit(500).all()
    return {"subscriptions": [_subscription_payload(row) for row in rows]}


@subscription_admin_router.post("/subscriptions", status_code=status.HTTP_201_CREATED)
def assign_subscription(
    payload: SubscriptionAssignmentRequest,
    actor: UserAccount = Depends(require_admin),
    db: Session = Depends(get_db),
):
    subscription = service.assign_subscription(
        db, actor, user_id=payload.user_id, plan_id=payload.plan_id,
        provider=payload.provider, provider_reference=payload.provider_reference,
        amount_minor=payload.amount_minor, currency=payload.currency,
        reason=payload.reason,
    )
    return {"subscription": _subscription_payload(subscription)}


@subscription_admin_router.post("/subscriptions/{subscription_id}/renew", status_code=status.HTTP_201_CREATED)
def renew_subscription(
    subscription_id: int,
    payload: SubscriptionRenewalRequest,
    actor: UserAccount = Depends(require_admin),
    db: Session = Depends(get_db),
):
    subscription = service.renew_subscription(
        db, actor, subscription_id=subscription_id, plan_id=payload.plan_id,
        provider=payload.provider, provider_reference=payload.provider_reference,
        amount_minor=payload.amount_minor, currency=payload.currency,
        reason=payload.reason,
    )
    return {"subscription": _subscription_payload(subscription)}


@subscription_admin_router.post("/subscriptions/{subscription_id}/verify-payment")
def verify_subscription_payment(
    subscription_id: int,
    payload: SubscriptionActionRequest,
    actor: UserAccount = Depends(require_admin),
    db: Session = Depends(get_db),
):
    subscription = service.verify_payment(db, actor, subscription_id, reason=payload.reason)
    return {"subscription": _subscription_payload(subscription)}


@subscription_admin_router.post("/subscriptions/{subscription_id}/payment-status")
def change_subscription_payment_status(
    subscription_id: int,
    payload: SubscriptionPaymentStatusRequest,
    actor: UserAccount = Depends(require_admin),
    db: Session = Depends(get_db),
):
    payment: PaymentVerification = service.change_payment_status(
        db, actor, subscription_id, new_status=payload.status, reason=payload.reason,
    )
    return {"payment": {"id": payment.id, "subscription_id": payment.subscription_id, "status": payment.status}}


@subscription_admin_router.post("/subscriptions/{subscription_id}/suspend")
def suspend_subscription(
    subscription_id: int,
    payload: SubscriptionActionRequest,
    actor: UserAccount = Depends(require_admin),
    db: Session = Depends(get_db),
):
    subscription = service.suspend_subscription(db, actor, subscription_id, reason=payload.reason)
    return {"subscription": _subscription_payload(subscription)}


@subscription_admin_router.post("/subscriptions/{subscription_id}/revoke")
def revoke_subscription(
    subscription_id: int,
    payload: SubscriptionActionRequest,
    actor: UserAccount = Depends(require_admin),
    db: Session = Depends(get_db),
):
    subscription = service.revoke_subscription(db, actor, subscription_id, reason=payload.reason)
    return {"subscription": _subscription_payload(subscription)}


@subscription_candidate_router.get("/candidate/subscription")
@subscription_candidate_router.get("/subscription")
def candidate_subscription_status(
    candidate: UserAccount = Depends(require_authenticated_candidate),
    db: Session = Depends(get_db),
):
    return service.get_candidate_subscription_status(db, candidate)
