import unittest
import os
import sys
import json
import re
from pathlib import Path
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# Ensure project root is in sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from app.main import app
from app.database import Base, get_db
from app.db_models import UserAccount
from app.security import hash_password

# Setup isolated in-memory SQLite database
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

CANDIDATE_HTML_FILES = [
    "Candidate-dashboard.html",
    "Dashboard.html",
    "Interview-studio.html",
    "Mock-interview.html",
    "Interview-coach.html",
    "Resume-match.html",
    "Interview history.html",
    "Company-playbooks.html",
    "Upgrade-pro.html",
    "User-guide.html",
    "Answer-evaluator.html"
]

CANONICAL_NAV_URLS = [
    "/candidate/dashboard",
    "/candidate/interview-studio",
    "/candidate/mock-interview",
    "/candidate/interview-coach",
    "/candidate/resume-match",
    "/candidate/history",
    "/scorecard",
    "/candidate/company-playbooks"
]


class TestCandidateSidebarConsistency(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        Base.metadata.create_all(bind=engine)
        cls.client = TestClient(app)

    @classmethod
    def tearDownClass(cls):
        Base.metadata.drop_all(bind=engine)

    def setUp(self):
        # Clean DB before each test
        db = TestingSessionLocal()
        db.query(UserAccount).delete()
        db.commit()
        db.close()

    def test_all_candidate_html_files_exist_and_include_shell_assets(self):
        """All 11 candidate HTML files must include candidate-shell.css and candidate-shell.js."""
        for filename in CANDIDATE_HTML_FILES:
            filepath = BASE_DIR / filename
            self.assertTrue(filepath.exists(), f"File {filename} does not exist.")

            content = filepath.read_text(encoding="utf-8")
            self.assertIn("candidate-shell.css", content, f"{filename} is missing candidate-shell.css link.")
            self.assertIn("candidate-shell.js", content, f"{filename} is missing candidate-shell.js script.")

    def test_all_candidate_html_files_contain_canonical_sidebar_elements(self):
        """All candidate pages must have the canonical sidebar ID and profile elements."""
        for filename in CANDIDATE_HTML_FILES:
            filepath = BASE_DIR / filename
            content = filepath.read_text(encoding="utf-8")

            # Check sidebar and card IDs
            self.assertIn('id="sidebar"', content, f"{filename} missing id='sidebar'.")
            self.assertIn('id="sidebarUpgradeCard"', content, f"{filename} missing id='sidebarUpgradeCard'.")
            self.assertIn('id="sidebarUpgradeTitle"', content, f"{filename} missing id='sidebarUpgradeTitle'.")
            self.assertIn('id="sidebarUpgradeDesc"', content, f"{filename} missing id='sidebarUpgradeDesc'.")

            # Check profile identity elements
            self.assertIn('id="sidebarUserAvatar"', content, f"{filename} missing id='sidebarUserAvatar'.")
            self.assertIn('id="sidebarUserName"', content, f"{filename} missing id='sidebarUserName'.")
            self.assertIn('id="sidebarUserPlan"', content, f"{filename} missing id='sidebarUserPlan'.")
            self.assertIn('id="sidebarLogoutBtn"', content, f"{filename} missing id='sidebarLogoutBtn'.")

    def test_canonical_navigation_hierarchy_and_order_across_all_pages(self):
        """All candidate HTML files must include all 8 canonical navigation links in exact order."""
        for filename in CANDIDATE_HTML_FILES:
            filepath = BASE_DIR / filename
            content = filepath.read_text(encoding="utf-8")

            # Extract sidebar block
            sidebar_match = re.search(r'(?s)<aside\s+class="sidebar"[^>]*>.*?</aside>', content)
            self.assertIsNotNone(sidebar_match, f"Could not find <aside class='sidebar'> in {filename}")
            sidebar_html = sidebar_match.group(0)

            # Check that all canonical URLs appear in exact order within the sidebar
            last_pos = -1
            for nav_url in CANONICAL_NAV_URLS:
                pos = sidebar_html.find(f'href="{nav_url}"')
                self.assertNotEqual(
                    pos, -1,
                    f"Navigation URL '{nav_url}' missing from sidebar in {filename}"
                )
                self.assertGreater(
                    pos, last_pos,
                    f"Navigation URL '{nav_url}' appears out of order in {filename}"
                )
                last_pos = pos

    def test_dashboards_never_default_missing_plan_to_pro(self):
        """Candidate-dashboard.html and Dashboard.html must never default plan_tier to PRO."""
        for filename in ["Candidate-dashboard.html", "Dashboard.html"]:
            filepath = BASE_DIR / filename
            content = filepath.read_text(encoding="utf-8")

            # Check that the legacy buggy pattern does not exist
            self.assertNotIn(
                "(CURRENT_CANDIDATE.plan_tier || 'PRO').toUpperCase() + ' TIER'",
                content,
                f"{filename} still contains the legacy bug defaulting plan_tier to PRO!"
            )
            self.assertNotIn(
                "plan_tier || 'PRO'",
                content,
                f"{filename} still contains 'plan_tier || 'PRO''!"
            )

    def test_static_candidate_shell_endpoints_served(self):
        """FastAPI app must serve candidate-shell.css and candidate-shell.js with correct MIME types."""
        # CSS at canonical and candidate-scoped URLs
        res_css = self.client.get("/shared/candidate-shell.css")
        self.assertEqual(res_css.status_code, 200)
        self.assertIn("text/css", res_css.headers.get("content-type", ""))
        self.assertIn("--sidebar-w: 290px", res_css.text)

        res_css_cand = self.client.get("/candidate/shared/candidate-shell.css")
        self.assertEqual(res_css_cand.status_code, 200)
        self.assertIn("text/css", res_css_cand.headers.get("content-type", ""))

        # JS at canonical and candidate-scoped URLs
        res_js = self.client.get("/shared/candidate-shell.js")
        self.assertEqual(res_js.status_code, 200)
        self.assertIn("javascript", res_js.headers.get("content-type", ""))
        self.assertIn("CANONICAL_NAVIGATION", res_js.text)
        self.assertIn("CandidateShell", res_js.text)

        res_js_cand = self.client.get("/candidate/shared/candidate-shell.js")
        self.assertEqual(res_js_cand.status_code, 200)
        self.assertIn("javascript", res_js_cand.headers.get("content-type", ""))

    def test_candidate_me_returns_profile_identity_and_plan_tier(self):
        """GET /api/candidate/me must return full_name and plan_tier for authenticated candidate."""
        db = TestingSessionLocal()
        candidate = UserAccount(
            email="candidate.free@example.com",
            full_name="Sarah Connor",
            password_hash=hash_password("Secr3tP@ss!"),
            role="candidate",
            is_active=True,
            plan_tier="free"
        )
        db.add(candidate)
        db.commit()
        db.refresh(candidate)
        db.close()

        # Login to obtain session cookie
        login_res = self.client.post(
            "/candidate/login",
            json={"email": "candidate.free@example.com", "password": "Secr3tP@ss!"}
        )
        self.assertEqual(login_res.status_code, 200)

        # Call /api/candidate/me
        me_res = self.client.get("/api/candidate/me")
        self.assertEqual(me_res.status_code, 200)
        data = me_res.json()

        user = data.get("user", data)
        self.assertEqual(user.get("full_name"), "Sarah Connor")
        self.assertEqual(user.get("email"), "candidate.free@example.com")
        self.assertEqual(user.get("plan_tier"), "free")

    def test_candidate_me_returns_pro_plan_tier(self):
        """GET /api/candidate/me must return plan_tier='pro' when candidate has pro plan."""
        db = TestingSessionLocal()
        candidate = UserAccount(
            email="candidate.pro@example.com",
            full_name="Alex Murphy",
            password_hash=hash_password("Secr3tP@ss!"),
            role="candidate",
            is_active=True,
            plan_tier="pro"
        )
        db.add(candidate)
        db.commit()
        db.refresh(candidate)
        db.close()

        # Login to obtain session cookie
        login_res = self.client.post(
            "/candidate/login",
            json={"email": "candidate.pro@example.com", "password": "Secr3tP@ss!"}
        )
        self.assertEqual(login_res.status_code, 200)

        # Call /api/candidate/me
        me_res = self.client.get("/api/candidate/me")
        self.assertEqual(me_res.status_code, 200)
        data = me_res.json()

        user = data.get("user", data)
        self.assertEqual(user.get("full_name"), "Alex Murphy")
        self.assertEqual(user.get("plan_tier"), "pro")

    def test_scorecard_has_canonical_dashboard_link(self):
        """scorecard.html header must have a link pointing back to /candidate/dashboard."""
        filepath = BASE_DIR / "scorecard.html"
        self.assertTrue(filepath.exists())
        content = filepath.read_text(encoding="utf-8")
        self.assertIn('href="/candidate/dashboard"', content)

    def test_vercel_json_includes_shared_bundle_and_rewrites(self):
        """vercel.json must bundle shared/** and contain rewrites for /candidate/shared/:match*."""
        vpath = BASE_DIR / "vercel.json"
        self.assertTrue(vpath.exists())
        vdata = json.loads(vpath.read_text(encoding="utf-8"))

        include_files = vdata.get("functions", {}).get("api/index.py", {}).get("includeFiles", "")
        self.assertIn("shared/**", include_files, "vercel.json missing shared/** in includeFiles.")

        rewrites = vdata.get("rewrites", [])
        shared_rewrite = any(
            r.get("source") == "/candidate/shared/:match*" and r.get("destination") == "/shared/:match*"
            for r in rewrites
        )
        self.assertTrue(shared_rewrite, "vercel.json missing /candidate/shared/:match* rewrite.")


if __name__ == "__main__":
    unittest.main()
