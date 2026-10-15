import json
import os
from pathlib import Path
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app


ROOT = Path(__file__).resolve().parent.parent
client = TestClient(app)


class TestPublicHome(unittest.TestCase):
    def test_root_shows_public_home_and_sign_in_link(self):
        for path in ("/", "/api/index.py?__path=/"):
            with self.subTest(path=path):
                response = client.get(path)

                self.assertEqual(response.status_code, 200)
                self.assertIn("Practice with purpose.", response.text)
                self.assertIn('href="/candidate/login"', response.text)

    def test_vercel_root_rewrite_uses_fastapi_public_home_route(self):
        config = json.loads((ROOT / "vercel.json").read_text(encoding="utf-8"))
        root_rewrite = next(rule for rule in config["rewrites"] if rule["source"] == "/")

        self.assertEqual(root_rewrite["destination"], "/api/index.py?__path=/")
        self.assertIn("Public-home.html", config["functions"]["api/index.py"]["includeFiles"])

    def test_login_page_remains_available_without_authentication(self):
        response = client.get("/candidate/login")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Candidate Login", response.text)

    def test_candidate_profile_still_requires_authentication(self):
        with patch.dict(os.environ, {"DEV_AUTH_BYPASS": "false"}):
            response = client.get("/api/candidate/me")

        self.assertEqual(response.status_code, 401)


if __name__ == "__main__":
    unittest.main()
