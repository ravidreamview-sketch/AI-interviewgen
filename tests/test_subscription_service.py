"""Isolated local SQLite coverage for subscription lifecycle rules."""

import os
os.environ["PYTHON_DOTENV_DISABLED"] = "true"

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
import unittest
from datetime import timedelta
from unittest.mock import patch

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import database, subscription_service as service
from app.db_models import Base, UserAccount, Subscription, PaymentVerification


class SubscriptionServiceTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool,
        )
        database.configure_sqlite_foreign_keys(self.engine)
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine, expire_on_commit=False)
        self.db = self.Session()
        self.admin = UserAccount(email="admin@example.invalid", password_hash="hash", role="super_admin", is_active=True)
        self.candidate = UserAccount(email="candidate@example.invalid", password_hash="hash", role="candidate", is_active=True)
        self.other = UserAccount(email="other@example.invalid", password_hash="hash", role="candidate", is_active=True)
        self.db.add_all([self.admin, self.candidate, self.other])
        self.db.commit()
        self.plan = service.create_plan(self.db, self.admin, code="monthly", name="Monthly", price_minor=1000, currency="USD")

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def assign(self, candidate=None, ref="ref-1"):
        return service.assign_subscription(
            self.db, self.admin, user_id=(candidate or self.candidate).id,
            plan_id=self.plan.id, provider="manual", provider_reference=ref,
            amount_minor=1000, currency="USD", reason="Reviewed bank transfer",
        )

    def verify(self, subscription):
        return service.verify_payment(self.db, self.admin, subscription.id, reason="Receipt checked")

    def test_assignment_waits_for_verified_payment_then_grants_full_thirty_days(self):
        subscription = self.assign()
        self.assertEqual(subscription.status, "pending")
        self.assertEqual(subscription.payment_verification.status, "pending")
        self.assertEqual(subscription.ends_at - subscription.starts_at, timedelta(days=30))
        with self.assertRaises(HTTPException) as pending:
            service.ensure_candidate_entitlement(self.db, self.candidate)
        self.assertEqual(pending.exception.status_code, 402)
        self.verify(subscription)
        subscription = self.db.get(Subscription, subscription.id)
        self.assertEqual(subscription.status, "active")
        self.assertEqual(subscription.ends_at - subscription.starts_at, timedelta(days=30))
        self.assertEqual(service.ensure_candidate_entitlement(self.db, self.candidate).id, subscription.id)

    def test_legacy_plan_tier_does_not_grant_access(self):
        self.candidate.plan_tier = "enterprise"
        self.db.commit()
        with self.assertRaises(HTTPException) as raised:
            service.ensure_candidate_entitlement(self.db, self.candidate)
        self.assertEqual(raised.exception.status_code, 402)

    def test_self_approval_is_rejected(self):
        self.admin.role = "candidate"
        self.db.commit()
        with self.assertRaises(HTTPException) as raised:
            service.assign_subscription(self.db, self.admin, user_id=self.admin.id, plan_id=self.plan.id,
                provider="manual", provider_reference="x", amount_minor=1000, currency="USD", reason="x")
        self.assertEqual(raised.exception.status_code, 403)

    def test_payment_reversal_denies_access_and_cannot_be_reverified(self):
        subscription = self.assign()
        self.verify(subscription)
        service.change_payment_status(self.db, self.admin, subscription.id, new_status="refunded", reason="Refund confirmed")
        with self.assertRaises(HTTPException) as denied:
            service.ensure_candidate_entitlement(self.db, self.candidate)
        self.assertEqual(denied.exception.status_code, 402)
        with self.assertRaises(HTTPException):
            self.verify(subscription)

    def test_suspension_and_revocation_never_restore_access(self):
        sub = self.assign(ref="suspend-ref")
        self.verify(sub)
        service.suspend_subscription(self.db, self.admin, sub.id, reason="Review pending")
        with self.assertRaises(HTTPException):
            service.ensure_candidate_entitlement(self.db, self.candidate)
        with self.assertRaises(HTTPException):
            self.verify(sub)

        another = self.assign(self.other, ref="revoke-ref")
        self.verify(another)
        service.revoke_subscription(self.db, self.admin, another.id, reason="Account misuse")
        with self.assertRaises(HTTPException):
            service.ensure_candidate_entitlement(self.db, self.other)
        with self.assertRaises(HTTPException):
            self.verify(another)

    def test_interval_is_half_open_and_account_status_is_reloaded(self):
        sub = self.assign()
        self.verify(sub)
        sub = self.db.get(Subscription, sub.id)
        with patch.object(service, "utc_now", return_value=sub.starts_at):
            self.assertEqual(service.ensure_candidate_entitlement(self.db, self.candidate).id, sub.id)
        with patch.object(service, "utc_now", return_value=sub.ends_at):
            with self.assertRaises(HTTPException) as raised:
                service.ensure_candidate_entitlement(self.db, self.candidate)
        self.assertEqual(raised.exception.status_code, 402)
        self.db.rollback()
        with self.Session() as other_session:
            persisted = other_session.get(UserAccount, self.candidate.id)
            persisted.is_active = False
            other_session.commit()
        with self.assertRaises(HTTPException) as inactive:
            service.ensure_candidate_entitlement(self.db, self.candidate)
        self.assertEqual(inactive.exception.status_code, 403)

    def test_duplicate_payment_reference_rolls_back_subscription_and_audit(self):
        self.assign(ref="duplicate-reference")
        self.db.expire_all()
        with self.assertRaises(HTTPException) as raised:
            self.assign(self.other, ref="duplicate-reference")
        self.assertEqual(raised.exception.status_code, 409)
        self.db.rollback()
        self.assertEqual(self.db.query(Subscription).count(), 1)
        self.assertEqual(self.db.query(PaymentVerification).count(), 1)

    def test_renewal_is_scheduled_at_parent_end_and_duplicate_is_rejected(self):
        parent = self.assign()
        self.verify(parent)
        parent = self.db.get(Subscription, parent.id)
        parent.ends_at = service.utc_now() + timedelta(days=5)
        parent.starts_at = parent.ends_at - timedelta(days=30)
        self.db.commit()
        renewal = service.renew_subscription(
            self.db, self.admin, subscription_id=parent.id, plan_id=self.plan.id,
            provider="manual", provider_reference="renewal-ref", amount_minor=1000,
            currency="USD", reason="Renewal payment pending",
        )
        self.assertEqual(renewal.starts_at, parent.ends_at)
        self.assertEqual(renewal.ends_at - renewal.starts_at, timedelta(days=30))
        self.verify(renewal)
        self.assertEqual(service.ensure_candidate_entitlement(self.db, self.candidate).id, parent.id)
        with patch.object(service, "utc_now", return_value=renewal.starts_at):
            self.assertEqual(service.ensure_candidate_entitlement(self.db, self.candidate).id, renewal.id)
        with self.assertRaises(HTTPException):
            service.renew_subscription(
                self.db, self.admin, subscription_id=parent.id, plan_id=self.plan.id,
                provider="manual", provider_reference="renewal-ref-2", amount_minor=1000,
                currency="USD", reason="Duplicate renewal",
            )

    def test_concurrent_assignments_for_one_candidate_allow_only_one_term(self):
        gate = Barrier(2)

        def attempt(reference):
            with self.Session() as session:
                actor = session.get(UserAccount, self.admin.id)
                target = session.get(UserAccount, self.candidate.id)
                gate.wait(timeout=5)
                try:
                    service.assign_subscription(
                        session, actor, user_id=target.id, plan_id=self.plan.id,
                        provider="manual", provider_reference=reference,
                        amount_minor=1000, currency="USD", reason="Concurrent test",
                    )
                    return "created"
                except HTTPException as exc:
                    if exc.status_code == 409:
                        return "conflict"
                    raise

        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(pool.map(attempt, ["concurrent-a", "concurrent-b"]))
        self.assertCountEqual(outcomes, ["created", "conflict"])
        self.assertEqual(self.db.query(Subscription).count(), 1)


if __name__ == "__main__":
    unittest.main()
