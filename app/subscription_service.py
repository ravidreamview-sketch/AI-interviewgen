"""Server-side subscription lifecycle and entitlement rules.

Payment status is maintained by an authorized administrator. This module never
accepts client supplied activation times and never treats account plan labels as
payment evidence.
"""

from __future__ import annotations

import json
import threading
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from typing import Iterator

from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db_models import (
    AuditLog,
    PaymentVerification,
    Subscription,
    SubscriptionPlan,
    UserAccount,
)

TERM = timedelta(days=30)
_user_locks: dict[tuple[str, int], threading.RLock] = {}
_user_locks_guard = threading.Lock()


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _key_for_user(db: Session, user_id: int) -> tuple[str, int]:
    bind = db.get_bind()
    return (str(bind.url), user_id)


@contextmanager
def _serialize_user_operation(db: Session, user_id: int) -> Iterator[None]:
    """Serialize same-process SQLite writers; PostgreSQL also locks the user row."""
    key = _key_for_user(db, user_id)
    with _user_locks_guard:
        lock = _user_locks.setdefault(key, threading.RLock())
    with lock:
        yield


def _fail(code: int, message: str) -> None:
    raise HTTPException(status_code=code, detail=message)


def _admin_actor(actor: UserAccount, target_user_id: int | None = None) -> None:
    if not actor or actor.role not in {"admin", "super_admin"} or not actor.is_active:
        _fail(status.HTTP_403_FORBIDDEN, "Administrator access is required.")
    if target_user_id is not None and actor.id == target_user_id:
        _fail(status.HTTP_403_FORBIDDEN, "Administrators cannot approve their own candidate subscription.")


def _audit(
    db: Session,
    actor: UserAccount | None,
    action: str,
    resource: str,
    before: dict | None = None,
    after: dict | None = None,
) -> None:
    # Use the existing UTC-naive AuditLog timestamp convention. The log row is
    # committed with the associated subscription/payment state change.
    db.add(
        AuditLog(
            user_id=actor.id if actor else None,
            admin_email=actor.email if actor else "system",
            action=action,
            resource=resource,
            previous_value=json.dumps(before, sort_keys=True) if before is not None else None,
            new_value=json.dumps(after, sort_keys=True) if after is not None else None,
            timestamp=utc_now().replace(tzinfo=None),
        )
    )


def _commit_or_rollback(db: Session) -> None:
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise


def create_plan(
    db: Session,
    actor: UserAccount,
    *,
    code: str,
    name: str,
    price_minor: int,
    currency: str,
    description: str | None = None,
) -> SubscriptionPlan:
    _admin_actor(actor)
    code = code.strip().lower()
    name = name.strip()
    currency = currency.strip().upper()
    if not code or not name or price_minor <= 0 or not _valid_currency(currency):
        _fail(status.HTTP_422_UNPROCESSABLE_ENTITY, "Plan code, name, positive price, and three-letter currency are required.")
    plan = SubscriptionPlan(
        code=code,
        name=name,
        description=description.strip() if description else None,
        duration_days=30,
        price_minor=price_minor,
        currency=currency,
        is_active=True,
    )
    try:
        db.add(plan)
        db.flush()
        _audit(db, actor, "SUBSCRIPTION_PLAN_CREATED", f"subscription_plan:{plan.id}", after={"code": code, "duration_days": 30, "price_minor": price_minor, "currency": currency})
        _commit_or_rollback(db)
        return plan
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="A plan with that code already exists.") from exc
    except Exception:
        db.rollback()
        raise


def _valid_currency(value: str) -> bool:
    return len(value) == 3 and value.isascii() and value.isalpha() and value.isupper()


def _get_candidate(db: Session, user_id: int, *, lock: bool = False) -> UserAccount:
    query = db.query(UserAccount).filter(UserAccount.id == user_id)
    if lock:
        query = query.with_for_update()
    candidate = query.first()
    if candidate is None:
        _fail(status.HTTP_404_NOT_FOUND, "Candidate account not found.")
    if candidate.role != "candidate":
        _fail(status.HTTP_403_FORBIDDEN, "Subscriptions can only be assigned to candidate accounts.")
    if not candidate.is_active:
        _fail(status.HTTP_403_FORBIDDEN, "Inactive accounts cannot receive subscriptions.")
    return candidate


def _get_plan(db: Session, plan_id: int) -> SubscriptionPlan:
    plan = db.query(SubscriptionPlan).filter(SubscriptionPlan.id == plan_id).with_for_update().first()
    if plan is None or not plan.is_active:
        _fail(status.HTTP_404_NOT_FOUND, "Active subscription plan not found.")
    if plan.duration_days != 30:
        _fail(status.HTTP_409_CONFLICT, "Subscription plans must provide exactly 30 days.")
    if plan.price_minor <= 0 or not _valid_currency(plan.currency):
        _fail(status.HTTP_409_CONFLICT, "The selected plan has invalid pricing metadata.")
    return plan


def _create_pending_term(
    db: Session,
    actor: UserAccount,
    candidate: UserAccount,
    plan: SubscriptionPlan,
    *,
    starts_at: datetime,
    provider: str,
    provider_reference: str,
    amount_minor: int,
    currency: str,
    reason: str,
    renewal_of_id: int | None = None,
) -> Subscription:
    currency = currency.strip().upper()
    if amount_minor != plan.price_minor or currency != plan.currency:
        _fail(status.HTTP_422_UNPROCESSABLE_ENTITY, "Payment amount and currency must match the selected plan.")
    if not _valid_currency(currency):
        _fail(status.HTTP_422_UNPROCESSABLE_ENTITY, "A valid three-letter currency is required.")
    provider = provider.strip().lower()
    provider_reference = provider_reference.strip()
    if not provider or not provider_reference:
        _fail(status.HTTP_422_UNPROCESSABLE_ENTITY, "Payment provider and reference are required.")
    if not reason or not reason.strip():
        _fail(status.HTTP_422_UNPROCESSABLE_ENTITY, "An administrator approval reason is required.")

    start = _as_utc(starts_at)
    end = start + TERM
    subscription = Subscription(
        user_id=candidate.id,
        plan_id=plan.id,
        status="pending",
        starts_at=start,
        ends_at=end,
        plan_code_snapshot=plan.code,
        plan_name_snapshot=plan.name,
        amount_minor_snapshot=plan.price_minor,
        currency_snapshot=plan.currency,
        auto_renew=False,
        renewal_of_id=renewal_of_id,
        approved_by_id=actor.id,
        approved_at=utc_now(),
    )
    db.add(subscription)
    db.flush()
    payment = PaymentVerification(
        subscription_id=subscription.id,
        provider=provider,
        provider_reference=provider_reference,
        amount_minor=amount_minor,
        currency=currency,
        status="pending",
        recorded_by_id=actor.id,
    )
    db.add(payment)
    db.flush()
    _audit(
        db,
        actor,
        "SUBSCRIPTION_ASSIGNED",
        f"subscription:{subscription.id}",
        after={"user_id": candidate.id, "plan_id": plan.id, "starts_at": start.isoformat(), "ends_at": end.isoformat(), "approval_reason": reason.strip()},
    )
    _audit(
        db,
        actor,
        "PAYMENT_RECORDED",
        f"payment_verification:{payment.id}",
        after={"subscription_id": subscription.id, "provider": provider, "amount_minor": amount_minor, "currency": currency, "status": "pending"},
    )
    return subscription


def assign_subscription(
    db: Session,
    actor: UserAccount,
    *,
    user_id: int,
    plan_id: int,
    provider: str,
    provider_reference: str,
    amount_minor: int,
    currency: str,
    reason: str,
) -> Subscription:
    _admin_actor(actor, user_id)
    with _serialize_user_operation(db, user_id):
        try:
            candidate = _get_candidate(db, user_id, lock=True)
            now = utc_now()
            # Protect the no-overlap invariant. A currently running or scheduled
            # term must be renewed through the linked renewal workflow.
            blocking = (
                db.query(Subscription)
                .filter(
                    Subscription.user_id == user_id,
                    Subscription.status.in_({"pending", "active"}),
                    Subscription.suspended_at.is_(None),
                    Subscription.revoked_at.is_(None),
                    Subscription.starts_at < now,
                    Subscription.ends_at > now,
                    ~Subscription.payment_verification.has(
                        PaymentVerification.status.in_(PAYMENT_FAILURE_STATES)
                    ),
                )
                .with_for_update()
                .first()
            )
            scheduled = (
                db.query(Subscription)
                .filter(
                    Subscription.user_id == user_id,
                    Subscription.status.in_({"pending", "active"}),
                    Subscription.suspended_at.is_(None),
                    Subscription.revoked_at.is_(None),
                    Subscription.starts_at >= now,
                    Subscription.ends_at > now,
                    ~Subscription.payment_verification.has(
                        PaymentVerification.status.in_(PAYMENT_FAILURE_STATES)
                    ),
                )
                .with_for_update()
                .first()
            )
            if blocking or scheduled:
                _fail(status.HTTP_409_CONFLICT, "An active or scheduled subscription exists; use the renewal workflow or wait for its term to end.")
            plan = _get_plan(db, plan_id)
            subscription = _create_pending_term(
                db, actor, candidate, plan, starts_at=now, provider=provider,
                provider_reference=provider_reference, amount_minor=amount_minor,
                currency=currency, reason=reason,
            )
            _commit_or_rollback(db)
            return subscription
        except IntegrityError as exc:
            db.rollback()
            raise HTTPException(status_code=409, detail="A conflicting subscription or payment reference already exists.") from exc
        except Exception:
            db.rollback()
            raise


def renew_subscription(
    db: Session,
    actor: UserAccount,
    *,
    subscription_id: int,
    plan_id: int,
    provider: str,
    provider_reference: str,
    amount_minor: int,
    currency: str,
    reason: str,
) -> Subscription:
    _admin_actor(actor)
    try:
        # Read the owner without locking, then lock rows in the same order as
        # assignment/entitlement checks (candidate first, subscription second).
        parent = db.query(Subscription).filter(Subscription.id == subscription_id).first()
        if parent is None:
            _fail(status.HTTP_404_NOT_FOUND, "Subscription not found.")
        _admin_actor(actor, parent.user_id)
        with _serialize_user_operation(db, parent.user_id):
            candidate = _get_candidate(db, parent.user_id, lock=True)
            parent = db.query(Subscription).filter(Subscription.id == subscription_id).with_for_update().first()
            if parent is None:
                _fail(status.HTTP_404_NOT_FOUND, "Subscription not found.")
            if parent.status not in {"active", "expired"} or parent.suspended_at is not None or parent.revoked_at is not None:
                _fail(status.HTTP_409_CONFLICT, "Only a paid, unsuspended, non-revoked term can be renewed.")
            payment = db.query(PaymentVerification).filter(PaymentVerification.subscription_id == parent.id).with_for_update().first()
            if payment is None or payment.status != "verified" or payment.verified_at is None or payment.verified_by_id is None:
                _fail(status.HTTP_409_CONFLICT, "The prior term has no current verified payment.")
            now = utc_now()
            starts_at = _as_utc(parent.ends_at)
            if starts_at < now:
                _fail(status.HTTP_409_CONFLICT, "The prior term has expired; assign a new term instead of renewing it.")
            if starts_at + TERM <= now:
                _fail(status.HTTP_409_CONFLICT, "The scheduled renewal term has already ended.")
            newest = (
                db.query(Subscription)
                .filter(Subscription.user_id == parent.user_id)
                .order_by(Subscription.starts_at.desc(), Subscription.id.desc())
                .with_for_update()
                .first()
            )
            if newest is None or newest.id != parent.id:
                _fail(status.HTTP_409_CONFLICT, "Renewal must be prepared from the candidate's latest term.")
            if db.query(Subscription.id).filter(Subscription.renewal_of_id == parent.id).first():
                _fail(status.HTTP_409_CONFLICT, "A renewal already exists for this subscription.")
            plan = _get_plan(db, plan_id)
            child = _create_pending_term(
                db, actor, candidate, plan, starts_at=starts_at, provider=provider,
                provider_reference=provider_reference, amount_minor=amount_minor,
                currency=currency, reason=reason, renewal_of_id=parent.id,
            )
            _commit_or_rollback(db)
            return child
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="A conflicting renewal or payment reference already exists.") from exc
    except Exception:
        db.rollback()
        raise


def verify_payment(db: Session, actor: UserAccount, subscription_id: int, *, reason: str) -> Subscription:
    _admin_actor(actor)
    if not reason or not reason.strip():
        _fail(status.HTTP_422_UNPROCESSABLE_ENTITY, "A verification note is required.")
    try:
        subscription = db.query(Subscription).filter(Subscription.id == subscription_id).with_for_update().first()
        if subscription is None:
            _fail(status.HTTP_404_NOT_FOUND, "Subscription not found.")
        _admin_actor(actor, subscription.user_id)
        payment = db.query(PaymentVerification).filter(PaymentVerification.subscription_id == subscription.id).with_for_update().first()
        if payment is None:
            _fail(status.HTTP_409_CONFLICT, "A payment record is required before verification.")
        if payment.status != "pending":
            _fail(status.HTTP_409_CONFLICT, "This payment is no longer pending and cannot be verified again.")
        if payment.amount_minor != subscription.amount_minor_snapshot or payment.currency != subscription.currency_snapshot:
            _fail(status.HTTP_409_CONFLICT, "Payment evidence does not match the subscription price snapshot.")
        now = utc_now()
        payment.status = "verified"
        payment.verified_by_id = actor.id
        payment.verified_at = now
        payment.status_changed_by_id = actor.id
        payment.status_changed_at = now
        payment.status_reason = reason.strip()
        before_status = subscription.status
        if subscription.revoked_at is not None or subscription.suspended_at is not None or subscription.status in {"revoked", "suspended", "expired"}:
            _fail(status.HTTP_409_CONFLICT, "Suspended, revoked, or expired subscriptions cannot be activated by payment verification.")
        # An initial term begins when its payment is verified, so the customer
        # receives the full 30 days. A renewal keeps its pre-scheduled boundary.
        if subscription.renewal_of_id is None:
            subscription.starts_at = now
            subscription.ends_at = now + TERM
        if _as_utc(subscription.starts_at) <= now < _as_utc(subscription.ends_at):
            subscription.status = "active"
        _audit(db, actor, "PAYMENT_VERIFIED", f"payment_verification:{payment.id}", before={"status": "pending"}, after={"status": "verified", "verified_at": now.isoformat(), "reason": reason.strip()})
        if subscription.status == "active" and before_status != "active":
            _audit(db, actor, "SUBSCRIPTION_ACTIVATED", f"subscription:{subscription.id}", before={"status": before_status}, after={"status": "active", "starts_at": _as_utc(subscription.starts_at).isoformat(), "ends_at": _as_utc(subscription.ends_at).isoformat()})
        _commit_or_rollback(db)
        return subscription
    except Exception:
        db.rollback()
        raise


PAYMENT_FAILURE_STATES = {"rejected", "disputed", "refunded", "chargeback", "reversed"}


def change_payment_status(
    db: Session,
    actor: UserAccount,
    subscription_id: int,
    *,
    new_status: str,
    reason: str,
) -> PaymentVerification:
    _admin_actor(actor)
    if new_status not in PAYMENT_FAILURE_STATES or not reason or not reason.strip():
        _fail(status.HTTP_422_UNPROCESSABLE_ENTITY, "A supported failure status and reason are required.")
    try:
        subscription = db.query(Subscription).filter(Subscription.id == subscription_id).with_for_update().first()
        if subscription is None:
            _fail(status.HTTP_404_NOT_FOUND, "Subscription not found.")
        payment = db.query(PaymentVerification).filter(PaymentVerification.subscription_id == subscription.id).with_for_update().first()
        if payment is None:
            _fail(status.HTTP_409_CONFLICT, "Payment record not found.")
        allowed = {"pending": {"rejected"}, "verified": {"disputed", "refunded", "chargeback", "reversed"}}
        if new_status not in allowed.get(payment.status, set()):
            _fail(status.HTTP_409_CONFLICT, "This payment status transition is not allowed.")
        old_status = payment.status
        now = utc_now()
        payment.status = new_status
        payment.status_changed_by_id = actor.id
        payment.status_changed_at = now
        payment.status_reason = reason.strip()
        _audit(db, actor, "PAYMENT_STATUS_CHANGED", f"payment_verification:{payment.id}", before={"status": old_status}, after={"status": new_status, "reason": reason.strip(), "changed_at": now.isoformat()})
        _commit_or_rollback(db)
        return payment
    except Exception:
        db.rollback()
        raise


def suspend_subscription(db: Session, actor: UserAccount, subscription_id: int, *, reason: str) -> Subscription:
    _admin_actor(actor)
    if not reason or not reason.strip():
        _fail(status.HTTP_422_UNPROCESSABLE_ENTITY, "A suspension reason is required.")
    try:
        subscription = db.query(Subscription).filter(Subscription.id == subscription_id).with_for_update().first()
        if subscription is None:
            _fail(status.HTTP_404_NOT_FOUND, "Subscription not found.")
        _admin_actor(actor, subscription.user_id)
        if subscription.status not in {"pending", "active"}:
            _fail(status.HTTP_409_CONFLICT, "Only pending or active subscriptions can be suspended.")
        old_status = subscription.status
        now = utc_now()
        subscription.status = "suspended"
        subscription.suspended_at = now
        subscription.suspended_by_id = actor.id
        subscription.suspension_reason = reason.strip()
        _audit(db, actor, "SUBSCRIPTION_SUSPENDED", f"subscription:{subscription.id}", before={"status": old_status}, after={"status": "suspended", "reason": reason.strip(), "suspended_at": now.isoformat()})
        _commit_or_rollback(db)
        return subscription
    except Exception:
        db.rollback()
        raise


def revoke_subscription(db: Session, actor: UserAccount, subscription_id: int, *, reason: str) -> Subscription:
    _admin_actor(actor)
    if not reason or not reason.strip():
        _fail(status.HTTP_422_UNPROCESSABLE_ENTITY, "A revocation reason is required.")
    try:
        subscription = db.query(Subscription).filter(Subscription.id == subscription_id).with_for_update().first()
        if subscription is None:
            _fail(status.HTTP_404_NOT_FOUND, "Subscription not found.")
        _admin_actor(actor, subscription.user_id)
        if subscription.status in {"revoked", "expired"} or subscription.revoked_at is not None:
            _fail(status.HTTP_409_CONFLICT, "This subscription is terminal and cannot be revoked again or reactivated.")
        old_status = subscription.status
        now = utc_now()
        subscription.status = "revoked"
        subscription.revoked_at = now
        subscription.revoked_by_id = actor.id
        subscription.revocation_reason = reason.strip()
        _audit(db, actor, "SUBSCRIPTION_REVOKED", f"subscription:{subscription.id}", before={"status": old_status}, after={"status": "revoked", "reason": reason.strip(), "revoked_at": now.isoformat()})
        _commit_or_rollback(db)
        return subscription
    except Exception:
        db.rollback()
        raise


def ensure_candidate_entitlement(db: Session, candidate: UserAccount) -> Subscription:
    """Require a currently paid candidate entitlement or return HTTP 402."""
    if not candidate or not candidate.is_active:
        _fail(status.HTTP_403_FORBIDDEN, "An active candidate account is required.")
    if candidate.role != "candidate":
        _fail(status.HTTP_403_FORBIDDEN, "Candidate access is required.")
    now = utc_now()
    try:
        locked_candidate = (
            db.query(UserAccount)
            .filter(UserAccount.id == candidate.id)
            .populate_existing()
            .with_for_update()
            .first()
        )
        if locked_candidate is None or not locked_candidate.is_active:
            _fail(status.HTTP_403_FORBIDDEN, "An active candidate account is required.")
        if locked_candidate.role != "candidate":
            _fail(status.HTTP_403_FORBIDDEN, "Candidate access is required.")
        rows = (
            db.query(Subscription)
            .filter(
                Subscription.user_id == candidate.id,
                Subscription.starts_at <= now,
                Subscription.ends_at > now,
            )
            .with_for_update()
            .all()
        )
        eligible: list[Subscription] = []
        for subscription in rows:
            if subscription.status not in {"pending", "active"}:
                continue
            if subscription.revoked_at is not None or subscription.suspended_at is not None:
                continue
            if subscription.approved_by_id is None or subscription.approved_at is None:
                continue
            if _as_utc(subscription.approved_at) > now:
                continue
            if _as_utc(subscription.ends_at) - _as_utc(subscription.starts_at) != TERM:
                continue
            payment = subscription.payment_verification
            if (
                payment is None
                or payment.status != "verified"
                or payment.verified_by_id is None
                or payment.verified_at is None
                or _as_utc(payment.verified_at) > now
                or payment.amount_minor != subscription.amount_minor_snapshot
                or payment.currency != subscription.currency_snapshot
            ):
                continue
            if subscription.status == "pending":
                old_status = subscription.status
                subscription.status = "active"
                _audit(db, None, "SUBSCRIPTION_ACTIVATED", f"subscription:{subscription.id}", before={"status": old_status}, after={"status": "active", "activated_at": now.isoformat(), "reason": "scheduled verified term reached its start"})
            if subscription.status == "active":
                eligible.append(subscription)
        if len(eligible) != 1:
            if eligible:
                db.rollback()
            _fail(status.HTTP_402_PAYMENT_REQUIRED, "An active, administrator-approved subscription with verified payment is required.")
        if db.dirty or db.new:
            _commit_or_rollback(db)
        return eligible[0]
    except HTTPException:
        raise
    except Exception:
        db.rollback()
        raise


def get_candidate_subscription_status(db: Session, candidate: UserAccount) -> dict:
    if not candidate or candidate.role != "candidate":
        _fail(status.HTTP_403_FORBIDDEN, "Candidate access is required.")
    now = utc_now()
    subscription = (
        db.query(Subscription)
        .filter(Subscription.user_id == candidate.id)
        .order_by(Subscription.starts_at.desc(), Subscription.id.desc())
        .first()
    )
    if subscription is None:
        return {"status": "none", "starts_at": None, "ends_at": None, "payment_status": None}
    payment = subscription.payment_verification
    current = (
        candidate.is_active
        and subscription.status == "active"
        and subscription.approved_at is not None
        and subscription.approved_by_id is not None
        and _as_utc(subscription.approved_at) <= now
        and subscription.suspended_at is None
        and subscription.revoked_at is None
        and _as_utc(subscription.starts_at) <= now < _as_utc(subscription.ends_at)
        and payment is not None
        and payment.status == "verified"
        and payment.verified_at is not None
        and payment.verified_by_id is not None
        and _as_utc(payment.verified_at) <= now
        and _as_utc(subscription.ends_at) - _as_utc(subscription.starts_at) == TERM
        and payment.amount_minor == subscription.amount_minor_snapshot
        and payment.currency == subscription.currency_snapshot
    )
    return {
        "status": "active" if current else (payment.status if payment else subscription.status),
        "subscription_status": subscription.status,
        "starts_at": _as_utc(subscription.starts_at).isoformat(),
        "ends_at": _as_utc(subscription.ends_at).isoformat(),
        "payment_status": payment.status if payment else None,
        "has_access": bool(current),
    }
