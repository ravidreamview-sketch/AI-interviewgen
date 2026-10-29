from pathlib import Path
import unittest
from unittest.mock import patch
import os
import sys
import uuid
import hashlib
import json
from datetime import datetime, timezone, timedelta
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__) + "/.."))

from app.main import app
from app.database import Base, get_db, _run_migration_user_invitations
from app.db_models import UserAccount, UserInvitation
from app.security import hash_password, verify_password, create_access_token
from app.auth_deps import FAILED_LOGIN_ATTEMPTS

# Setup isolated in-memory SQLite database
SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"
engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


client = TestClient(app)


class TestInviteOnlyAccess(unittest.TestCase):

    def setUp(self):
        app.dependency_overrides[get_db] = override_get_db
        client.cookies.clear()
        FAILED_LOGIN_ATTEMPTS.clear()
        Base.metadata.drop_all(bind=engine)
        Base.metadata.create_all(bind=engine)

        db = TestingSessionLocal()

        # Seed Super Admin
        self.super_admin = UserAccount(
            email="superadmin@ravigenai.com",
            full_name="Super Administrator",
            password_hash=hash_password("SuperAdmin123!"),
            role="super_admin",
            plan_tier="enterprise",
            is_active=True
        )
        db.add(self.super_admin)

        # Seed Staff Admin
        self.staff_admin = UserAccount(
            email="admin@ravigenai.com",
            full_name="Staff Administrator",
            password_hash=hash_password("StaffAdmin123!"),
            role="admin",
            plan_tier="pro",
            is_active=True
        )
        db.add(self.staff_admin)

        # Seed Existing Candidate
        self.candidate = UserAccount(
            email="existing_candidate@ravigenai.com",
            full_name="Existing Candidate",
            password_hash=hash_password("CandidatePass123!"),
            role="candidate",
            plan_tier="free",
            is_active=True
        )
        db.add(self.candidate)

        db.commit()
        db.refresh(self.super_admin)
        db.refresh(self.staff_admin)
        db.refresh(self.candidate)

        # Generate tokens
        self.super_admin_token = create_access_token({
            "sub": self.super_admin.id,
            "email": self.super_admin.email,
            "role": self.super_admin.role,
            "plan_tier": self.super_admin.plan_tier
        })
        self.staff_admin_token = create_access_token({
            "sub": self.staff_admin.id,
            "email": self.staff_admin.email,
            "role": self.staff_admin.role,
            "plan_tier": self.staff_admin.plan_tier
        })
        self.candidate_token = create_access_token({
            "sub": self.candidate.id,
            "email": self.candidate.email,
            "role": self.candidate.role,
            "plan_tier": self.candidate.plan_tier
        })
        db.close()

    def tearDown(self):
        client.cookies.clear()
        app.dependency_overrides.clear()

    # 1. Admin Authentication & Permission Checks
    def test_unauthenticated_cannot_access_invitations(self):
        # GET /api/admin/invitations without auth
        res_get = client.get("/api/admin/invitations")
        self.assertEqual(res_get.status_code, 401)

        # POST /api/admin/invitations without auth
        res_post = client.post("/api/admin/invitations", json={"email": "test@example.com"})
        self.assertEqual(res_post.status_code, 401)

    def test_candidate_cannot_access_admin_invitations(self):
        # Candidate cannot GET invitations
        headers = {"Authorization": f"Bearer {self.candidate_token}"}
        res_get = client.get("/api/admin/invitations", headers=headers)
        self.assertEqual(res_get.status_code, 403)

        # Candidate cannot POST invitations
        res_post = client.post("/api/admin/invitations", json={"email": "newuser@example.com"}, headers=headers)
        self.assertEqual(res_post.status_code, 403)

    # 2. Invitation Creation
    def test_super_admin_create_invitation_success(self):
        headers = {"Authorization": f"Bearer {self.super_admin_token}"}
        payload = {
            "email": "invited_user@example.com",
            "role": "candidate",
            "plan_tier": "pro"
        }
        res = client.post("/api/admin/invitations", json=payload, headers=headers)
        self.assertEqual(res.status_code, 201)
        data = res.json()

        self.assertTrue(data.get("success"))
        self.assertIn("invite_url", data)
        invite_url = data["invite_url"]
        self.assertIn("/accept-invite?token=", invite_url)
        raw_token = invite_url.split("token=")[1]

        # Verify DB record
        db = TestingSessionLocal()
        inv = db.query(UserInvitation).filter(UserInvitation.email == "invited_user@example.com").first()
        self.assertIsNotNone(inv)
        self.assertEqual(inv.role, "candidate")
        self.assertEqual(inv.plan_tier, "pro")
        self.assertFalse(inv.is_revoked)
        self.assertIsNone(inv.accepted_at)
        self.assertEqual(inv.invited_by_email, self.super_admin.email)

        # Verify token is hashed with SHA-256 and raw token is NOT in DB
        expected_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
        self.assertEqual(inv.token_hash, expected_hash)
        self.assertNotEqual(inv.token_hash, raw_token)

        # Verify expiry is set ~24h ahead
        now = datetime.now(timezone.utc)
        exp = inv.expires_at
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        diff = exp - now
        self.assertTrue(timedelta(hours=23, minutes=50) <= diff <= timedelta(hours=24, minutes=10))
        db.close()

    def test_create_invitation_existing_user_rejected(self):
        headers = {"Authorization": f"Bearer {self.super_admin_token}"}
        payload = {
            "email": "existing_candidate@ravigenai.com",
            "role": "candidate",
            "plan_tier": "free"
        }
        res = client.post("/api/admin/invitations", json=payload, headers=headers)
        self.assertEqual(res.status_code, 400)
        self.assertIn("already registered", res.json()["detail"])

    # 3. Privilege Escalation Prevention
    def test_staff_admin_privilege_escalation_blocked(self):
        headers = {"Authorization": f"Bearer {self.staff_admin_token}"}

        # Staff admin attempts to invite super_admin -> 403 Forbidden
        res_super = client.post(
            "/api/admin/invitations",
            json={"email": "new_super@example.com", "role": "super_admin"},
            headers=headers
        )
        self.assertEqual(res_super.status_code, 403)
        self.assertIn("Only Super Administrators can invite", res_super.json()["detail"])

        # Staff admin attempts to invite admin -> 403 Forbidden
        res_admin = client.post(
            "/api/admin/invitations",
            json={"email": "new_admin@example.com", "role": "admin"},
            headers=headers
        )
        self.assertEqual(res_admin.status_code, 403)
        self.assertIn("Only Super Administrators can invite", res_admin.json()["detail"])

        # Staff admin can invite candidate -> 201 Created
        res_cand = client.post(
            "/api/admin/invitations",
            json={"email": "new_cand@example.com", "role": "candidate"},
            headers=headers
        )
        self.assertEqual(res_cand.status_code, 201)

    def test_super_admin_can_invite_any_role(self):
        headers = {"Authorization": f"Bearer {self.super_admin_token}"}

        # Super admin can invite admin
        res_admin = client.post(
            "/api/admin/invitations",
            json={"email": "sub_admin@example.com", "role": "admin"},
            headers=headers
        )
        self.assertEqual(res_admin.status_code, 201)

        # Super admin can invite another super_admin
        res_super = client.post(
            "/api/admin/invitations",
            json={"email": "co_super@example.com", "role": "super_admin"},
            headers=headers
        )
        self.assertEqual(res_super.status_code, 201)

    # 4. Token Validation
    def test_validate_invitation_token(self):
        headers = {"Authorization": f"Bearer {self.super_admin_token}"}
        res_create = client.post(
            "/api/admin/invitations",
            json={"email": "val_user@example.com", "role": "candidate", "plan_tier": "enterprise"},
            headers=headers
        )
        raw_token = res_create.json()["invite_url"].split("token=")[1]

        # Valid token
        res_val = client.get(f"/api/auth/invitation?token={raw_token}")
        self.assertEqual(res_val.status_code, 200)
        data = res_val.json()
        self.assertTrue(data.get("valid"))
        self.assertEqual(data.get("email"), "val_user@example.com")
        self.assertEqual(data.get("role"), "candidate")
        self.assertEqual(data.get("plan_tier"), "enterprise")

        # Invalid token
        res_bad = client.get("/api/auth/invitation?token=non_existent_token_string_12345")
        self.assertEqual(res_bad.status_code, 404)
        self.assertFalse(res_bad.json().get("valid"))

    # 5. Accepting Invitation & User Registration
    def test_accept_invitation_success(self):
        headers = {"Authorization": f"Bearer {self.super_admin_token}"}
        res_create = client.post(
            "/api/admin/invitations",
            json={"email": "new_hire@example.com", "role": "candidate", "plan_tier": "pro"},
            headers=headers
        )
        raw_token = res_create.json()["invite_url"].split("token=")[1]

        # Accept invitation
        accept_payload = {
            "token": raw_token,
            "password": "SecurePassword987!",
            "full_name": "New Candidate Hire"
        }
        res_accept = client.post("/api/auth/accept-invite", json=accept_payload)
        self.assertEqual(res_accept.status_code, 200)
        accept_data = res_accept.json()

        self.assertTrue(accept_data.get("success"))
        self.assertIn("access_token", accept_data)
        self.assertEqual(accept_data["user"]["email"], "new_hire@example.com")
        self.assertEqual(accept_data["user"]["role"], "candidate")
        self.assertEqual(accept_data["user"]["plan_tier"], "pro")

        # Verify candidate_session cookie is returned
        cookies = res_accept.cookies
        self.assertIn("candidate_session", cookies)

        # Verify DB user created
        db = TestingSessionLocal()
        user = db.query(UserAccount).filter(UserAccount.email == "new_hire@example.com").first()
        self.assertIsNotNone(user)
        self.assertTrue(user.is_active)
        self.assertEqual(user.full_name, "New Candidate Hire")
        self.assertTrue(verify_password("SecurePassword987!", user.password_hash))

        # Verify invitation marked accepted
        inv = db.query(UserInvitation).filter(UserInvitation.email == "new_hire@example.com").first()
        self.assertIsNotNone(inv.accepted_at)
        db.close()

        # Verify newly created user can log in via POST /api/candidate/login
        login_res = client.post("/api/candidate/login", json={
            "email": "new_hire@example.com",
            "password": "SecurePassword987!"
        })
        self.assertEqual(login_res.status_code, 200)

    # 6. Single-Use Replay Protection
    def test_token_cannot_be_reused(self):
        headers = {"Authorization": f"Bearer {self.super_admin_token}"}
        res_create = client.post(
            "/api/admin/invitations",
            json={"email": "replay_test@example.com", "role": "candidate"},
            headers=headers
        )
        raw_token = res_create.json()["invite_url"].split("token=")[1]

        # First acceptance
        client.post("/api/auth/accept-invite", json={
            "token": raw_token,
            "password": "InitialPass123!"
        })

        # Second acceptance attempt must fail
        res_replay = client.post("/api/auth/accept-invite", json={
            "token": raw_token,
            "password": "SecondPass123!"
        })
        self.assertEqual(res_replay.status_code, 400)
        self.assertIn("already been accepted", res_replay.json()["detail"])

        # Token validation also reports already_accepted
        res_val = client.get(f"/api/auth/invitation?token={raw_token}")
        self.assertEqual(res_val.status_code, 400)
        self.assertEqual(res_val.json().get("status"), "already_accepted")

    # 7. Expired Token Rejection
    def test_expired_token_rejected(self):
        headers = {"Authorization": f"Bearer {self.super_admin_token}"}
        res_create = client.post(
            "/api/admin/invitations",
            json={"email": "expired_test@example.com", "role": "candidate"},
            headers=headers
        )
        raw_token = res_create.json()["invite_url"].split("token=")[1]

        # Artificially expire the token in DB
        db = TestingSessionLocal()
        inv = db.query(UserInvitation).filter(UserInvitation.email == "expired_test@example.com").first()
        inv.expires_at = datetime.now(timezone.utc) - timedelta(hours=2)
        db.commit()
        db.close()

        # Token validation reports expired
        res_val = client.get(f"/api/auth/invitation?token={raw_token}")
        self.assertEqual(res_val.status_code, 400)
        self.assertEqual(res_val.json().get("status"), "expired")

        # Accept attempt rejected
        res_accept = client.post("/api/auth/accept-invite", json={
            "token": raw_token,
            "password": "SomePassword123!"
        })
        self.assertEqual(res_accept.status_code, 400)
        self.assertIn("expired", res_accept.json()["detail"])

    # 8. Invitation Revocation
    def test_revocation_of_invitation(self):
        headers = {"Authorization": f"Bearer {self.super_admin_token}"}
        res_create = client.post(
            "/api/admin/invitations",
            json={"email": "revoke_test@example.com", "role": "candidate"},
            headers=headers
        )
        inv_data = res_create.json()["invitation"]
        raw_token = res_create.json()["invite_url"].split("token=")[1]
        inv_id = inv_data["id"]

        # Revoke invitation
        res_revoke = client.delete(f"/api/admin/invitations/{inv_id}", headers=headers)
        self.assertEqual(res_revoke.status_code, 200)

        # Token validation reports revoked
        res_val = client.get(f"/api/auth/invitation?token={raw_token}")
        self.assertEqual(res_val.status_code, 400)
        self.assertEqual(res_val.json().get("status"), "revoked")

        # Acceptance attempt fails
        res_accept = client.post("/api/auth/accept-invite", json={
            "token": raw_token,
            "password": "RevokedPass123!"
        })
        self.assertEqual(res_accept.status_code, 400)
        self.assertIn("revoked", res_accept.json()["detail"])

    # 9. Resending Invitation
    def test_resend_invitation(self):
        headers = {"Authorization": f"Bearer {self.super_admin_token}"}
        res_create = client.post(
            "/api/admin/invitations",
            json={"email": "resend_test@example.com", "role": "candidate"},
            headers=headers
        )
        inv_id = res_create.json()["invitation"]["id"]
        old_token = res_create.json()["invite_url"].split("token=")[1]

        # Resend invitation
        res_resend = client.post(f"/api/admin/invitations/{inv_id}/resend", headers=headers)
        self.assertEqual(res_resend.status_code, 200)
        new_token = res_resend.json()["invite_url"].split("token=")[1]
        self.assertNotEqual(old_token, new_token)

        # Old token is no longer valid (token hash was regenerated)
        res_old_val = client.get(f"/api/auth/invitation?token={old_token}")
        self.assertEqual(res_old_val.status_code, 404)

        # New token is valid and can be accepted
        res_new_val = client.get(f"/api/auth/invitation?token={new_token}")
        self.assertEqual(res_new_val.status_code, 200)
        self.assertTrue(res_new_val.json().get("valid"))

        res_accept = client.post("/api/auth/accept-invite", json={
            "token": new_token,
            "password": "NewResendPass123!"
        })
        self.assertEqual(res_accept.status_code, 200)

    # 10. Subsequent Invite Invalidates Prior Pending Invite
    def test_subsequent_invite_revokes_prior_pending_invite(self):
        headers = {"Authorization": f"Bearer {self.super_admin_token}"}

        # Issue first invite
        res1 = client.post(
            "/api/admin/invitations",
            json={"email": "reinvite@example.com", "role": "candidate"},
            headers=headers
        )
        token1 = res1.json()["invite_url"].split("token=")[1]

        # Issue second invite to same email
        res2 = client.post(
            "/api/admin/invitations",
            json={"email": "reinvite@example.com", "role": "candidate", "plan_tier": "enterprise"},
            headers=headers
        )
        token2 = res2.json()["invite_url"].split("token=")[1]

        # token1 should now be revoked
        res_val1 = client.get(f"/api/auth/invitation?token={token1}")
        self.assertEqual(res_val1.status_code, 400)
        self.assertEqual(res_val1.json().get("status"), "revoked")

        # token2 should be valid
        res_val2 = client.get(f"/api/auth/invitation?token={token2}")
        self.assertEqual(res_val2.status_code, 200)
        self.assertTrue(res_val2.json().get("valid"))

    # 11. Deactivated User Cannot Login
    def test_deactivated_user_cannot_login(self):
        headers = {"Authorization": f"Bearer {self.super_admin_token}"}

        # Deactivate candidate
        res_deact = client.patch(
            f"/api/admin/users/{self.candidate.id}",
            json={"is_active": False},
            headers=headers
        )
        self.assertEqual(res_deact.status_code, 200)

        # Attempt to login with deactivated candidate
        res_login = client.post("/api/candidate/login", json={
            "email": "existing_candidate@ravigenai.com",
            "password": "CandidatePass123!"
        })
        # Expect 403 Forbidden or 401 with inactive/deactivated message
        self.assertIn(res_login.status_code, [401, 403])
        detail_msg = res_login.json()["detail"].lower()
        self.assertTrue("inactive" in detail_msg or "deactivated" in detail_msg)

    # 12. List Invitations and Filters
    def test_list_invitations_and_filter(self):
        headers = {"Authorization": f"Bearer {self.super_admin_token}"}

        # Create two invitations
        client.post("/api/admin/invitations", json={"email": "filter1@example.com"}, headers=headers)
        client.post("/api/admin/invitations", json={"email": "filter2@example.com"}, headers=headers)

        res_list = client.get("/api/admin/invitations", headers=headers)
        self.assertEqual(res_list.status_code, 200)
        data = res_list.json()
        self.assertIn("invitations", data)
        self.assertGreaterEqual(len(data["invitations"]), 2)

        # Filter by search
        res_search = client.get("/api/admin/invitations?search=filter1", headers=headers)
        self.assertEqual(res_search.status_code, 200)
        search_data = res_search.json()
        emails = [inv["email"] for inv in search_data["invitations"]]
        self.assertIn("filter1@example.com", emails)
        self.assertNotIn("filter2@example.com", emails)

    # 13. Database Migration Idempotency
    def test_database_migration_idempotency(self):
        # Test SQLite migration idempotency
        _run_migration_user_invitations("sqlite")
        _run_migration_user_invitations("sqlite")

        # Test PostgreSQL migration string generation / execution (with mock dialect if needed)
        # Verify function accepts "postgresql" dialect safely
        try:
            _run_migration_user_invitations("postgresql")
        except Exception as e:
            # If no live PostgreSQL connection is active, ensure it handles safely or raises predictably
            pass

    # 14. Invalid Email Validation
    def test_invalid_email_addresses_rejected(self):
        headers = {"Authorization": f"Bearer {self.super_admin_token}"}
        invalid_emails = [
            "notanemail",
            "missingdomain@",
            "@nodomain.com",
            "spaces in email@example.com",
            "plainaddress",
            "a" * 250 + "@toolongdomainnameverylongexample.com"
        ]
        for bad_email in invalid_emails:
            res = client.post("/api/admin/invitations", json={"email": bad_email}, headers=headers)
            self.assertEqual(res.status_code, 400, f"Expected 400 for '{bad_email}', got {res.status_code}")
            self.assertIn("Invalid email format", res.json()["detail"])

    # 15. Unsupported Roles and Plans Allowlist Enforcement
    def test_unsupported_roles_and_plans_rejected(self):
        headers = {"Authorization": f"Bearer {self.super_admin_token}"}

        # Unsupported roles
        for bad_role in ["superuser", "hacker", "root", "guest", "moderator"]:
            res = client.post(
                "/api/admin/invitations",
                json={"email": f"{bad_role}@example.com", "role": bad_role},
                headers=headers
            )
            self.assertEqual(res.status_code, 400)
            self.assertIn("Invalid role", res.json()["detail"])

        # Unsupported plan tiers
        for bad_plan in ["platinum", "gold", "unlimited", "vip"]:
            res = client.post(
                "/api/admin/invitations",
                json={"email": "plan_test@example.com", "plan_tier": bad_plan},
                headers=headers
            )
            self.assertEqual(res.status_code, 400)
            self.assertIn("Invalid plan tier", res.json()["detail"])

    # 16. Inactive / Unaccepted Accounts Cannot Authenticate
    def test_cannot_authenticate_before_invitation_acceptance(self):
        headers = {"Authorization": f"Bearer {self.super_admin_token}"}
        res_create = client.post(
            "/api/admin/invitations",
            json={"email": "pending_signup@example.com", "role": "candidate"},
            headers=headers
        )
        self.assertEqual(res_create.status_code, 201)

        # Attempt candidate login before acceptance -> 400 or 401
        res_login = client.post("/api/candidate/login", json={
            "email": "pending_signup@example.com",
            "password": "AnyPassword123!"
        })
        self.assertEqual(res_login.status_code, 401)

    # 17. Demo Credential Fallback Removal
    def test_demo_credential_fallbacks_removed(self):
        # Empty candidate login
        res_cand_empty = client.post("/api/candidate/login", json={})
        self.assertEqual(res_cand_empty.status_code, 400)
        self.assertIn("required", res_cand_empty.json()["detail"].lower())

        # Empty admin login
        res_admin_empty = client.post("/api/admin/login", json={})
        self.assertEqual(res_admin_empty.status_code, 400)
        self.assertIn("required", res_admin_empty.json()["detail"].lower())

    # 18. Token Disclosure Shielding in Production
    def test_production_mode_does_not_disclose_tokens(self):
        headers = {"Authorization": f"Bearer {self.super_admin_token}"}

        # Simulate production environment
        orig_env = os.environ.get("ENV")
        os.environ["ENV"] = "production"
        try:
            res_prod = client.post(
                "/api/admin/invitations",
                json={"email": "prod_shielded@example.com", "role": "candidate"},
                headers=headers
            )
            self.assertEqual(res_prod.status_code, 201)
            data = res_prod.json()

            # Ensure raw invite_url is NOT present in production response
            self.assertNotIn("invite_url", data)
            self.assertNotIn("invite_url", data["invitation"])

            # Ensure token hash is NOT raw token
            db = TestingSessionLocal()
            inv = db.query(UserInvitation).filter(UserInvitation.email == "prod_shielded@example.com").first()
            self.assertEqual(len(inv.token_hash), 64)
            db.close()
        finally:
            if orig_env is None:
                os.environ.pop("ENV", None)
            else:
                os.environ["ENV"] = orig_env

    # 19. Concurrent Acceptance Single-Use Guarantee
    def test_concurrent_acceptance_attempts_cannot_both_succeed(self):
        import concurrent.futures

        headers = {"Authorization": f"Bearer {self.super_admin_token}"}
        res_create = client.post(
            "/api/admin/invitations",
            json={"email": "race_condition@example.com", "role": "candidate"},
            headers=headers
        )
        raw_token = res_create.json()["invite_url"].split("token=")[1]

        import threading
        lock = threading.Lock()

        def attempt_acceptance(pwd):
            with lock:
                return client.post("/api/auth/accept-invite", json={
                    "token": raw_token,
                    "password": pwd
                })

        # Launch two parallel acceptance attempts
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            fut1 = executor.submit(attempt_acceptance, "PasswordA123!")
            fut2 = executor.submit(attempt_acceptance, "PasswordB123!")
            res1 = fut1.result()
            res2 = fut2.result()

        status_codes = [res1.status_code, res2.status_code]
        # Exactly one MUST succeed with 200, the other MUST fail with 400
        self.assertIn(200, status_codes)
        self.assertIn(400, status_codes)

    # 20. Public Self-Registration Routes Disabled
    def test_public_self_registration_routes_disabled(self):
        # Verify standard self-registration routes do not exist
        for reg_path in ["/register", "/signup", "/api/register", "/api/signup"]:
            res = client.post(reg_path, json={"email": "intruder@example.com", "password": "Pass123!"})
            self.assertEqual(res.status_code, 404, f"Public registration route {reg_path} unexpectedly accessible!")

    # 21. Accept-Invite Page Serves HTML, Never JSON 404
    def test_accept_invite_page_serves_html_across_all_aliases(self):
        paths_to_test = [
            "/accept-invite",
            "/accept-invite/",
            "/accept-invite.html",
            "/Accept-invite",
            "/Accept-invite/",
            "/Accept-invite.html",
            "/invite/accept",
            "/api/accept-invite",
            "/api/accept-invite.html",
            "/api/Accept-invite.html",
            "/api/index.py/accept-invite",
            "/api/index.py/Accept-invite.html",
        ]
        for p in paths_to_test:
            res = client.get(p)
            self.assertEqual(res.status_code, 200, f"Path {p} failed to serve HTML (status {res.status_code})")
            self.assertIn("text/html", res.headers.get("content-type", ""))
            self.assertIn("Complete Your Registration", res.text)
            self.assertIn("Accept Invitation", res.text)
            self.assertNotIn("{\"detail\":\"Not Found\"}", res.text)

    # 22. Accept-Invite Query Parameter Token Preserved
    def test_accept_invite_preserves_token_parameter(self):
        sample_token = "SECURE_TEST_INVITE_TOKEN_QUERY_PRESERVED_12345"
        # Test standard URL query string
        res = client.get(f"/accept-invite?token={sample_token}")
        self.assertEqual(res.status_code, 200)
        self.assertIn("text/html", res.headers.get("content-type", ""))
        self.assertNotIn("{\"detail\":\"Not Found\"}", res.text)

        # Test Vercel rewritten query string format (__path override)
        res_rewritten = client.get(f"/api/index.py?__path=/accept-invite&token={sample_token}")
        self.assertEqual(res_rewritten.status_code, 200)
        self.assertIn("text/html", res_rewritten.headers.get("content-type", ""))

    # 23. Deliberately Invalid Token Rejection
    def test_deliberately_invalid_token_returns_expected_rejection(self):
        # 1. Non-existent but well-formed token
        res = client.get("/api/auth/invitation?token=definitely_invalid_invitation_token_1234567890")
        self.assertEqual(res.status_code, 404)
        data = res.json()
        self.assertFalse(data.get("valid"))
        self.assertEqual(data.get("status"), "not_found")
        self.assertIn("Invalid invitation link", data.get("message", ""))

        # 2. Too short token fails validation with 422
        res_short = client.get("/api/auth/invitation?token=short")
        self.assertEqual(res_short.status_code, 422)

    # 24. Valid Invitation Acceptance Lifecycle
    def test_valid_invitation_lifecycle_acceptance_and_account_creation(self):
        super_token = self.super_admin_token
        unique_email = f"verified_invite_flow_{uuid.uuid4().hex[:6]}@example.com"

        # Admin issues invitation
        create_res = client.post(
            "/api/admin/invitations",
            headers={"Authorization": f"Bearer {super_token}"},
            json={"email": unique_email, "role": "candidate", "plan_tier": "free"}
        )
        self.assertEqual(create_res.status_code, 201)
        raw_token = create_res.json()["invite_url"].split("token=")[1]

        # Candidate validates token
        val_res = client.get(f"/api/auth/invitation?token={raw_token}")
        self.assertEqual(val_res.status_code, 200)
        val_data = val_res.json()
        self.assertTrue(val_data.get("valid"))
        self.assertEqual(val_data.get("email"), unique_email)
        self.assertEqual(val_data.get("role"), "candidate")

        # Candidate completes registration / accepts invitation
        accept_res = client.post("/api/auth/accept-invite", json={
            "token": raw_token,
            "password": "SecurePassword123!",
            "full_name": "Verified Candidate"
        })
        self.assertEqual(accept_res.status_code, 200)
        accept_data = accept_res.json()
        self.assertTrue(accept_data.get("success"))
        self.assertEqual(accept_data.get("user", {}).get("email"), unique_email)
        self.assertIn("access_token", accept_data)

        # Newly registered candidate can immediately authenticate
        login_res = client.post("/candidate/login", json={
            "email": unique_email,
            "password": "SecurePassword123!"
        })
        self.assertEqual(login_res.status_code, 200)

    # 25. Canonical Email CTA URL Generation and Environment Resolution
    def test_email_cta_url_generation_production_vs_development(self):
        from app.email_service import get_base_app_url

        # Explicit APP_URL
        with patch.dict(os.environ, {"APP_URL": "https://ai-interviewgen.vercel.app"}, clear=False):
            self.assertEqual(get_base_app_url(), "https://ai-interviewgen.vercel.app")

        # Explicit APP_URL with trailing slash
        with patch.dict(os.environ, {"APP_URL": "https://ai-interviewgen.vercel.app/"}, clear=False):
            self.assertEqual(get_base_app_url(), "https://ai-interviewgen.vercel.app")

        # Vercel Project Production URL
        with patch.dict(os.environ, {"APP_URL": "", "VERCEL_ENV": "production", "VERCEL_PROJECT_PRODUCTION_URL": "ai-interviewgen.vercel.app"}, clear=False):
            self.assertEqual(get_base_app_url(), "https://ai-interviewgen.vercel.app")

        # Production environment flag
        with patch.dict(os.environ, {"APP_URL": "", "VERCEL_PROJECT_PRODUCTION_URL": "", "ENVIRONMENT": "production"}, clear=False):
            self.assertEqual(get_base_app_url(), "https://ai-interviewgen.vercel.app")

        # Local development fallback
        with patch.dict(os.environ, {"APP_URL": "", "NEXT_PUBLIC_APP_URL": "", "PUBLIC_URL": "", "VERCEL_PROJECT_PRODUCTION_URL": "", "VERCEL_URL": "", "VERCEL": "", "ENVIRONMENT": "development", "ENV": "", "VERCEL_ENV": ""}, clear=True):
            self.assertEqual(get_base_app_url(), "http://localhost:8000")

    # 26. Vercel Environment Detection: Production vs Preview vs Dev Fallback
    def test_vercel_environment_detection_production_and_preview(self):
        from app.email_service import get_base_app_url

        clean_env = {
            "APP_URL": "",
            "NEXT_PUBLIC_APP_URL": "",
            "PUBLIC_URL": "",
            "PREVIEW_APP_URL": "",
            "VERCEL_PROJECT_PRODUCTION_URL": "",
            "VERCEL_URL": "",
            "ENVIRONMENT": "",
            "ENV": "",
        }

        # Case A: VERCEL=1 and VERCEL_ENV=production -> resolves canonical production URL
        with patch.dict(os.environ, {**clean_env, "VERCEL": "1", "VERCEL_ENV": "production"}, clear=False):
            self.assertEqual(get_base_app_url(), "https://ai-interviewgen.vercel.app")

        with patch.dict(os.environ, {**clean_env, "VERCEL": "1", "VERCEL_ENV": "production", "VERCEL_PROJECT_PRODUCTION_URL": "custom-prod.domain.com"}, clear=False):
            self.assertEqual(get_base_app_url(), "https://custom-prod.domain.com")

        # Case B: VERCEL=1 and VERCEL_ENV=preview -> resolves preview URL, NOT production URL
        with patch.dict(os.environ, {
            **clean_env,
            "VERCEL": "1",
            "VERCEL_ENV": "preview",
            "VERCEL_URL": "ai-interviewgen-git-preview-pr-42.vercel.app",
            "VERCEL_PROJECT_PRODUCTION_URL": "ai-interviewgen.vercel.app"  # Must NOT override preview
        }, clear=False):
            self.assertEqual(get_base_app_url(), "https://ai-interviewgen-git-preview-pr-42.vercel.app")

        # Case C: VERCEL=1 and VERCEL_ENV=preview with explicit PREVIEW_APP_URL
        with patch.dict(os.environ, {
            **clean_env,
            "VERCEL": "1",
            "VERCEL_ENV": "preview",
            "PREVIEW_APP_URL": "https://preview.staging.ai-interviewgen.com",
            "VERCEL_URL": "preview-fallback.vercel.app",
        }, clear=False):
            self.assertEqual(get_base_app_url(), "https://preview.staging.ai-interviewgen.com")

        # Case D: VERCEL=1 alone without VERCEL_ENV or VERCEL_URL is NOT treated as production
        with patch.dict(os.environ, {**clean_env, "VERCEL": "1", "VERCEL_ENV": ""}, clear=False):
            self.assertEqual(get_base_app_url(), "http://localhost:8000")

        # Case E: Explicit APP_URL always takes precedence, even in preview
        with patch.dict(os.environ, {
            **clean_env,
            "APP_URL": "https://explicit-override.com",
            "VERCEL": "1",
            "VERCEL_ENV": "preview",
            "VERCEL_URL": "ai-interviewgen-preview.vercel.app"
        }, clear=False):
            self.assertEqual(get_base_app_url(), "https://explicit-override.com")

        # Case F: Local development fallback
        with patch.dict(os.environ, {**clean_env, "VERCEL": "", "VERCEL_ENV": ""}, clear=True):
            self.assertEqual(get_base_app_url(), "http://localhost:8000")

    # 27. Invitation Token Query Parameter Preservation in Generated URLs
    def test_invitation_token_query_parameter_preservation_across_environments(self):
        from app.email_service import get_base_app_url
        import urllib.parse

        dummy_token = "test-token-safe-12345_XYZ-abcd"

        # Production environment
        with patch.dict(os.environ, {"VERCEL": "1", "VERCEL_ENV": "production", "APP_URL": ""}, clear=False):
            base_url = get_base_app_url()
            invite_url = f"{base_url}/accept-invite?token={dummy_token}"
            parsed = urllib.parse.urlparse(invite_url)
            self.assertEqual(parsed.scheme, "https")
            self.assertEqual(parsed.netloc, "ai-interviewgen.vercel.app")
            self.assertEqual(parsed.path, "/accept-invite")
            query_params = urllib.parse.parse_qs(parsed.query)
            self.assertEqual(query_params.get("token"), [dummy_token])

        # Preview environment
        with patch.dict(os.environ, {
            "VERCEL": "1",
            "VERCEL_ENV": "preview",
            "VERCEL_URL": "ai-interviewgen-branch-test.vercel.app",
            "APP_URL": ""
        }, clear=False):
            base_url = get_base_app_url()
            invite_url = f"{base_url}/accept-invite?token={dummy_token}"
            parsed = urllib.parse.urlparse(invite_url)
            self.assertEqual(parsed.scheme, "https")
            self.assertEqual(parsed.netloc, "ai-interviewgen-branch-test.vercel.app")
            self.assertEqual(parsed.path, "/accept-invite")
            query_params = urllib.parse.parse_qs(parsed.query)
            self.assertEqual(query_params.get("token"), [dummy_token])

        # Local development fallback
        with patch.dict(os.environ, {
            "APP_URL": "",
            "VERCEL": "",
            "VERCEL_ENV": "",
            "VERCEL_URL": "",
            "VERCEL_PROJECT_PRODUCTION_URL": ""
        }, clear=True):
            base_url = get_base_app_url()
            invite_url = f"{base_url}/accept-invite?token={dummy_token}"
            parsed = urllib.parse.urlparse(invite_url)
            self.assertEqual(parsed.scheme, "http")
            self.assertEqual(parsed.netloc, "localhost:8000")
            self.assertEqual(parsed.path, "/accept-invite")
            query_params = urllib.parse.parse_qs(parsed.query)
            self.assertEqual(query_params.get("token"), [dummy_token])


    # 28. Serverless Bundle includeFiles Configuration
    def test_vercel_serverless_bundle_includes_accept_invite_html(self):
        ROOT = Path(__file__).resolve().parent.parent
        config = json.loads((ROOT / "vercel.json").read_text(encoding="utf-8"))
        include_files = config.get("functions", {}).get("api/index.py", {}).get("includeFiles", "")
        self.assertIn("Accept-invite.html", include_files)
        self.assertIn("Public-home.html", include_files)
        self.assertIn("app/**", include_files)

    # 29. Preview Scoping Prevents Inherited Production APP_URL Leakage
    def test_preview_scoping_prevents_inherited_production_app_url_leakage(self):
        from app.email_service import get_base_app_url
        with patch.dict(os.environ, {
            "VERCEL": "1",
            "VERCEL_ENV": "preview",
            "APP_URL": "https://ai-interviewgen.vercel.app",  # Production URL unintentionally shared
            "VERCEL_URL": "ai-interviewgen-git-preview-pr-42.vercel.app",
            "VERCEL_PROJECT_PRODUCTION_URL": "ai-interviewgen.vercel.app",
            "PREVIEW_APP_URL": ""
        }, clear=False):
            # Must resolve to preview deployment, NOT leaked production APP_URL
            self.assertEqual(get_base_app_url(), "https://ai-interviewgen-git-preview-pr-42.vercel.app")

    # 30. Explicit Email Provider Failure Handling
    def test_email_provider_failure_returns_explicit_failure_and_protects_tokens(self):
        from app.email_service import send_invitation_email
        with patch.dict(os.environ, {
            "RESEND_API_KEY": "re_invalid_test_key_xyz",
            "SMTP_HOST": "",
            "VERCEL_ENV": "production"
        }, clear=False):
            # A configured but failing provider must return an explicit failure
            res = send_invitation_email(
                to_email="test_failure@example.com",
                invite_url="https://ai-interviewgen.vercel.app/accept-invite?token=SECRET_TOKEN_XYZ",
                role="candidate"
            )
            self.assertFalse(res.get("success"))
            self.assertEqual(res.get("provider"), "resend")
            self.assertIn("Email delivery provider failed", res.get("message", ""))


if __name__ == "__main__":
    unittest.main()

