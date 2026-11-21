import unittest
import os
from unittest.mock import patch
from datetime import timedelta

from app.core.config import Settings
from app.core.security import (
    hash_password,
    verify_password,
    create_access_token,
    decode_access_token,
    _get_signing_key,
)
from app.core.database import check_db_connection, get_db
from app.api.v1.api_router import api_v1_router
from app.api.v1.health import health_check, readiness_check
from app.main import app


class TestPhase1Foundation(unittest.TestCase):
    """
    Phase 1 Application Foundation & Modular Architecture Verification Suite.
    Validates configuration, security boundaries, database health checks, and modular routing.
    """

    # --------------------------------------------------------------------------
    # 1. Configuration & Secret Management
    # --------------------------------------------------------------------------
    def test_01_config_defaults_and_cors(self):
        cfg = Settings(ENV="development")
        self.assertEqual(cfg.API_V1_STR, "/api/v1")
        self.assertFalse(cfg.is_production)
        self.assertIn("http://localhost:8000", cfg.cors_origins)
        self.assertTrue("sqlite" in cfg.resolved_database_url)

    def test_02_production_rejects_missing_or_short_jwt_secret(self):
        with patch.dict(os.environ, {"ENV": "production"}):
            with self.assertRaises(ValueError):
                Settings(ADMIN_JWT_SECRET="too-short-secret")

            with self.assertRaises(ValueError):
                Settings(ADMIN_JWT_SECRET="")

    def test_03_production_accepts_valid_jwt_secret(self):
        valid_32_char_secret = "a" * 32
        with patch.dict(os.environ, {"ENV": "production"}):
            cfg = Settings(ADMIN_JWT_SECRET=valid_32_char_secret)
            self.assertTrue(cfg.is_production)
            self.assertEqual(cfg.ADMIN_JWT_SECRET, valid_32_char_secret)

    # --------------------------------------------------------------------------
    # 2. Security Foundation (PBKDF2 & JWT Architecture)
    # --------------------------------------------------------------------------
    def test_04_password_hashing_and_verification(self):
        raw_pass = "SecurePassphrase2026!"
        hashed = hash_password(raw_pass)

        # Verify format matches pbkdf2_sha256$600000$<salt>$<hash>
        parts = hashed.split("$")
        self.assertEqual(parts[0], "pbkdf2_sha256")
        self.assertEqual(parts[1], "600000")
        self.assertEqual(len(parts), 4)

        # Verify verification logic
        self.assertTrue(verify_password(raw_pass, hashed))
        self.assertFalse(verify_password("WrongPassword!", hashed))
        self.assertFalse(verify_password("", hashed))

    def test_05_jwt_token_creation_and_decoding(self):
        claims = {"sub": "candidate@example.com", "role": "candidate", "id": 42}
        token = create_access_token(claims, expires_delta=timedelta(minutes=30))

        decoded = decode_access_token(token)
        self.assertIsNotNone(decoded)
        self.assertEqual(decoded["sub"], "candidate@example.com")
        self.assertEqual(decoded["role"], "candidate")
        self.assertEqual(decoded["id"], 42)
        self.assertIn("jti", decoded)
        self.assertIn("exp", decoded)

    def test_06_tampered_or_expired_jwt_fails_validation(self):
        claims = {"sub": "candidate@example.com", "role": "candidate"}
        token = create_access_token(claims, expires_delta=timedelta(minutes=30))

        # Tamper signature
        parts = token.split(".")
        tampered_token = f"{parts[0]}.{parts[1]}.invalid_signature"
        self.assertIsNone(decode_access_token(tampered_token))

        # Expired token
        expired_token = create_access_token(claims, expires_delta=timedelta(seconds=-10))
        self.assertIsNone(decode_access_token(expired_token))

    def test_07_signing_key_fails_safely_in_production(self):
        from app.core.security import settings
        with patch.object(settings, "ENV", "production"):
            with patch.object(settings, "ADMIN_JWT_SECRET", None):
                with self.assertRaises(RuntimeError):
                    _get_signing_key()

    # --------------------------------------------------------------------------
    # 3. Database Health & Session Dependency
    # --------------------------------------------------------------------------
    def test_08_database_connectivity_and_session(self):
        # Database ping check
        is_healthy = check_db_connection()
        self.assertTrue(is_healthy, "Local database ping (SELECT 1) must succeed")

        # Session generator
        session_gen = get_db()
        db = next(session_gen)
        self.assertIsNotNone(db)
        db.close()

    # --------------------------------------------------------------------------
    # 4. Modular Router & Application Integration
    # --------------------------------------------------------------------------
    def test_09_v1_api_router_contains_all_foundation_modules(self):
        all_sub_routes = []
        for inc in api_v1_router.routes:
            if hasattr(inc, "include_context"):
                sub = inc.include_context.included_router
                prefix = inc.include_context.prefix
                for r in sub.routes:
                    all_sub_routes.append(prefix + getattr(r, "path", ""))

        self.assertGreaterEqual(len(all_sub_routes), 15, "api_v1_router must contain all foundation endpoints")
        self.assertTrue(any("/health" in p for p in all_sub_routes))
        self.assertTrue(any("/readiness" in p for p in all_sub_routes))
        self.assertTrue(any("/auth/login" in p for p in all_sub_routes))
        self.assertTrue(any("/learners/profile" in p for p in all_sub_routes))
        self.assertTrue(any("/paths/active" in p for p in all_sub_routes))
        self.assertTrue(any("/tutor/query" in p for p in all_sub_routes))
        self.assertTrue(any("/scenarios/list" in p for p in all_sub_routes))
        self.assertTrue(any("/interviews/start" in p for p in all_sub_routes))
        self.assertTrue(any("/competency/readiness" in p for p in all_sub_routes))
        self.assertTrue(any("/resumes/match" in p for p in all_sub_routes))
        self.assertTrue(any("/admin/users" in p for p in all_sub_routes))

    def test_10_health_and_readiness_handlers(self):
        health_res = health_check()
        self.assertEqual(health_res["status"], "healthy")
        self.assertIn("version", health_res)

        readiness_res = readiness_check()
        self.assertIn(readiness_res["status"], ("ready", "degraded"))
        self.assertEqual(readiness_res["database"], "connected")

    def test_11_main_app_mounts_v1_router_and_middlewares(self):
        # Verify that /api/v1 router is mounted in main app
        v1_mount = [
            r for r in app.routes
            if hasattr(r, "include_context") and getattr(r.include_context, "prefix", "") == "/api/v1"
        ]
        self.assertEqual(len(v1_mount), 1, "Main app must mount /api/v1 router")

        # Check middlewares are attached
        middleware_names = [getattr(m, "cls", type(m)).__name__ for m in app.user_middleware]
        self.assertIn("SecurityHeadersMiddleware", middleware_names)
        self.assertIn("RequestTracingMiddleware", middleware_names)


if __name__ == "__main__":
    unittest.main()
