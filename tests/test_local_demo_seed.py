import unittest
from pathlib import Path
from unittest.mock import patch
import os
import sys

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.database import Base, _ensure_local_demo_candidate, get_db
from app.db_models import UserAccount
from app.security import hash_password, verify_password
from app.main import app
from app.models import CandidateLoginRequest


class TestLocalDemoCandidateSeed(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(bind=self.engine)
        self.Session = sessionmaker(bind=self.engine)

    def tearDown(self):
        Base.metadata.drop_all(bind=self.engine)
        self.engine.dispose()

    def test_local_seed_creates_hashed_free_demo_account_idempotently(self):
        with patch("app.database.is_local_development", True):
            with self.Session() as db:
                self.assertTrue(_ensure_local_demo_candidate(db))
                self.assertFalse(_ensure_local_demo_candidate(db))
                user = db.query(UserAccount).filter_by(email="candidate@example.com").one()
                self.assertTrue(verify_password("CandidatePass123!", user.password_hash))
                self.assertNotEqual(user.password_hash, "CandidatePass123!")
                self.assertEqual(user.plan_tier, "free")

    def test_local_seed_preserves_existing_registered_account(self):
        with self.Session() as db:
            user = UserAccount(
                email="candidate@example.com",
                password_hash=hash_password("ExistingRegisteredPassword42!"),
                role="candidate",
                plan_tier="free",
                is_active=False,
            )
            db.add(user)
            db.commit()
            original_hash = user.password_hash
            with patch("app.database.is_local_development", True):
                self.assertFalse(_ensure_local_demo_candidate(db))
            db.refresh(user)
            self.assertEqual(user.password_hash, original_hash)
            self.assertFalse(user.is_active)

    def test_nonlocal_environment_does_not_seed_demo_user(self):
        with patch("app.database.is_local_development", False):
            with self.Session() as db:
                self.assertFalse(_ensure_local_demo_candidate(db))
                self.assertIsNone(db.query(UserAccount).filter_by(email="candidate@example.com").first())

    def test_reactivates_only_matching_known_demo_account(self):
        with self.Session() as db:
            user = UserAccount(
                email="candidate@example.com",
                full_name="Demo Candidate",
                password_hash=hash_password("CandidatePass123!"),
                role="candidate",
                plan_tier="pro",
                is_active=False,
            )
            db.add(user)
            db.commit()
            with patch("app.database.is_local_development", True):
                self.assertTrue(_ensure_local_demo_candidate(db))
            self.assertTrue(user.is_active)
            self.assertEqual(user.plan_tier, "free")

    def test_seeded_demo_authenticates_and_sets_session_cookie(self):
        TestingSession = sessionmaker(bind=self.engine, autoflush=False, autocommit=False)

        def isolated_get_db():
            with TestingSession() as db:
                yield db

        app.dependency_overrides[get_db] = isolated_get_db
        try:
            with TestingSession() as db, patch("app.database.is_local_development", True):
                self.assertTrue(_ensure_local_demo_candidate(db))

            with TestClient(app) as client:
                response = client.post("/api/candidate/login", json={
                    "email": "candidate@example.com",
                    "password": "CandidatePass123!",
                })
                self.assertEqual(response.status_code, 200, response.text)
                self.assertTrue(response.json()["success"])
                self.assertIn("candidate_session", response.cookies)
                profile = client.get("/api/candidate/me")
                self.assertEqual(profile.status_code, 200, profile.text)

                wrong_password = client.post("/api/candidate/login", json={
                    "email": "candidate@example.com",
                    "password": "wrong-password",
                })
                self.assertEqual(wrong_password.status_code, 401)

                unknown_user = client.post("/api/candidate/login", json={
                    "email": "missing@example.test",
                    "password": "CandidatePass123!",
                })
                self.assertEqual(unknown_user.status_code, 401)

            with TestingSession() as db:
                demo = db.query(UserAccount).filter_by(email="candidate@example.com").one()
                demo.is_active = False
                db.commit()
            with TestClient(app) as client:
                inactive = client.post("/api/candidate/login", json={
                    "email": "candidate@example.com",
                    "password": "CandidatePass123!",
                })
                self.assertEqual(inactive.status_code, 403)

            html = (Path(__file__).resolve().parent.parent / "Candidate-login.html").read_text(encoding="utf-8")
            self.assertIn('fetch("/api/candidate/login"', html)
            self.assertIn('"Content-Type": "application/json"', html)
            self.assertIn('email: email', html)
            self.assertIn('password: password', html)
            self.assertEqual(set(CandidateLoginRequest.model_fields), {"email", "password"})
        finally:
            app.dependency_overrides.pop(get_db, None)


if __name__ == "__main__":
    unittest.main()
