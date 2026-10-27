import json
import os
from pathlib import Path
import unittest
from unittest.mock import patch
from datetime import timezone

from fastapi.testclient import TestClient

from app.main import app
from api.index import app as vercel_app


ROOT = Path(__file__).resolve().parent.parent
client = TestClient(app)
vercel_client = TestClient(vercel_app)


class TestPublicHome(unittest.TestCase):
    def test_root_shows_public_home_and_sign_in_link(self):
        response = client.get("/")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Practice with purpose.", response.text)
        self.assertIn('href="/candidate/login"', response.text)

    def test_vercel_root_rewrite_uses_public_home(self):
        config = json.loads((ROOT / "vercel.json").read_text(encoding="utf-8"))
        root_rewrite = next(rule for rule in config["rewrites"] if rule["source"] == "/")

        self.assertEqual(root_rewrite["destination"], "/api/index.py?__path=/")
        self.assertEqual(
            config["functions"]["api/index.py"]["includeFiles"],
            "{app/**,Public-home.html}",
        )

    def test_vercel_entrypoint_routes_home_health_and_candidate_login(self):
        home = vercel_client.get("/api/index.py?__path=/")
        health = vercel_client.get("/health")
        login = vercel_client.get("/candidate/login")

        self.assertEqual(home.status_code, 200)
        self.assertIn("Practice with purpose.", home.text)
        self.assertEqual(health.status_code, 200)
        self.assertEqual(health.json()["status"], "ok")
        self.assertEqual(login.status_code, 200)
        self.assertIn("Candidate Login", login.text)

    def test_vercel_entrypoint_prefix_is_removed_from_override_path(self):
        response = vercel_client.get("/api/index.py?__path=/api/index.py")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Practice with purpose.", response.text)

    def test_candidate_profile_still_requires_authentication(self):
        with patch.dict(os.environ, {"DEV_AUTH_BYPASS": "false"}):
            response = client.get("/api/candidate/me")

        self.assertEqual(response.status_code, 401)


if __name__ == "__main__":
    unittest.main()
