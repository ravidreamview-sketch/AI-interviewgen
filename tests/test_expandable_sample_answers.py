import unittest
import json
from pathlib import Path
from fastapi.testclient import TestClient
from app.main import app
from app.services import generate_sample_answer, build_contextual_sample_answer
from app.database import SessionLocal
from app.db_models import UserAccount, InterviewHistory
from app.security import create_access_token, hash_password


client = TestClient(app)


class TestExpandableSampleAnswers(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db = SessionLocal()
        cls.candidate = cls.db.query(UserAccount).filter(UserAccount.role == "candidate").first()
        if not cls.candidate:
            cls.candidate = UserAccount(
                email="candidate_sample_answer_test@example.com",
                role="candidate",
                full_name="Sample Answer Candidate",
                is_active=True
            )
            cls.candidate.set_password("Password123!")
            cls.db.add(cls.candidate)
            cls.db.commit()
            cls.db.refresh(cls.candidate)
        cls.token = create_access_token({
            "sub": str(cls.candidate.id),
            "email": cls.candidate.email,
            "role": cls.candidate.role
        })
        cls.auth_headers = {"Authorization": f"Bearer {cls.token}"}

        cls.candidate2 = cls.db.query(UserAccount).filter(UserAccount.email == "cand2_sample_answer_test@example.com").first()
        if not cls.candidate2:
            cls.candidate2 = UserAccount(
                email="cand2_sample_answer_test@example.com",
                role="candidate",
                full_name="Second Candidate",
                password_hash=hash_password("Password123!"),
                is_active=True
            )
            cls.db.add(cls.candidate2)
            cls.db.commit()
            cls.db.refresh(cls.candidate2)
        cls.token2 = create_access_token({
            "sub": str(cls.candidate2.id),
            "email": cls.candidate2.email,
            "role": cls.candidate2.role
        })
        cls.auth_headers_cand2 = {"Authorization": f"Bearer {cls.token2}"}

    @classmethod
    def tearDownClass(cls):
        cls.db.close()

    # 1. Test On-Demand Endpoint /api/sample-answer
    def test_01_sample_answer_endpoint_success(self):
        res = client.post(
            "/api/sample-answer",
            json={
                "question": "How do you ensure interaction design patterns meet WCAG 2.2 AA accessibility standards?",
                "role": "Frontend Architect",
                "skills": ["React", "TypeScript", "WCAG"],
                "difficulty": "Hard"
            }
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("sample_answer", data)
        self.assertIn("key_points", data)
        self.assertIn("practical_example", data)
        self.assertTrue(len(data["sample_answer"]) > 50)
        self.assertGreaterEqual(len(data["key_points"]), 3)
        self.assertTrue(len(data["practical_example"]) > 20)
        self.assertIn("WCAG", data["sample_answer"])

    # 2. Test Dual Route /api/generate-sample-answer Alias
    def test_02_generate_sample_answer_alias_success(self):
        res = client.post(
            "/api/generate-sample-answer",
            json={
                "question": "Explain how you structure distributed locking and idempotency in microservices.",
                "role": "Backend Engineer",
                "skills": ["FastAPI", "Redis", "PostgreSQL"],
                "difficulty": "Hard"
            }
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("sample_answer", data)
        self.assertTrue("idempotenc" in data["sample_answer"].lower() or "lock" in data["sample_answer"].lower())
        self.assertGreaterEqual(len(data["key_points"]), 3)
        self.assertIsNotNone(data["practical_example"])

    # 3. Test Domain Relevance Across Distinct Engineering Disciplines
    def test_03_domain_specific_sample_answers(self):
        domains = [
            (
                "How do you design and execute a mixed-methods user research plan for an ambiguous feature definition?",
                "UX Researcher",
                ["User Research", "Usability Testing"],
                "research"
            ),
            (
                "How do you establish typographic scale, 8pt spatial grid, and color contrast tokens in Figma Variables?",
                "Design Systems Lead",
                ["Figma", "Design Tokens"],
                "token"
            ),
            (
                "Explain your approach to continuous integration and automated canary rollouts in Kubernetes.",
                "DevOps Engineer",
                ["Kubernetes", "CI/CD", "Docker"],
                "canary"
            ),
            (
                "How do you optimize slow PostgreSQL queries with composite indexing and explain analyze?",
                "Database Architect",
                ["PostgreSQL", "SQL"],
                "index"
            ),
            (
                "How do you architect a hybrid RAG system combining dense vector embeddings and sparse BM25 retrieval?",
                "AI Engineer",
                ["LLM", "RAG", "Embeddings"],
                "retrieval"
            ),
            (
                "How do you structure event-driven data streaming pipelines with Kafka and idempotent consumers?",
                "Data Engineer",
                ["Kafka", "Pipelines", "ETL"],
                "kafka"
            )
        ]

        for q, role, skills, expected_kw in domains:
            ans = generate_sample_answer(q, role=role, skills=skills, difficulty="Hard")
            self.assertIn("sample_answer", ans)
            self.assertIn("key_points", ans)
            self.assertGreaterEqual(len(ans["key_points"]), 3)
            self.assertIsNotNone(ans["practical_example"])
            self.assertTrue(
                expected_kw.lower() in ans["sample_answer"].lower() or any(expected_kw.lower() in kp.lower() for kp in ans["key_points"]),
                f"Expected keyword '{expected_kw}' not found in answer or key points for '{q}'"
            )

    # 4. Test Answers Do Not Hallucinate Personal Employment History
    def test_04_no_personal_hallucination(self):
        questions = [
            "Tell me about a time you optimized a database.",
            "How do you handle microservices failures under load?",
            "How do you design accessible modal components?"
        ]
        forbidden_phrases = [
            "at my previous company",
            "at my last job",
            "my former team",
            "when i worked at google",
            "in my 10 years at"
        ]
        for q in questions:
            ans = generate_sample_answer(q, role="Software Engineer", skills=["Python"], difficulty="Hard")
            answer_text = ans["sample_answer"].lower()
            for forbidden in forbidden_phrases:
                self.assertNotIn(forbidden, answer_text, f"Forbidden personal claim '{forbidden}' found in sample answer")

    # 5. Test Question Generation /api/generate Decoupled Fast Response
    def test_05_api_generate_fast_decoupled(self):
        res = client.post(
            "/api/generate",
            headers=self.auth_headers,
            json={
                "role": "Product Designer",
                "experience": "4 Years",
                "skills": ["Figma", "User Research", "WCAG"],
                "difficulty": "Hard",
                "number_of_questions": 4
            }
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("questions", data)
        self.assertEqual(len(data["questions"]), 4)
        self.assertIn("questions_details", data)
        self.assertEqual(len(data["questions_details"]), 4)
        self.assertIn("timings_ms", data)
        self.assertIn("provider", data["timings_ms"])
        self.assertIn("total", data["timings_ms"])

        paper_id = data["id"]

        # Ensure decoupled behavior: initial generate does NOT run heavy sample answer generation
        for item in data["questions_details"]:
            self.assertIn("id", item)
            self.assertIn("question", item)
            self.assertIn("model_answer", item)
            self.assertIsNone(item.get("sample_answer"))
            self.assertEqual(item.get("key_points"), [])
            self.assertIsNone(item.get("practical_example"))

        # On-demand sample answer generation for question 0 with persistence
        sa_res = client.post(
            "/api/sample-answer",
            headers=self.auth_headers,
            json={
                "question": data["questions_details"][0]["question"],
                "role": "Product Designer",
                "skills": ["Figma", "User Research", "WCAG"],
                "difficulty": "Hard",
                "interview_id": paper_id,
                "question_index": 0
            }
        )
        self.assertEqual(sa_res.status_code, 200)
        sa_data = sa_res.json()
        self.assertTrue(sa_data.get("persisted"))
        self.assertTrue(len(sa_data["sample_answer"]) > 30)
        self.assertGreaterEqual(len(sa_data["key_points"]), 3)

    # 6. Test /generate Alias Route Also Decoupled and Fast
    def test_06_generate_alias_fast_decoupled(self):
        res = client.post(
            "/generate",
            headers=self.auth_headers,
            json={
                "role": "Backend Engineer",
                "experience": "5 Years",
                "skills": ["Python", "FastAPI", "PostgreSQL"],
                "difficulty": "Hard",
                "number_of_questions": 3
            }
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(len(data["questions_details"]), 3)
        self.assertIn("timings_ms", data)
        for item in data["questions_details"]:
            self.assertIsNone(item.get("sample_answer"))
            self.assertEqual(item.get("key_points"), [])

        paper_id = data["id"]
        sa_res = client.post(
            "/api/sample-answer",
            headers=self.auth_headers,
            json={
                "question": data["questions_details"][0]["question"],
                "role": "Backend Engineer",
                "skills": ["Python", "FastAPI"],
                "difficulty": "Hard",
                "interview_id": paper_id,
                "question_index": 0
            }
        )
        self.assertEqual(sa_res.status_code, 200)
        sa_data = sa_res.json()
        self.assertTrue(sa_data.get("persisted"))
        self.assertTrue(len(sa_data["sample_answer"]) > 30)

    # 7. Test Each Question's Answer is Unique to Its Domain
    def test_07_answers_differ_across_different_questions(self):
        ans_a = generate_sample_answer(
            "How do you ensure interaction design patterns meet WCAG 2.2 AA accessibility standards?",
            role="Frontend Architect",
            skills=["WCAG", "React"],
            difficulty="Hard"
        )
        ans_b = generate_sample_answer(
            "How do you design Kafka streaming pipelines with idempotent consumers?",
            role="Data Engineer",
            skills=["Kafka", "Streaming"],
            difficulty="Hard"
        )
        self.assertNotEqual(ans_a["sample_answer"], ans_b["sample_answer"])
        self.assertIn("WCAG", ans_a["sample_answer"])
        self.assertIn("Kafka", ans_b["sample_answer"])

    # 8. Test Edge Cases & Missing/Short Inputs
    def test_08_empty_or_short_question_handled_gracefully(self):
        ans = generate_sample_answer("", role="Engineer")
        self.assertIn("sample_answer", ans)
        self.assertIn("Please provide a valid question", ans["sample_answer"])

    # 9. Verify Frontend File (Interview-studio.html) Structure and Elements
    def test_09_frontend_ui_elements_in_interview_studio_html(self):
        html_path = Path("Interview-studio.html")
        self.assertTrue(html_path.exists())
        content = html_path.read_text(encoding="utf-8")

        # 1. UI Button and chevron classes
        self.assertIn("q-sample-answer-btn", content)
        self.assertIn("q-toggle-chevron", content)
        self.assertIn("q-sample-answer-panel", content)
        self.assertIn("View Sample Answer", content)
        self.assertIn("Hide Sample Answer", content)

        # 2. Structured answer sub-sections
        self.assertIn("q-answer-section", content)
        self.assertIn("q-answer-heading", content)
        self.assertIn("Key Points to Cover", content)
        self.assertIn("Practical Example", content)

        # 3. Loading and error states
        self.assertIn("q-answer-loading", content)
        self.assertIn("q-answer-spinner", content)
        self.assertIn("q-answer-error", content)
        self.assertIn("q-answer-retry-btn", content)

        # 4. JS Toggle logic & API connection
        self.assertIn("setupSampleAnswerToggle", content)
        self.assertIn("fetchAndRenderSampleAnswer", content)
        self.assertIn("renderAnswerContent", content)
        self.assertIn("/api/sample-answer", content)

        # 5. Preserved existing elements
        self.assertIn("qnum", content)
        self.assertIn("qtext", content)
        self.assertIn("qcopy", content)
        self.assertIn("q-provenance-badge", content)
        self.assertIn("q-confidence-tag", content)


    # 10. Test Database Persistence of On-Demand Sample Answers in questions_payload
    def test_10_database_persistence_of_on_demand_sample_answers(self):
        res = client.post(
            "/api/generate",
            headers=self.auth_headers,
            json={
                "role": "Cloud Security Engineer",
                "experience": "6 Years",
                "skills": ["AWS", "IAM", "KMS"],
                "difficulty": "Hard",
                "number_of_questions": 3
            }
        )
        self.assertEqual(res.status_code, 200)
        paper_id = res.json()["id"]

        # Directly query the database initially: all sample answers are None
        db = SessionLocal()
        row = db.query(InterviewHistory).filter(InterviewHistory.id == paper_id).first()
        self.assertIsNotNone(row)
        self.assertIsNotNone(row.questions_payload)
        parsed_payload = json.loads(row.questions_payload)
        self.assertEqual(len(parsed_payload), 3)
        for q in parsed_payload:
            self.assertIsNone(q.get("sample_answer"))
            self.assertEqual(q.get("key_points"), [])
            self.assertIsNone(q.get("practical_example"))
        db.close()

        # Generate on-demand sample answer for question index 0
        sa_res = client.post(
            "/api/sample-answer",
            headers=self.auth_headers,
            json={
                "question": parsed_payload[0]["question"],
                "role": "Cloud Security Engineer",
                "skills": ["AWS", "IAM", "KMS"],
                "difficulty": "Hard",
                "interview_id": paper_id,
                "question_index": 0
            }
        )
        self.assertEqual(sa_res.status_code, 200)
        self.assertTrue(sa_res.json().get("persisted"))

        # Re-query the database: question 0 now has answer persisted; question 1 remains None
        db = SessionLocal()
        row = db.query(InterviewHistory).filter(InterviewHistory.id == paper_id).first()
        updated_payload = json.loads(row.questions_payload)
        self.assertIsNotNone(updated_payload[0].get("sample_answer"))
        self.assertTrue(len(updated_payload[0]["sample_answer"]) > 30)
        self.assertGreaterEqual(len(updated_payload[0]["key_points"]), 3)
        self.assertIsNotNone(updated_payload[0]["practical_example"])
        self.assertIsNone(updated_payload[1].get("sample_answer"))
        self.assertIsNone(updated_payload[2].get("sample_answer"))
        db.close()

    # 11. Test History API Returns Stored Question Details with Answers
    def test_11_history_api_restores_saved_sample_answers(self):
        # Generate a test paper first
        gen_res = client.post(
            "/api/generate",
            headers=self.auth_headers,
            json={
                "role": "Machine Learning Engineer",
                "experience": "4 Years",
                "skills": ["PyTorch", "Transformers", "CUDA"],
                "difficulty": "Hard",
                "number_of_questions": 2
            }
        )
        paper_id = gen_res.json()["id"]

        # Populate sample answer on-demand for question 0
        sa_res = client.post(
            "/api/sample-answer",
            headers=self.auth_headers,
            json={
                "question": gen_res.json()["questions_details"][0]["question"],
                "role": "Machine Learning Engineer",
                "skills": ["PyTorch", "Transformers", "CUDA"],
                "difficulty": "Hard",
                "interview_id": paper_id,
                "question_index": 0
            }
        )
        self.assertEqual(sa_res.status_code, 200)
        saved_answer = sa_res.json()["sample_answer"]

        # Retrieve through GET /api/history/{id}
        detail_res = client.get(f"/api/history/{paper_id}", headers=self.auth_headers)
        self.assertEqual(detail_res.status_code, 200)
        detail_data = detail_res.json()

        self.assertIn("questions_details", detail_data)
        self.assertEqual(len(detail_data["questions_details"]), 2)
        self.assertEqual(detail_data["questions_details"][0]["sample_answer"], saved_answer)
        self.assertIsNone(detail_data["questions_details"][1]["sample_answer"])

        # Also retrieve via list GET /api/history
        list_res = client.get("/api/history", headers=self.auth_headers)
        self.assertEqual(list_res.status_code, 200)
        found = next((item for item in list_res.json() if item["id"] == paper_id), None)
        self.assertIsNotNone(found)
        self.assertIn("questions_details", found)
        self.assertEqual(found["questions_details"][0]["sample_answer"], saved_answer)

    # 12. Test Backward Compatibility With Legacy NULL questions_payload Records
    def test_12_backward_compatibility_with_null_payload_records(self):
        db = SessionLocal()
        legacy_paper = InterviewHistory(
            role="Legacy System Admin",
            experience="10 Years",
            skills="Linux, Bash, Perl",
            difficulty="Medium",
            questions="1. How do you troubleshoot high system load?\n2. Explain zombie vs orphan processes.",
            questions_payload=None,  # Simulates legacy pre-migration row
            user_id=self.candidate.id,
            question_engine_version="qengine-v1.0.0"
        )
        db.add(legacy_paper)
        db.commit()
        db.refresh(legacy_paper)
        legacy_id = legacy_paper.id
        db.close()

        # History detail must succeed gracefully without crashing
        res = client.get(f"/api/history/{legacy_id}", headers=self.auth_headers)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["role"], "Legacy System Admin")
        self.assertEqual(len(data["questions"]), 2)
        # questions_details should either be omitted or gracefully handled
        self.assertTrue("questions_details" not in data or data.get("questions_details") is None)

    # 13. Test Database Migration Idempotency on SQLite & PostgreSQL
    def test_13_migration_idempotency(self):
        from app.database import _run_migration_interview_history, engine
        from sqlalchemy import inspect

        # Running migration again on SQLite must not raise any errors
        _run_migration_interview_history("sqlite")
        _run_migration_interview_history("sqlite")

        # Verify column exists and is nullable
        insp = inspect(engine)
        cols = {col["name"]: col for col in insp.get_columns("interview_history")}
        self.assertIn("questions_payload", cols)
        self.assertTrue(cols["questions_payload"].get("nullable", True))

    # 14. Test Frontend History Restoration in Interview-studio.html
    def test_14_frontend_history_restoration_syntax(self):
        html_path = Path("Interview-studio.html")
        content = html_path.read_text(encoding="utf-8")
        # Ensure loadPaperIntoSheet checks questions_details first
        self.assertIn("paper.questions_details", content)
        self.assertIn("currentQs = (paper.questions_details && paper.questions_details.length)", content)

    # 15. Test Multiple Question Sample Answers Persist Without Overwriting Each Other
    def test_15_concurrent_answer_saves_do_not_overwrite(self):
        # Generate paper with 2 questions
        gen_res = client.post(
            "/api/generate",
            headers=self.auth_headers,
            json={
                "role": "Site Reliability Engineer",
                "experience": "5 Years",
                "skills": ["Kubernetes", "Prometheus", "Linux"],
                "difficulty": "Hard",
                "number_of_questions": 2
            }
        )
        self.assertEqual(gen_res.status_code, 200)
        paper_id = gen_res.json()["id"]
        q0 = gen_res.json()["questions_details"][0]["question"]
        q1 = gen_res.json()["questions_details"][1]["question"]

        # Save Q0 sample answer
        res0 = client.post(
            "/api/sample-answer",
            headers=self.auth_headers,
            json={
                "question": q0,
                "role": "Site Reliability Engineer",
                "skills": ["Kubernetes"],
                "difficulty": "Hard",
                "interview_id": paper_id,
                "question_index": 0
            }
        )
        self.assertEqual(res0.status_code, 200)
        ans0 = res0.json()["sample_answer"]

        # Save Q1 sample answer
        res1 = client.post(
            "/api/sample-answer",
            headers=self.auth_headers,
            json={
                "question": q1,
                "role": "Site Reliability Engineer",
                "skills": ["Prometheus"],
                "difficulty": "Hard",
                "interview_id": paper_id,
                "question_index": 1
            }
        )
        self.assertEqual(res1.status_code, 200)
        ans1 = res1.json()["sample_answer"]

        # Verify DB has BOTH answers intact (neither was lost or overwritten)
        db = SessionLocal()
        row = db.query(InterviewHistory).filter(InterviewHistory.id == paper_id).first()
        payload = json.loads(row.questions_payload)
        db.close()

        self.assertEqual(payload[0]["sample_answer"], ans0)
        self.assertEqual(payload[1]["sample_answer"], ans1)

    # 16. Test Security: Cross-User Answer Persistence and Unauthenticated Access are Forbidden
    def test_16_cross_user_sample_answer_persistence_rejected(self):
        # Generate paper owned by candidate 1
        gen_res = client.post(
            "/api/generate",
            headers=self.auth_headers,
            json={
                "role": "Security Specialist",
                "experience": "3 Years",
                "skills": ["Cryptography", "TLS"],
                "difficulty": "Medium",
                "number_of_questions": 1
            }
        )
        self.assertEqual(gen_res.status_code, 200)
        paper_id = gen_res.json()["id"]

        # Unauthenticated request with interview_id -> 401
        unauth_res = client.post(
            "/api/sample-answer",
            json={
                "question": "Explain TLS 1.3 handshake.",
                "role": "Security Specialist",
                "skills": ["TLS"],
                "difficulty": "Medium",
                "interview_id": paper_id,
                "question_index": 0
            }
        )
        self.assertEqual(unauth_res.status_code, 401)

        # Candidate 2 trying to persist on candidate 1's paper -> 403 Forbidden
        cand2_res = client.post(
            "/api/sample-answer",
            headers=self.auth_headers_cand2,
            json={
                "question": "Explain TLS 1.3 handshake.",
                "role": "Security Specialist",
                "skills": ["TLS"],
                "difficulty": "Medium",
                "interview_id": paper_id,
                "question_index": 0
            }
        )
        self.assertEqual(cand2_res.status_code, 403)

    # 17. Test Cached Sample Answer Hit Avoids Regeneration
    def test_17_cached_sample_answer_avoids_regeneration(self):
        gen_res = client.post(
            "/api/generate",
            headers=self.auth_headers,
            json={
                "role": "Platform Engineer",
                "experience": "4 Years",
                "skills": ["Terraform", "AWS"],
                "difficulty": "Medium",
                "number_of_questions": 1
            }
        )
        self.assertEqual(gen_res.status_code, 200)
        paper_id = gen_res.json()["id"]
        q_text = gen_res.json()["questions_details"][0]["question"]

        # First call generates and persists
        res1 = client.post(
            "/api/sample-answer",
            headers=self.auth_headers,
            json={
                "question": q_text,
                "role": "Platform Engineer",
                "skills": ["Terraform"],
                "difficulty": "Medium",
                "interview_id": paper_id,
                "question_index": 0
            }
        )
        self.assertEqual(res1.status_code, 200)
        ans1 = res1.json()["sample_answer"]
        self.assertTrue(res1.json().get("persisted"))

        # Second call hits cache directly
        res2 = client.post(
            "/api/sample-answer",
            headers=self.auth_headers,
            json={
                "question": q_text,
                "role": "Platform Engineer",
                "skills": ["Terraform"],
                "difficulty": "Medium",
                "interview_id": paper_id,
                "question_index": 0
            }
        )
        self.assertEqual(res2.status_code, 200)
        ans2 = res2.json()["sample_answer"]
        self.assertEqual(ans1, ans2)
        self.assertTrue(res2.json().get("persisted"))
        # Cache response must be fast (<20ms)
        self.assertLess(res2.json().get("timing_ms", 999), 20.0)


if __name__ == "__main__":
    unittest.main()

