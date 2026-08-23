import unittest
import os
import sys
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__) + "/.."))

from sqlalchemy.pool import StaticPool
from app.main import app
from app.database import Base, get_db
from app.db_models import UserAccount
from app.security import hash_password, verify_password
from app.auth_deps import FAILED_LOGIN_ATTEMPTS

# Setup isolated test in-memory SQLite database with StaticPool
SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"
engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_db():
    try:
        db = TestingSessionLocal()
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db
client = TestClient(app)


class TestCandidateAuthentication(unittest.TestCase):

    def setUp(self):
        client.cookies.clear()
        FAILED_LOGIN_ATTEMPTS.clear()
        Base.metadata.drop_all(bind=engine)
        Base.metadata.create_all(bind=engine)
        
        db = TestingSessionLocal()
        # Seed Super Admin
        admin_user = UserAccount(
            email="superadmin@ravigenai.com",
            password_hash=hash_password("SuperAdminPass123!"),
            role="super_admin",
            plan_tier="enterprise",
            is_active=True
        )
        db.add(admin_user)
        db.commit()
        db.close()

    def tearDown(self):
        client.cookies.clear()
        Base.metadata.drop_all(bind=engine)

    def get_admin_token(self):
        res = client.post("/api/admin/login", json={
            "email": "superadmin@ravigenai.com",
            "password": "SuperAdminPass123!"
        })
        self.assertEqual(res.status_code, 200)
        return res.json()["token"]

    def test_1_candidate_cannot_login_before_account_exists(self):
        res = client.post("/api/candidate/login", json={
            "email": "nonexistent@ravigenai.com",
            "password": "Password123!"
        })
        self.assertEqual(res.status_code, 401)
        self.assertEqual(res.json()["detail"], "Invalid email or password.")

    def test_2_admin_can_create_candidate(self):
        token = self.get_admin_token()
        headers = {"Authorization": f"Bearer {token}", "X-Requested-With": "XMLHttpRequest"}
        res = client.post("/api/admin/users", headers=headers, json={
            "email": "candidate1@ravigenai.com",
            "password": "CandidatePass123!",
            "role": "candidate",
            "plan_tier": "pro",
            "is_active": True
        })
        self.assertEqual(res.status_code, 201)
        data = res.json()
        self.assertTrue(data["success"])
        self.assertEqual(data["user"]["email"], "candidate1@ravigenai.com")
        self.assertEqual(data["user"]["role"], "candidate")

    def test_3_candidate_password_is_hashed(self):
        token = self.get_admin_token()
        headers = {"Authorization": f"Bearer {token}", "X-Requested-With": "XMLHttpRequest"}
        raw_pass = "CandidatePass123!"
        client.post("/api/admin/users", headers=headers, json={
            "email": "candidate_hash_test@ravigenai.com",
            "password": raw_pass,
            "role": "candidate"
        })
        
        db = TestingSessionLocal()
        user = db.query(UserAccount).filter(UserAccount.email == "candidate_hash_test@ravigenai.com").first()
        db.close()
        
        self.assertIsNotNone(user)
        self.assertNotEqual(user.password_hash, raw_pass)
        self.assertTrue(user.password_hash.startswith("pbkdf2_sha256$"))
        self.assertTrue(verify_password(raw_pass, user.password_hash))

    def test_4_candidate_can_login_after_creation(self):
        token = self.get_admin_token()
        headers = {"Authorization": f"Bearer {token}", "X-Requested-With": "XMLHttpRequest"}
        client.post("/api/admin/users", headers=headers, json={
            "email": "login_candidate@ravigenai.com",
            "password": "ValidPassword123!",
            "role": "candidate"
        })
        
        login_res = client.post("/api/candidate/login", json={
            "email": "login_candidate@ravigenai.com",
            "password": "ValidPassword123!"
        })
        self.assertEqual(login_res.status_code, 200)
        data = login_res.json()
        self.assertTrue(data["success"])
        self.assertIn("token", data)
        self.assertEqual(data["user"]["email"], "login_candidate@ravigenai.com")
        self.assertEqual(data["role"], "candidate")

    def test_5_candidate_session_created_securely(self):
        token = self.get_admin_token()
        headers = {"Authorization": f"Bearer {token}", "X-Requested-With": "XMLHttpRequest"}
        client.post("/api/admin/users", headers=headers, json={
            "email": "session_test@ravigenai.com",
            "password": "SessionPassword123!",
            "role": "candidate"
        })
        
        res = client.post("/api/candidate/login", json={
            "email": "session_test@ravigenai.com",
            "password": "SessionPassword123!"
        })
        self.assertEqual(res.status_code, 200)
        self.assertIn("candidate_session", res.cookies)
        self.assertIsNotNone(res.json()["token"])

    def test_6_candidate_can_access_candidate_dashboard_me(self):
        token = self.get_admin_token()
        headers = {"Authorization": f"Bearer {token}", "X-Requested-With": "XMLHttpRequest"}
        client.post("/api/admin/users", headers=headers, json={
            "email": "dashboard_cand@ravigenai.com",
            "password": "DashboardPass123!",
            "role": "candidate"
        })
        
        login_res = client.post("/api/candidate/login", json={
            "email": "dashboard_cand@ravigenai.com",
            "password": "DashboardPass123!"
        })
        cand_token = login_res.json()["token"]
        
        cand_headers = {"Authorization": f"Bearer {cand_token}"}
        me_res = client.get("/api/candidate/me", headers=cand_headers)
        self.assertEqual(me_res.status_code, 200)
        self.assertEqual(me_res.json()["user"]["email"], "dashboard_cand@ravigenai.com")

    def test_7_candidate_cannot_access_admin_dashboard_apis(self):
        token = self.get_admin_token()
        headers = {"Authorization": f"Bearer {token}", "X-Requested-With": "XMLHttpRequest"}
        client.post("/api/admin/users", headers=headers, json={
            "email": "restricted_cand@ravigenai.com",
            "password": "RestrictedPass123!",
            "role": "candidate"
        })
        
        login_res = client.post("/api/candidate/login", json={
            "email": "restricted_cand@ravigenai.com",
            "password": "RestrictedPass123!"
        })
        cand_token = login_res.json()["token"]
        
        cand_headers = {"Authorization": f"Bearer {cand_token}", "X-Requested-With": "XMLHttpRequest"}
        admin_users_res = client.get("/api/admin/users", headers=cand_headers)
        self.assertEqual(admin_users_res.status_code, 403)
        self.assertIn("Admin privileges required", admin_users_res.json()["detail"])

    def test_8_candidate_cannot_access_admin_apis(self):
        token = self.get_admin_token()
        headers = {"Authorization": f"Bearer {token}", "X-Requested-With": "XMLHttpRequest"}
        client.post("/api/admin/users", headers=headers, json={
            "email": "no_admin_api@ravigenai.com",
            "password": "NoAdminApiPass123!",
            "role": "candidate"
        })
        
        login_res = client.post("/api/candidate/login", json={
            "email": "no_admin_api@ravigenai.com",
            "password": "NoAdminApiPass123!"
        })
        cand_token = login_res.json()["token"]
        cand_headers = {"Authorization": f"Bearer {cand_token}", "X-Requested-With": "XMLHttpRequest"}
        
        for endpoint in ["/api/admin/users", "/api/admin/roles", "/api/admin/audit-logs", "/api/admin/dashboard-stats"]:
            res = client.get(endpoint, headers=cand_headers)
            self.assertEqual(res.status_code, 403)

    def test_9_inactive_candidate_cannot_login(self):
        token = self.get_admin_token()
        headers = {"Authorization": f"Bearer {token}", "X-Requested-With": "XMLHttpRequest"}
        client.post("/api/admin/users", headers=headers, json={
            "email": "inactive_cand@ravigenai.com",
            "password": "InactivePass123!",
            "role": "candidate",
            "is_active": False
        })
        
        login_res = client.post("/api/candidate/login", json={
            "email": "inactive_cand@ravigenai.com",
            "password": "InactivePass123!"
        })
        self.assertEqual(login_res.status_code, 403)
        self.assertEqual(login_res.json()["detail"], "Your account is currently inactive. Please contact your administrator.")

    def test_10_invalid_credentials_generic_error(self):
        token = self.get_admin_token()
        headers = {"Authorization": f"Bearer {token}", "X-Requested-With": "XMLHttpRequest"}
        client.post("/api/admin/users", headers=headers, json={
            "email": "exist_cand@ravigenai.com",
            "password": "CorrectPass123!",
            "role": "candidate"
        })
        
        res1 = client.post("/api/candidate/login", json={
            "email": "exist_cand@ravigenai.com",
            "password": "WrongPassword123!"
        })
        self.assertEqual(res1.status_code, 401)
        self.assertEqual(res1.json()["detail"], "Invalid email or password.")
        
        res2 = client.post("/api/candidate/login", json={
            "email": "doesnotexist@ravigenai.com",
            "password": "CorrectPass123!"
        })
        self.assertEqual(res2.status_code, 401)
        self.assertEqual(res2.json()["detail"], "Invalid email or password.")

    def test_11_candidate_cannot_change_role(self):
        token = self.get_admin_token()
        headers = {"Authorization": f"Bearer {token}", "X-Requested-With": "XMLHttpRequest"}
        create_res = client.post("/api/admin/users", headers=headers, json={
            "email": "self_promo@ravigenai.com",
            "password": "CandidatePass123!",
            "role": "candidate"
        })
        cand_id = create_res.json()["user"]["id"]
        
        login_res = client.post("/api/candidate/login", json={
            "email": "self_promo@ravigenai.com",
            "password": "CandidatePass123!"
        })
        cand_token = login_res.json()["token"]
        cand_headers = {"Authorization": f"Bearer {cand_token}", "X-Requested-With": "XMLHttpRequest"}
        
        patch_res = client.patch(f"/api/admin/users/{cand_id}", headers=cand_headers, json={
            "role": "super_admin"
        })
        self.assertEqual(patch_res.status_code, 403)

    def test_12_candidate_cannot_access_other_user_admin_data(self):
        token = self.get_admin_token()
        headers = {"Authorization": f"Bearer {token}", "X-Requested-With": "XMLHttpRequest"}
        client.post("/api/admin/users", headers=headers, json={
            "email": "cand_a@ravigenai.com",
            "password": "Password123!",
            "role": "candidate"
        })
        
        login_res = client.post("/api/candidate/login", json={
            "email": "cand_a@ravigenai.com",
            "password": "Password123!"
        })
        cand_token = login_res.json()["token"]
        cand_headers = {"Authorization": f"Bearer {cand_token}", "X-Requested-With": "XMLHttpRequest"}
        
        res = client.get("/api/admin/users?search=superadmin", headers=cand_headers)
        self.assertEqual(res.status_code, 403)

    def test_13_generate_endpoint_requires_auth(self):
        unauth_res = client.post("/api/generate", json={
            "role": "Software Engineer",
            "skills": ["Python", "FastAPI"]
        })
        self.assertEqual(unauth_res.status_code, 401)
        
        token = self.get_admin_token()
        headers = {"Authorization": f"Bearer {token}", "X-Requested-With": "XMLHttpRequest"}
        client.post("/api/admin/users", headers=headers, json={
            "email": "generator_cand@ravigenai.com",
            "password": "Password123!",
            "role": "candidate"
        })
        
        login_res = client.post("/api/candidate/login", json={
            "email": "generator_cand@ravigenai.com",
            "password": "Password123!"
        })
        cand_token = login_res.json()["token"]
        cand_headers = {"Authorization": f"Bearer {cand_token}"}
        
        gen_res = client.post("/api/generate", headers=cand_headers, json={
            "role": "Software Engineer",
            "skills": ["Python", "FastAPI"],
            "number_of_questions": 3
        })
        self.assertEqual(gen_res.status_code, 200)
        self.assertIn("questions", gen_res.json())


if __name__ == "__main__":
    unittest.main()
