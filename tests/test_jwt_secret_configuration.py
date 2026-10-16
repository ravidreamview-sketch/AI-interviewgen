import os
import unittest
from unittest.mock import patch

from app.security import _load_jwt_secret


class TestJwtSecretConfiguration(unittest.TestCase):
    def test_production_requires_configured_secret(self):
        with patch.dict(os.environ, {"VERCEL": "1"}, clear=True):
            with self.assertRaisesRegex(
                RuntimeError,
                "ADMIN_JWT_SECRET must be configured in production",
            ):
                _load_jwt_secret()

    def test_production_rejects_short_secret(self):
        with patch.dict(
            os.environ,
            {"ENV": "production", "ADMIN_JWT_SECRET": "short"},
            clear=True,
        ):
            with self.assertRaisesRegex(
                RuntimeError,
                "ADMIN_JWT_SECRET must contain at least 32 characters",
            ):
                _load_jwt_secret()

    def test_production_uses_configured_secret_without_exposing_it(self):
        configured_secret = "test-only-secret-value-with-at-least-32-characters"
        with patch.dict(
            os.environ,
            {"VERCEL": "1", "ADMIN_JWT_SECRET": configured_secret},
            clear=True,
        ):
            self.assertEqual(_load_jwt_secret(), configured_secret)

    def test_local_development_can_use_ephemeral_secret(self):
        with patch.dict(os.environ, {}, clear=True):
            first_secret = _load_jwt_secret()
            second_secret = _load_jwt_secret()

        self.assertEqual(len(first_secret), 43)
        self.assertNotEqual(first_secret, second_secret)


if __name__ == "__main__":
    unittest.main()
