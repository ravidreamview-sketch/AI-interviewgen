"""DevSecOps role prompt, fallback, and question-response contract tests."""

import os
import unittest
from unittest.mock import patch

_pinned_environment = {
    name: os.environ.get(name)
    for name in ("ENV", "DATABASE_URL", "LOCAL_DEMO_ACCESS", "DEV_AUTH_BYPASS")
}
os.environ["ENV"] = "test"
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["LOCAL_DEMO_ACCESS"] = "0"
os.environ["DEV_AUTH_BYPASS"] = "0"

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth_deps import get_current_user
from app.database import Base, get_db
from app.db_models import InterviewHistory, UserAccount
from app.main import app
from app.models import InterviewRequest
from app.prompts import DEVSECOPS_QUESTION_DOMAINS, interview_prompt
from app.services import get_fallback_questions

for _name, _value in _pinned_environment.items():
    if _value is None:
        os.environ.pop(_name, None)
    else:
        os.environ[_name] = _value


class TestDevSecOpsRolePreset(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        cls.SessionLocal = sessionmaker(bind=cls.engine, autoflush=False, autocommit=False)
        Base.metadata.create_all(bind=cls.engine)
        cls.previous_overrides = app.dependency_overrides.copy()
        cls.current_candidate = None

        def override_get_db():
            db = cls.SessionLocal()
            try:
                yield db
            finally:
                db.close()

        def override_current_user():
            return cls.current_candidate

        app.dependency_overrides[get_db] = override_get_db
        app.dependency_overrides[get_current_user] = override_current_user
        cls.client = TestClient(app)

    @classmethod
    def tearDownClass(cls):
        app.dependency_overrides.clear()
        app.dependency_overrides.update(cls.previous_overrides)
        Base.metadata.drop_all(bind=cls.engine)
        cls.engine.dispose()

    def setUp(self):
        with self.SessionLocal() as db:
            self.candidate = UserAccount(
                email="devsecops-test@example.test",
                full_name="DevSecOps Test Candidate",
                password_hash="test-only-unused",
                role="candidate",
                plan_tier="free",
                is_active=True,
            )
            db.add(self.candidate)
            db.commit()
            db.refresh(self.candidate)
            self.candidate_id = self.candidate.id
        self.__class__.current_candidate = self.candidate

    def tearDown(self):
        with self.SessionLocal() as db:
            db.query(InterviewHistory).delete()
            db.query(UserAccount).filter_by(id=self.candidate_id).delete()
            db.commit()
        self.__class__.current_candidate = None

    def test_prompt_includes_all_role_domains_and_requested_question_count(self):
        skills = [
            "Jenkins and GitLab CI/CD",
            "Docker and Podman",
            "Kubernetes and Red Hat OpenShift",
            "Argo CD, OpenShift GitOps and Helm",
            "SonarQube, SAST, DAST, Trivy and secret detection",
            "JFrog Artifactory, Nexus and Quay",
            "Terraform and Ansible",
            "Bash/Shell scripting and Python fundamentals",
            "Linux administration and troubleshooting",
            "Prometheus, Grafana, Dynatrace and ELK",
            "AWS/Azure fundamentals and EKS/AKS",
            "RBAC, TLS, network policies, secrets management and PCI DSS",
        ]
        prompt = interview_prompt(
            InterviewRequest(
                role="DevSecOps Engineer",
                experience="3+ Years",
                skills=skills,
                difficulty="Hard",
                number_of_questions=20,
                custom_question="Location: Chennai. Focus on the listed role requirements.",
            )
        )

        self.assertIn("EXACTLY 20", prompt)
        self.assertIn("3+ Years", prompt)
        self.assertIn("Location: Chennai", prompt)
        for name, coverage, _ in DEVSECOPS_QUESTION_DOMAINS:
            self.assertIn(name, prompt)
            self.assertIn(coverage.split(";")[0], prompt)
        for term in ("Jenkins", "GitLab CI/CD", "Docker", "Argo CD", "Trivy", "Terraform", "Artifactory", "Prometheus", "EKS", "PCI DSS"):
            self.assertIn(term, prompt)

    def test_fallback_uses_devsecops_bank_instead_of_generic_seed_questions(self):
        questions = get_fallback_questions(
            "DevSecOps Engineer",
            ["Kubernetes", "Terraform"],
            20,
            "Location: Chennai. Secure CI/CD, Kubernetes, and PCI DSS requirements.",
        )

        self.assertEqual(len(questions), 20)
        self.assertIn("Jenkins", questions[0])
        self.assertTrue(any("PCI DSS" in question for question in questions))
        self.assertTrue(any("OpenShift" in question for question in questions))

    def test_generate_endpoint_returns_domain_labels_and_evaluation_focus(self):
        generated = "\n".join(
            f"{index}. DevSecOps practice question {index}?"
            for index in range(1, 21)
        )
        payload = {
            "role": "DevSecOps Engineer",
            "experience": "3+ Years",
            "skills": ["Jenkins", "Kubernetes", "Terraform", "PCI DSS"],
            "difficulty": "Hard",
            "number_of_questions": 20,
            "custom_question": "Focus on the DevSecOps requirements for this role.",
        }

        with patch("app.main.generate_ai_questions", return_value=generated) as generate_ai:
            response = self.client.post("/api/generate", json=payload)

        self.assertEqual(response.status_code, 200, response.text)
        result = response.json()
        details = result["questions_details"]
        self.assertEqual(len(details), 20)
        self.assertEqual(
            [item["category"] for item in details],
            [domain[0] for domain in DEVSECOPS_QUESTION_DOMAINS for _ in range(2)],
        )
        self.assertIn("Assesses pipeline design", details[0]["model_answer"])
        self.assertIn("Assesses a structured diagnostic approach", details[-1]["model_answer"])
        self.assertIn("EXACTLY 20", generate_ai.call_args.args[0])


if __name__ == "__main__":
    unittest.main()
