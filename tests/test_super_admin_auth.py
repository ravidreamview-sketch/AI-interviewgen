"""
Automated Verification Suite for Super Admin Authentication & One-Time Provisioning
Covers:
1. One-time setup provisioning when no Super Admin exists
2. Permanent lockout of setup once Super Admin exists (403)
3. Valid Super Admin login (200 + token + HttpOnly cookie)
4. Invalid password rejection (401)
5. Unknown email rejection (401)
6. Admin dashboard / /api/admin/me access (200 with role and permissions)
7. Session persistence via admin_session cookie across subsequent requests
8. Admin logout functionality (clears cookie)
9. Unauthorized candidate access rejection on admin routes (403)
"""

import unittest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import app
from app.database import Base, get_db
import app.db_models as db_models
from app.db_models import UserAccount
from app.security import hash_password, create_access_token
from app.auth_deps import FAILED_LOGIN_ATTEMPTS

# Use StaticPool so in-memory SQLite tables persist across requests in the test process
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


class TestSuperAdminAuthAndProvisioning(unittest.TestCase):

    def setUp(self):
        app.dependency_overrides[get_db] = override_get_db
        client.cookies.clear()
        FAILED_LOGIN_ATTEMPTS.clear()
        Base.metadata.drop_all(bind=engine)
        Base.metadata.create_all(bind=engine)

    def tearDown(self):
        client.cookies.clear()
        Base.metadata.drop_all(bind=engine)
        app.dependency_overrides.pop(get_db, None)

    def test_01_setup_status_indicates_setup_required_when_empty(self):
        res = client.get("/api/admin/setup-status")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data["setup_required"])

    def test_02_one_time_setup_provisions_super_admin_and_creates_session(self):
        res = client.post("/api/admin/setup", json={
            "email": "primary_admin@enterprise.org",
            "password": "SecureAdminPassword2026!",
            "full_name": "Executive Admin"
        })
        self.assertEqual(res.status_code, 201)
        data = res.json()
        self.assertTrue(data["success"])
        self.assertEqual(data["user"]["role"], "super_admin")
        self.assertEqual(data["user"]["email"], "primary_admin@enterprise.org")
        self.assertIn("admin_session", client.cookies)

        # Check setup-status now indicates setup is NOT required
        status_res = client.get("/api/admin/setup-status")
        self.assertEqual(status_res.status_code, 200)
        self.assertFalse(status_res.json()["setup_required"])

    def test_03_setup_permanently_locked_once_admin_exists(self):
        # First setup succeeds
        client.post("/api/admin/setup", json={
            "email": "first_admin@enterprise.org",
            "password": "SecureAdminPassword2026!"
        })

        # Second setup must fail with 403 Forbidden
        res2 = client.post("/api/admin/setup", json={
            "email": "intruder_admin@enterprise.org",
            "password": "HackerPassword123!"
        })
        self.assertEqual(res2.status_code, 403)
        self.assertIn("locked", res2.json()["detail"].lower())

    def test_04_valid_super_admin_login(self):
        # Seed an admin
        db = TestingSessionLocal()
        admin = UserAccount(
            email="admin@example.com",
            password_hash=hash_password("SuperAdminPass123!"),
            role="super_admin",
            plan_tier="enterprise",
            is_active=True
        )
        db.add(admin)
        db.commit()
        db.close()

        res = client.post("/api/admin/login", json={
            "email": "admin@example.com",
            "password": "SuperAdminPass123!"
        })
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data["success"])
        self.assertEqual(data["user"]["role"], "super_admin")
        self.assertIn("admin_session", client.cookies)

    def test_05_invalid_password_rejection(self):
        db = TestingSessionLocal()
        admin = UserAccount(
            email="admin@example.com",
            password_hash=hash_password("SuperAdminPass123!"),
            role="super_admin",
            plan_tier="enterprise",
            is_active=True
        )
        db.add(admin)
        db.commit()
        db.close()

        res = client.post("/api/admin/login", json={
            "email": "admin@example.com",
            "password": "WrongPasswordAttempt"
        })
        self.assertEqual(res.status_code, 401)
        self.assertEqual(res.json()["detail"], "Invalid email address or password.")

    def test_06_unknown_email_rejection(self):
        res = client.post("/api/admin/login", json={
            "email": "nonexistent_admin@example.com",
            "password": "SuperAdminPass123!"
        })
        self.assertEqual(res.status_code, 401)
        self.assertEqual(res.json()["detail"], "Invalid email address or password.")

    def test_07_admin_dashboard_access_and_session_persistence(self):
        # 1. Login
        db = TestingSessionLocal()
        admin = UserAccount(
            email="director@enterprise.org",
            password_hash=hash_password("SuperAdminPass123!"),
            role="super_admin",
            plan_tier="enterprise",
            is_active=True
        )
        db.add(admin)
        db.commit()
        db.close()

        login_res = client.post("/api/admin/login", json={
            "email": "director@enterprise.org",
            "password": "SuperAdminPass123!"
        })
        self.assertEqual(login_res.status_code, 200)

        # 2. Access /api/admin/me using the cookie session
        me_res = client.get("/api/admin/me")
        self.assertEqual(me_res.status_code, 200)
        me_data = me_res.json()
        self.assertEqual(me_data["user"]["email"], "director@enterprise.org")
        self.assertEqual(me_data["user"]["role"], "super_admin")
        self.assertIn("admin:access", me_data["permissions"])

    def test_08_logout_functionality(self):
        db = TestingSessionLocal()
        admin = UserAccount(
            email="logout_test@enterprise.org",
            password_hash=hash_password("SuperAdminPass123!"),
            role="super_admin",
            plan_tier="enterprise",
            is_active=True
        )
        db.add(admin)
        db.commit()
        db.close()

        # Login
        client.post("/api/admin/login", json={
            "email": "logout_test@enterprise.org",
            "password": "SuperAdminPass123!"
        })

        # Verify authenticated
        self.assertEqual(client.get("/api/admin/me").status_code, 200)

        # Logout
        logout_res = client.post("/api/admin/logout")
        self.assertEqual(logout_res.status_code, 200)

        # Subsequent call must be 401
        self.assertEqual(client.get("/api/admin/me").status_code, 401)

    def test_09_unauthorized_candidate_access_rejection(self):
        # Seed candidate user
        db = TestingSessionLocal()
        candidate = UserAccount(
            email="regular_candidate@example.com",
            password_hash=hash_password("CandidatePass123!"),
            role="candidate",
            plan_tier="free",
            is_active=True
        )
        db.add(candidate)
        db.commit()
        db.close()

        # Login as candidate
        cand_login = client.post("/api/candidate/login", json={
            "email": "regular_candidate@example.com",
            "password": "CandidatePass123!"
        })
        self.assertEqual(cand_login.status_code, 200)

        # Attempt to access admin routes
        res = client.get("/api/admin/roles")
        self.assertEqual(res.status_code, 403)
        self.assertIn("Admin privileges required", res.json()["detail"])


if __name__ == "__main__":
    unittest.main()
