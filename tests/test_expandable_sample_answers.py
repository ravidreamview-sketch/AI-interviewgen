import unittest
import json
from pathlib import Path
from fastapi.testclient import TestClient
from app.main import app
from app.services import generate_sample_answer, build_contextual_sample_answer
from app.database import SessionLocal
from app.db_models import UserAccount, InterviewHistory
from app.security import create_access_token


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
                "user research"
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
                "declarative"
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

    # 5. Test Question Generation /api/generate Returns Enriched Sample Answers
    def test_05_api_generate_includes_sample_answers(self):
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

        for item in data["questions_details"]:
            self.assertIn("id", item)
            self.assertIn("question", item)
            self.assertIn("model_answer", item)
            self.assertIn("sample_answer", item)
            self.assertIn("key_points", item)
            self.assertIn("practical_example", item)
            # Ensure sample_answer is populated and relevant
            self.assertTrue(len(item["sample_answer"]) > 30)
            self.assertIsInstance(item["key_points"], list)
            self.assertGreaterEqual(len(item["key_points"]), 3)

    # 6. Test /generate Alias Route Also Returns Enriched Sample Answers
    def test_06_generate_alias_includes_sample_answers(self):
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
        for item in data["questions_details"]:
            self.assertTrue(len(item["sample_answer"]) > 30)
            self.assertGreaterEqual(len(item["key_points"]), 3)

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


# 10. Test Database Persistence of Sample Answers in questions_payload
    def test_10_database_persistence_of_sample_answers(self):
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

        # Directly query the database
        db = SessionLocal()
        row = db.query(InterviewHistory).filter(InterviewHistory.id == paper_id).first()
        self.assertIsNotNone(row)
        self.assertIsNotNone(row.questions_payload)
        self.assertIn("sample_answer", row.questions_payload)
        
        parsed_payload = json.loads(row.questions_payload)
        self.assertEqual(len(parsed_payload), 3)
        for q in parsed_payload:
            self.assertIn("sample_answer", q)
            self.assertIn("key_points", q)
            self.assertIn("practical_example", q)
            self.assertTrue(len(q["sample_answer"]) > 30)
            self.assertGreaterEqual(len(q["key_points"]), 3)
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
        original_details = gen_res.json()["questions_details"]

        # Retrieve through GET /api/history/{id}
        detail_res = client.get(f"/api/history/{paper_id}", headers=self.auth_headers)
        self.assertEqual(detail_res.status_code, 200)
        detail_data = detail_res.json()

        self.assertIn("questions_details", detail_data)
        self.assertEqual(len(detail_data["questions_details"]), 2)
        self.assertEqual(detail_data["questions_details"][0]["sample_answer"], original_details[0]["sample_answer"])
        self.assertEqual(detail_data["questions_details"][0]["key_points"], original_details[0]["key_points"])

        # Also retrieve via list GET /api/history
        list_res = client.get("/api/history", headers=self.auth_headers)
        self.assertEqual(list_res.status_code, 200)
        found = next((item for item in list_res.json() if item["id"] == paper_id), None)
        self.assertIsNotNone(found)
        self.assertIn("questions_details", found)
        self.assertEqual(found["questions_details"][0]["sample_answer"], original_details[0]["sample_answer"])

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


if __name__ == "__main__":
    unittest.main()

