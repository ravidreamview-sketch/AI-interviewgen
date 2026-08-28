import unittest
import os
import sys
import json
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__) + "/.."))

from app.main import app
from app.database import Base, get_db
from app.db_models import UserAccount, AuditLog, SystemConfig
from app.security import hash_password
from app.auth_deps import FAILED_LOGIN_ATTEMPTS

# Setup isolated test in-memory SQLite database
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


client = TestClient(app)


class TestDynamicMenuManagement(unittest.TestCase):

    def setUp(self):
        app.dependency_overrides[get_db] = override_get_db
        client.cookies.clear()
        FAILED_LOGIN_ATTEMPTS.clear()
        Base.metadata.drop_all(bind=engine)
        Base.metadata.create_all(bind=engine)

        db = TestingSessionLocal()
        # Seed Super Admin User
        admin_user = UserAccount(
            email="superadmin@ravigenai.com",
            password_hash=hash_password("SuperAdminPass123!"),
            role="super_admin",
            plan_tier="enterprise",
            is_active=True
        )
        # Seed Candidate User
        cand_user = UserAccount(
            email="candidate_test@ravigenai.com",
            password_hash=hash_password("CandidatePass123!"),
            role="candidate",
            plan_tier="free",
            is_active=True
        )
        db.add_all([admin_user, cand_user])
        db.commit()
        db.close()

    def tearDown(self):
        client.cookies.clear()
        Base.metadata.drop_all(bind=engine)
        app.dependency_overrides.pop(get_db, None)

    def get_admin_token(self):
        res = client.post("/api/admin/login", json={
            "email": "superadmin@ravigenai.com",
            "password": "SuperAdminPass123!"
        })
        self.assertEqual(res.status_code, 200)
        return res.json()["token"]

    def get_candidate_token(self):
        res = client.post("/api/candidate/login", json={
            "email": "candidate_test@ravigenai.com",
            "password": "CandidatePass123!"
        })
        self.assertEqual(res.status_code, 200)
        return res.cookies.get("candidate_session")

    def test_01_enabled_menu_appears_for_candidate(self):
        cand_token = self.get_candidate_token()
        headers = {"Authorization": f"Bearer {cand_token}"}
        res = client.get("/api/candidate/menus", headers=headers)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data["success"])
        menu_names = [m["name"] for m in data["menus"]]
        self.assertIn("Interview Studio", menu_names)

    def test_02_disabled_menu_does_not_appear_for_candidate(self):
        admin_token = self.get_admin_token()
        admin_headers = {"Authorization": f"Bearer {admin_token}", "X-Requested-With": "XMLHttpRequest"}
        
        # Disable "Interview Studio" menu
        patch_res = client.patch("/api/admin/menus/menu-2", headers=admin_headers, json={
            "status": "disabled"
        })
        self.assertEqual(patch_res.status_code, 200)

        # Candidate requests menu list
        cand_token = self.get_candidate_token()
        cand_headers = {"Authorization": f"Bearer {cand_token}"}
        res = client.get("/api/candidate/menus", headers=cand_headers)
        self.assertEqual(res.status_code, 200)
        menu_ids = [m["id"] for m in res.json()["menus"]]
        self.assertNotIn("menu-2", menu_ids)

    def test_03_super_admin_can_enable_menu(self):
        admin_token = self.get_admin_token()
        admin_headers = {"Authorization": f"Bearer {admin_token}", "X-Requested-With": "XMLHttpRequest"}
        
        # Disable menu first
        client.patch("/api/admin/menus/menu-6", headers=admin_headers, json={"status": "disabled"})
        
        # Enable menu
        enable_res = client.patch("/api/admin/menus/menu-6", headers=admin_headers, json={"status": "active"})
        self.assertEqual(enable_res.status_code, 200)
        self.assertEqual(enable_res.json()["menu"]["status"], "active")

    def test_04_super_admin_can_disable_menu(self):
        admin_token = self.get_admin_token()
        admin_headers = {"Authorization": f"Bearer {admin_token}", "X-Requested-With": "XMLHttpRequest"}
        
        disable_res = client.patch("/api/admin/menus/menu-3", headers=admin_headers, json={"status": "disabled"})
        self.assertEqual(disable_res.status_code, 200)
        self.assertEqual(disable_res.json()["menu"]["status"], "disabled")

    def test_05_candidate_navigation_updates_after_refresh(self):
        cand_token = self.get_candidate_token()
        cand_headers = {"Authorization": f"Bearer {cand_token}"}

        # Initial check -> "Session History" menu-6 enabled
        res1 = client.get("/api/candidate/menus", headers=cand_headers)
        self.assertIn("menu-6", [m["id"] for m in res1.json()["menus"]])

        # Admin disables menu-6
        admin_token = self.get_admin_token()
        admin_headers = {"Authorization": f"Bearer {admin_token}", "X-Requested-With": "XMLHttpRequest"}
        client.patch("/api/admin/menus/menu-6", headers=admin_headers, json={"status": "disabled"})

        # Candidate refresh re-fetch -> "Session History" menu-6 disabled & hidden
        res2 = client.get("/api/candidate/menus", headers=cand_headers)
        self.assertNotIn("menu-6", [m["id"] for m in res2.json()["menus"]])

    def test_06_candidate_cannot_access_disabled_feature_directly(self):
        admin_token = self.get_admin_token()
        admin_headers = {"Authorization": f"Bearer {admin_token}", "X-Requested-With": "XMLHttpRequest"}
        
        # Super Admin disables Session History (menu-6)
        client.patch("/api/admin/menus/menu-6", headers=admin_headers, json={"status": "disabled"})

        cand_token = self.get_candidate_token()
        cand_headers = {"Authorization": f"Bearer {cand_token}"}

        # Direct access to history API returns 403 Forbidden Feature Disabled
        history_res = client.get("/history", headers=cand_headers)
        self.assertEqual(history_res.status_code, 403)
        self.assertIn("disabled by administrator", history_res.json()["detail"])

    def test_07_candidate_cannot_access_admin_menu_api(self):
        cand_token = self.get_candidate_token()
        cand_headers = {"Authorization": f"Bearer {cand_token}", "X-Requested-With": "XMLHttpRequest"}
        
        # Candidate calling /api/admin/menus is blocked with 403 Forbidden
        admin_menus_res = client.get("/api/admin/menus", headers=cand_headers)
        self.assertEqual(admin_menus_res.status_code, 403)

    def test_08_role_restricted_menu_hidden_from_candidate(self):
        admin_token = self.get_admin_token()
        admin_headers = {"Authorization": f"Bearer {admin_token}", "X-Requested-With": "XMLHttpRequest"}

        # Create Admin-only menu
        client.post("/api/admin/menus", headers=admin_headers, json={
            "name": "Audit Logs Admin",
            "label": "Audit Logs",
            "type": "Core Workspace",
            "icon": "🔒",
            "route": "Admin.html",
            "status": "active",
            "visibility": "Super Admin",
            "allowed_roles": "super_admin"
        })

        cand_token = self.get_candidate_token()
        cand_headers = {"Authorization": f"Bearer {cand_token}"}
        res = client.get("/api/candidate/menus", headers=cand_headers)
        self.assertEqual(res.status_code, 200)
        menu_names = [m["name"] for m in res.json()["menus"]]
        self.assertNotIn("Audit Logs Admin", menu_names)

    def test_09_admin_menu_permissions_continue_working(self):
        admin_token = self.get_admin_token()
        admin_headers = {"Authorization": f"Bearer {admin_token}", "X-Requested-With": "XMLHttpRequest"}

        # Super Admin can GET list of all menus (including disabled)
        get_res = client.get("/api/admin/menus", headers=admin_headers)
        self.assertEqual(get_res.status_code, 200)
        self.assertIn("menus", get_res.json())

        # Super Admin can create new menu
        post_res = client.post("/api/admin/menus", headers=admin_headers, json={
            "name": "Test Tool",
            "label": "Test Tool",
            "status": "active",
            "visibility": "Public Candidate"
        })
        self.assertEqual(post_res.status_code, 200)
        m_id = post_res.json()["menu"]["id"]

        # Delete menu
        del_res = client.delete(f"/api/admin/menus/{m_id}", headers=admin_headers)
        self.assertEqual(del_res.status_code, 200)

    def test_10_menu_changes_create_audit_logs(self):
        admin_token = self.get_admin_token()
        admin_headers = {"Authorization": f"Bearer {admin_token}", "X-Requested-With": "XMLHttpRequest"}

        # Disable menu-1 -> MENU_DISABLED
        client.patch("/api/admin/menus/menu-1", headers=admin_headers, json={"status": "disabled"})
        
        # Enable menu-1 -> MENU_ENABLED
        client.patch("/api/admin/menus/menu-1", headers=admin_headers, json={"status": "active"})

        # Check Audit Logs
        db = TestingSessionLocal()
        logs = db.query(AuditLog).filter(AuditLog.action.in_(["MENU_DISABLED", "MENU_ENABLED"])).all()
        db.close()

        actions = [l.action for l in logs]
        self.assertIn("MENU_DISABLED", actions)
        self.assertIn("MENU_ENABLED", actions)

    def test_11_public_application_remains_functional(self):
        cand_token = self.get_candidate_token()
        cand_headers = {"Authorization": f"Bearer {cand_token}"}
        
        me_res = client.get("/api/candidate/me", headers=cand_headers)
        self.assertEqual(me_res.status_code, 200)
        self.assertEqual(me_res.json()["user"]["email"], "candidate_test@ravigenai.com")

    def test_13_public_menus_api_returns_active_candidate_items(self):
        # GET /api/public/menus without auth
        res = client.get("/api/public/menus")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data["success"])
        menu_names = [m["name"] for m in data["menus"]]
        self.assertIn("Dashboard", menu_names)

    def test_14_public_menus_api_reflects_admin_enable_disable_toast(self):
        admin_token = self.get_admin_token()
        admin_headers = {"Authorization": f"Bearer {admin_token}", "X-Requested-With": "XMLHttpRequest"}
        
        # Disable Dashboard (menu-1)
        disable_res = client.patch("/api/admin/menus/menu-1", headers=admin_headers, json={"status": "disabled"})
        self.assertEqual(disable_res.status_code, 200)
        self.assertIn("hidden from candidates", disable_res.json()["message"])

        # Check public menus API -> Dashboard hidden
        pub_res = client.get("/api/public/menus")
        pub_names = [m["name"] for m in pub_res.json()["menus"]]
        self.assertNotIn("Dashboard", pub_names)

        # Enable Dashboard (menu-1)
        enable_res = client.patch("/api/admin/menus/menu-1", headers=admin_headers, json={"status": "active"})
        self.assertEqual(enable_res.status_code, 200)
        self.assertIn("now visible to candidates", enable_res.json()["message"])

        # Check public menus API -> Dashboard visible again
        pub_res2 = client.get("/api/public/menus")
        pub_names2 = [m["name"] for m in pub_res2.json()["menus"]]
        self.assertIn("Dashboard", pub_names2)

    def test_15_candidate_cannot_modify_menu_visibility(self):
        cand_token = self.get_candidate_token()
        cand_headers = {"Authorization": f"Bearer {cand_token}", "X-Requested-With": "XMLHttpRequest"}
        
        post_res = client.post("/api/admin/menus", headers=cand_headers, json={"name": "Hacker Menu"})
        self.assertEqual(post_res.status_code, 403)

        patch_res = client.patch("/api/admin/menus/menu-1", headers=cand_headers, json={"status": "disabled"})
        self.assertEqual(patch_res.status_code, 403)

    def test_16_direct_url_access_blocked_when_menu_disabled(self):
        admin_token = self.get_admin_token()
        admin_headers = {"Authorization": f"Bearer {admin_token}", "X-Requested-With": "XMLHttpRequest"}
        
        # Disable Interview Studio (menu-2)
        client.patch("/api/admin/menus/menu-2", headers=admin_headers, json={"status": "disabled"})
        
        # Direct URL access to /candidate/interview-studio must return 403 Forbidden
        direct_res = client.get("/candidate/interview-studio")
        self.assertEqual(direct_res.status_code, 403)
        self.assertIn("Feature Temporarily Disabled", direct_res.text)
        
        # Re-enable Interview Studio
        client.patch("/api/admin/menus/menu-2", headers=admin_headers, json={"status": "active"})
        
        # Direct URL access restored
        direct_res_re = client.get("/candidate/interview-studio")
        self.assertEqual(direct_res_re.status_code, 200)


if __name__ == "__main__":
    unittest.main()
