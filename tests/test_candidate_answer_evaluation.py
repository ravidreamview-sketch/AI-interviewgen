import unittest
import json
from pathlib import Path
from fastapi.testclient import TestClient
from app.main import app
from app.database import SessionLocal, _run_migration_candidate_answer_attempts, engine
from app.db_models import UserAccount, InterviewHistory, CandidateAnswerAttempt
from app.security import create_access_token, hash_password
from app.services import evaluate_candidate_practice_answer, build_contextual_evaluation_fallback
from sqlalchemy import inspect


client = TestClient(app)


class TestCandidateAnswerEvaluation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        db = SessionLocal()
        # Candidate 1 (owner)
        cls.candidate1 = db.query(UserAccount).filter(UserAccount.email == "eval_cand1@example.com").first()
        if not cls.candidate1:
            cls.candidate1 = UserAccount(
                email="eval_cand1@example.com",
                role="candidate",
                full_name="Evaluation Candidate One",
                password_hash=hash_password("Pass123!"),
                is_active=True
            )
            db.add(cls.candidate1)
            db.commit()
            db.refresh(cls.candidate1)

        # Candidate 2 (other user for cross-user security tests)
        cls.candidate2 = db.query(UserAccount).filter(UserAccount.email == "eval_cand2@example.com").first()
        if not cls.candidate2:
            cls.candidate2 = UserAccount(
                email="eval_cand2@example.com",
                role="candidate",
                full_name="Evaluation Candidate Two",
                password_hash=hash_password("Pass123!"),
                is_active=True
            )
            db.add(cls.candidate2)
            db.commit()
            db.refresh(cls.candidate2)

        # Create an interview paper owned by candidate 1
        cls.test_paper = InterviewHistory(
            role="Senior Cloud Architect",
            experience="6 Years",
            skills="AWS, Terraform, Kubernetes, Zero Trust",
            difficulty="Hard",
            questions="1. How do you design multi-region disaster recovery with zero-RPO data replication?\n2. Explain service mesh mTLS traffic encryption at scale.",
            questions_payload=json.dumps([
                {
                    "question": "How do you design multi-region disaster recovery with zero-RPO data replication?",
                    "sample_answer": "Achieving zero RPO across cloud regions requires synchronous data replication or two-phase commits.",
                    "key_points": ["Synchronous replication latency trade-off", "Aurora Global Database or Spanner", "DNS failover with Route 53"],
                    "practical_example": "Configuring AWS Aurora with write-forwarding and Route 53 Application Recovery Controller."
                },
                {
                    "question": "Explain service mesh mTLS traffic encryption at scale.",
                    "sample_answer": "Service meshes like Istio or Linkerd use Envoy sidecars with short-lived X.509 certificates.",
                    "key_points": ["Automated cert rotation with SPIFFE/SPIRE", "Cryptographic identity", "Envoy proxy overhead"],
                    "practical_example": "Enforcing STRICT PeerAuthentication in Istio across production Kubernetes namespaces."
                }
            ]),
            user_id=cls.candidate1.id,
            question_engine_version="qengine-v1.0.0"
        )
        db.add(cls.test_paper)
        db.commit()
        db.refresh(cls.test_paper)

        cls.paper_id = cls.test_paper.id

        cls.token1 = create_access_token({
            "sub": str(cls.candidate1.id),
            "email": cls.candidate1.email,
            "role": cls.candidate1.role
        })
        cls.auth_headers_1 = {"Authorization": f"Bearer {cls.token1}"}

        cls.token2 = create_access_token({
            "sub": str(cls.candidate2.id),
            "email": cls.candidate2.email,
            "role": cls.candidate2.role
        })
        cls.auth_headers_2 = {"Authorization": f"Bearer {cls.token2}"}

        db.close()

    # 1. Test Valid Answer Evaluation Schema & 20-Point Rubric
    def test_01_valid_answer_evaluation_schema_and_rubric(self):
        payload = {
            "interview_id": self.paper_id,
            "question_index": 0,
            "question": "How do you design multi-region disaster recovery with zero-RPO data replication?",
            "candidate_answer": (
                "To achieve zero RPO across regions, we cannot rely on asynchronous replication because of data loss risks. "
                "Instead, we employ synchronous multi-region replication using distributed consensus systems like Google Cloud Spanner "
                "or multi-region Aurora with synchronous write-forwarding. Furthermore, we implement automated health checks and "
                "DNS failover using Route 53 ARC with routing controls to shift traffic seamlessly without split-brain scenarios."
            ),
            "role": "Senior Cloud Architect",
            "skills": ["AWS", "Terraform", "Kubernetes"],
            "difficulty": "Hard",
            "reference_sample_answer": "Achieving zero RPO across cloud regions requires synchronous data replication or two-phase commits."
        }

        res = client.post("/api/evaluate-answer", json=payload, headers=self.auth_headers_1)
        self.assertEqual(res.status_code, 200, f"Expected 200, got {res.status_code}: {res.text}")
        data = res.json()

        # Validate top-level schema
        self.assertIn("overall_score", data)
        self.assertIn("score_breakdown", data)
        self.assertIn("strengths", data)
        self.assertIn("improvements", data)
        self.assertIn("missing_key_points", data)
        self.assertIn("suggested_answer", data)
        self.assertIn("next_practice_steps", data)

        # Validate score bounds
        self.assertGreaterEqual(data["overall_score"], 0)
        self.assertLessEqual(data["overall_score"], 20)

        # Validate 4 breakdown dimensions out of 5 each
        breakdown = data["score_breakdown"]
        for dim in ["relevance", "technical_accuracy", "depth", "communication"]:
            self.assertIn(dim, breakdown)
            self.assertGreaterEqual(breakdown[dim], 0)
            self.assertLessEqual(breakdown[dim], 5)

        # Check total matches sum of 4 dimensions
        expected_sum = (
            breakdown["relevance"] +
            breakdown["technical_accuracy"] +
            breakdown["depth"] +
            breakdown["communication"]
        )
        self.assertEqual(data["overall_score"], expected_sum)

        # Validate feedback contents
        self.assertIsInstance(data["strengths"], list)
        self.assertGreaterEqual(len(data["strengths"]), 1)
        self.assertIsInstance(data["improvements"], list)
        self.assertIsInstance(data["missing_key_points"], list)
        self.assertIsInstance(data["suggested_answer"], str)
        self.assertGreater(len(data["suggested_answer"]), 20)
        self.assertIsInstance(data["next_practice_steps"], list)

    # 2. Test Dual Endpoint Alias /api/candidate/evaluate-answer
    def test_02_dual_endpoint_alias(self):
        payload = {
            "interview_id": self.paper_id,
            "question_index": 1,
            "question": "Explain service mesh mTLS traffic encryption at scale.",
            "candidate_answer": (
                "In Kubernetes microservices, we implement mutual TLS by installing an Istio service mesh. "
                "Istiod acts as a Certificate Authority issuing short-lived X.509 SPIFFE identity certs to Envoy sidecars. "
                "Envoy proxies terminate and initiate TLS transparently, enforcing STRICT mode authentication."
            ),
            "role": "Senior Cloud Architect",
            "skills": ["Kubernetes", "Istio"],
            "difficulty": "Hard"
        }
        res = client.post("/api/candidate/evaluate-answer", json=payload, headers=self.auth_headers_1)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("overall_score", data)
        self.assertIn("strengths", data)

    # 3. Test Answer Length Validation (Empty, < 15 Chars, < 3 Words)
    def test_03_answer_length_validation(self):
        # Empty string
        res_empty = client.post("/api/evaluate-answer", json={
            "question": "Explain zero-trust architecture.",
            "candidate_answer": ""
        }, headers=self.auth_headers_1)
        self.assertEqual(res_empty.status_code, 400)
        self.assertIn("at least 15 characters", res_empty.json()["detail"].lower())

        # Under 15 chars
        res_short = client.post("/api/evaluate-answer", json={
            "question": "Explain zero-trust architecture.",
            "candidate_answer": "Too short"  # 9 chars
        }, headers=self.auth_headers_1)
        self.assertEqual(res_short.status_code, 400)

        # Under 3 words
        res_few_words = client.post("/api/evaluate-answer", json={
            "question": "Explain zero-trust architecture.",
            "candidate_answer": "Supercalifragilisticexpialidocious words"  # > 15 chars, but only 2 words
        }, headers=self.auth_headers_1)
        self.assertEqual(res_few_words.status_code, 400)
        self.assertIn("3 words", res_few_words.json()["detail"].lower())

    # 4. Test Authentication Enforcement (401 Unauthorized)
    def test_04_authentication_required(self):
        res = client.post("/api/evaluate-answer", json={
            "question": "Explain zero-trust architecture.",
            "candidate_answer": "We enforce strict perimeterless security with identity-aware proxies."
        })
        self.assertEqual(res.status_code, 401)

    # 5. Test Cross-User Ownership Enforcement (403 Forbidden)
    def test_05_cross_user_paper_protection(self):
        payload = {
            "interview_id": self.paper_id,  # Owned by candidate 1
            "question_index": 0,
            "question": "How do you design multi-region disaster recovery with zero-RPO data replication?",
            "candidate_answer": "Candidate 2 trying to inject evaluation into Candidate 1 paper.",
            "role": "Cloud Architect"
        }
        # Attempt evaluation as candidate 2
        res = client.post("/api/evaluate-answer", json=payload, headers=self.auth_headers_2)
        self.assertEqual(res.status_code, 403)
        detail = res.json()["detail"].lower()
        self.assertTrue("forbidden" in detail or "permission" in detail)

    # 6. Test Persistence in candidate_answer_attempts Table
    def test_06_database_persistence_of_evaluation_attempts(self):
        answer_text = (
            "Service meshes inject sidecars next to each pod. Certificates are automatically rotated every 24 hours "
            "to minimize exposure window and enforce cryptographic identities with zero trust."
        )
        res = client.post("/api/evaluate-answer", json={
            "interview_id": self.paper_id,
            "question_index": 1,
            "question": "Explain service mesh mTLS traffic encryption at scale.",
            "candidate_answer": answer_text,
            "role": "Senior Cloud Architect",
            "skills": ["Kubernetes", "Service Mesh"]
        }, headers=self.auth_headers_1)
        self.assertEqual(res.status_code, 200)

        # Inspect database record
        db = SessionLocal()
        attempt = db.query(CandidateAnswerAttempt).filter(
            CandidateAnswerAttempt.interview_id == self.paper_id,
            CandidateAnswerAttempt.question_index == 1,
            CandidateAnswerAttempt.user_id == self.candidate1.id
        ).order_by(CandidateAnswerAttempt.id.desc()).first()

        self.assertIsNotNone(attempt)
        self.assertEqual(attempt.candidate_answer, answer_text)
        self.assertGreaterEqual(attempt.overall_score, 0)
        self.assertLessEqual(attempt.overall_score, 20)

        feedback = json.loads(attempt.evaluation_feedback)
        self.assertIn("score_breakdown", feedback)
        self.assertIn("strengths", feedback)
        self.assertIn("improvements", feedback)
        db.close()

    # 7. Test Retrieval of Evaluations via GET /api/history/{id}/evaluations
    def test_07_retrieve_saved_evaluations(self):
        res = client.get(f"/api/history/{self.paper_id}/evaluations", headers=self.auth_headers_1)
        self.assertEqual(res.status_code, 200)
        data = res.json()

        self.assertIn("interview_id", data)
        self.assertEqual(data["interview_id"], self.paper_id)
        self.assertIn("evaluations", data)

        # Question 1 was evaluated in test_06
        self.assertIn("1", data["evaluations"])
        eval_q1 = data["evaluations"]["1"]
        self.assertIn("candidate_answer", eval_q1)
        self.assertIn("overall_score", eval_q1)
        self.assertIn("score_breakdown", eval_q1)
        self.assertIn("relevance", eval_q1["score_breakdown"])

    # 8. Test Re-evaluation and Attempt Tracking
    def test_08_re_evaluation_updates_latest_attempt(self):
        updated_answer = (
            "Updated response: In addition to mTLS and sidecars, we enforce Layer 7 authorization policies, "
            "rate limiting, and telemetry exports to Jaeger and Prometheus for complete observability."
        )
        res = client.post("/api/evaluate-answer", json={
            "interview_id": self.paper_id,
            "question_index": 1,
            "question": "Explain service mesh mTLS traffic encryption at scale.",
            "candidate_answer": updated_answer,
            "role": "Senior Cloud Architect"
        }, headers=self.auth_headers_1)
        self.assertEqual(res.status_code, 200)

        # Verify that retrieval returns the updated attempt
        get_res = client.get(f"/api/history/{self.paper_id}/evaluations", headers=self.auth_headers_1)
        self.assertEqual(get_res.status_code, 200)
        data = get_res.json()
        self.assertEqual(data["evaluations"]["1"]["candidate_answer"], updated_answer)

    # 9. Test Cross-User Protection on History Retrieval
    def test_09_cross_user_evaluation_retrieval_forbidden(self):
        res = client.get(f"/api/history/{self.paper_id}/evaluations", headers=self.auth_headers_2)
        self.assertEqual(res.status_code, 403)

    # 10. Test Contextual Fallback Engine Direct Unit Test
    def test_10_contextual_evaluation_fallback_engine(self):
        q = "How do you optimize React rendering performance in large applications?"
        ans = (
            "We optimize performance by using React.memo for pure components, useCallback and useMemo "
            "to prevent unnecessary re-computations, and virtualization with react-window for large data tables. "
            "We also implement route-based code splitting using React.lazy and Suspense."
        )
        fb = build_contextual_evaluation_fallback(
            question=q,
            candidate_answer=ans,
            role="Staff Frontend Engineer",
            skills=["React", "TypeScript", "Performance"],
            difficulty="Hard",
            reference_sample_answer="Use virtualization, memoization hooks, and bundle splitting."
        )

        self.assertGreaterEqual(fb["overall_score"], 0)
        self.assertLessEqual(fb["overall_score"], 20)
        self.assertEqual(
            fb["overall_score"],
            fb["score_breakdown"]["relevance"] +
            fb["score_breakdown"]["technical_accuracy"] +
            fb["score_breakdown"]["depth"] +
            fb["score_breakdown"]["communication"]
        )
        self.assertTrue(len(fb["strengths"]) >= 1)
        self.assertTrue(len(fb["improvements"]) >= 1)
        self.assertTrue(len(fb["missing_key_points"]) >= 1)
        self.assertTrue(len(fb["suggested_answer"]) >= 20)
        self.assertTrue(len(fb["next_practice_steps"]) >= 1)

    # 11. Test Standalone Evaluation (Without interview_id)
    def test_11_standalone_evaluation_without_interview_id(self):
        payload = {
            "question": "What is the CAP theorem and how does DynamoDB address it?",
            "candidate_answer": (
                "The CAP theorem states that a distributed system can only provide two of Consistency, "
                "Availability, and Partition tolerance simultaneously. DynamoDB prioritizes Availability and "
                "Partition tolerance, offering tunable eventual consistency or strongly consistent reads via single-region primaries."
            ),
            "role": "Distributed Systems Engineer",
            "skills": ["DynamoDB", "NoSQL", "Distributed Systems"]
        }
        res = client.post("/api/evaluate-answer", json=payload, headers=self.auth_headers_1)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("overall_score", data)
        self.assertGreaterEqual(data["overall_score"], 10)

    # 12. Test Database Migration Idempotency
    def test_12_migration_idempotency(self):
        # Run migration multiple times on SQLite
        _run_migration_candidate_answer_attempts("sqlite")
        _run_migration_candidate_answer_attempts("sqlite")

        # Verify table and columns exist
        insp = inspect(engine)
        self.assertTrue(insp.has_table("candidate_answer_attempts"))
        cols = {col["name"]: col for col in insp.get_columns("candidate_answer_attempts")}

        self.assertIn("id", cols)
        self.assertIn("user_id", cols)
        self.assertIn("interview_id", cols)
        self.assertIn("question_index", cols)
        self.assertIn("question_text", cols)
        self.assertIn("candidate_answer", cols)
        self.assertIn("evaluation_feedback", cols)
        self.assertIn("overall_score", cols)

    # 13. Test Frontend UI Syntax and Integration in Interview-studio.html
    def test_13_frontend_ui_elements_in_interview_studio(self):
        html_path = Path("Interview-studio.html")
        content = html_path.read_text(encoding="utf-8")

        self.assertIn("Practice Your Answer", content)
        self.assertIn("q-practice-answer-btn", content)
        self.assertIn("q-practice-panel", content)
        self.assertIn("Evaluate My Answer", content)
        self.assertIn("setupPracticeAnswer", content)
        self.assertIn("fetchAndHydrateSavedEvaluations", content)
        self.assertIn("api/evaluate-answer", content)
        self.assertIn("api/history/", content)


if __name__ == "__main__":
    unittest.main()
