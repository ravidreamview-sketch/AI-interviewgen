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
        response = client.get("/")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Practice with purpose.", response.text)
        self.assertIn('href="/candidate/login"', response.text)

    def test_vercel_root_rewrite_uses_public_home(self):
        config = json.loads((ROOT / "vercel.json").read_text(encoding="utf-8"))
        root_rewrite = next(rule for rule in config["rewrites"] if rule["source"] == "/")

        self.assertEqual(root_rewrite["destination"], "/Public-home.html")

    def test_candidate_profile_still_requires_authentication(self):
        with patch.dict(os.environ, {"DEV_AUTH_BYPASS": "false"}):
            response = client.get("/api/candidate/me")

        self.assertEqual(response.status_code, 401)


if __name__ == "__main__":
    unittest.main()
