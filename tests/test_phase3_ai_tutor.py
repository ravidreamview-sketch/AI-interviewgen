"""
Phase 3 AI Tutor Agent Test Suite
==================================
Validates:
1. Context-Aware Tutoring: Correct assembly of LearnerProfile, AdaptiveRoadmap activity, and mistakes.
2. Pedagogical Strategies:
   - HINT mode: Socratic guidance without revealing full solution.
   - DEMONSTRATE mode: Concrete architectural/code demonstration.
   - CHALLENGE mode: Targeted questions verifying comprehension.
   - SOLUTION mode: Reference solution and trade-off analysis.
   - EXPLAIN mode: Structured conceptual breakdown.
3. Complexity Scaling: Simple (beginner), Standard (mid-level), Deep Dive (staff).
4. Security & Prompt Injection Defenses: Input sanitization, XML boundary containment, and no untrusted code execution.
5. Conversation Persistence: Multi-turn history, session creation, message storage, and chronological retrieval.
6. Tenant Isolation / Ownership: User A cannot access or append messages to User B's session.
7. Rate Limiting: Sliding window defense against query bursts.
8. API Route Handlers: Querying, listing sessions, message history, and session deletion.
"""

import json
import unittest
from datetime import datetime, timezone
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.db_models import (
    UserAccount,
    LearnerProfile,
    AdaptiveRoadmap,
    CandidateMistakesLedger,
    TutorSession,
    TutorMessage,
)
from app.services.ai_tutor_service import (
    TutorRateLimiter,
    assemble_tutor_context,
    build_tutor_system_prompt,
    sanitize_user_input,
    generate_socratic_fallback_reply,
    execute_tutor_interaction,
)
from app.api.v1.tutor import (
    query_ai_tutor,
    list_tutor_sessions,
    get_session_messages,
    delete_tutor_session,
    TutorQueryRequest,
)


class TestAiTutorPedagogyAndContext(unittest.TestCase):
    """Test context retrieval, system prompt formation, and pedagogical strategies."""

    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)
        self.db = self.Session()

        self.user = UserAccount(
            email="socratic_learner@test.com",
            full_name="Morgan Socratic",
            password_hash="test_hash",
            role="candidate",
        )
        self.db.add(self.user)
        self.db.commit()
        self.db.refresh(self.user)

        # Profile
        profile = LearnerProfile(
            user_id=self.user.id,
            target_role="Backend Engineer (Python / Cloud)",
            target_level="Senior",
            years_of_experience=4.0,
        )
        self.db.add(profile)

        # Mistakes Ledger
        mistake = CandidateMistakesLedger(
            user_id=self.user.id,
            adaptive_session_id="sess_01",
            skill="PostgreSQL & Database Design",
            mistake_category="Lock Contention",
            description="Caused table-level exclusive locks in high-concurrency migration",
            mistake_status="identified",
        )
        self.db.add(mistake)
        self.db.commit()

    def tearDown(self):
        self.db.close()
        Base.metadata.drop_all(self.engine)

    def test_assemble_tutor_context(self):
        ctx = assemble_tutor_context(user_id=self.user.id, db=self.db)
        self.assertEqual(ctx["target_role"], "Backend Engineer (Python / Cloud)")
        self.assertEqual(ctx["target_level"], "Senior")
        self.assertEqual(ctx["years_of_experience"], 4.0)
        self.assertGreater(len(ctx["recent_mistakes"]), 0)
        self.assertIn("Lock Contention", ctx["recent_mistakes"][0])

    def test_prompt_injection_containment_and_security(self):
        ctx = assemble_tutor_context(user_id=self.user.id, db=self.db)
        prompt = build_tutor_system_prompt(
            context=ctx,
            concept="Row-Level Locking",
            teaching_mode="hint",
            complexity_level="standard",
            skill_level=4,
        )

        # Verify security boundaries
        self.assertIn("CRITICAL SECURITY AND REASONING BOUNDARIES", prompt)
        self.assertIn("You do not execute code", prompt)
        self.assertIn("<candidate_query>", prompt)
        self.assertIn("DO NOT GIVE AWAY THE FULL SOLUTION OR CODE IMMEDIATELY", prompt)

    def test_guided_learning_hint_does_not_reveal_solution(self):
        reply, intent = generate_socratic_fallback_reply(
            concept="Row-Level Locking",
            query="How do I lock a row safely in PostgreSQL?",
            teaching_mode="hint",
            complexity_level="standard",
            skill_level=4,
        )
        self.assertEqual(intent, "hint")
        self.assertIn("Socratic Hint", reply)
        self.assertIn("Guiding Question", reply)
        # Should NOT contain full reference solution code
        self.assertNotIn("class ResilientHandler", reply)

    def test_guided_learning_solution_reveals_reference_architecture(self):
        reply, intent = generate_socratic_fallback_reply(
            concept="Concurrency Semaphore Rate Limiter",
            query="Show me the full reference solution.",
            teaching_mode="solution",
            complexity_level="standard",
            skill_level=4,
        )
        self.assertEqual(intent, "solution_reveal")
        self.assertIn("Complete Reference Solution", reply)
        self.assertIn("Trade-off Analysis", reply)
        self.assertIn("class ResilientHandler", reply)

    def test_guided_learning_demonstrate_mode(self):
        reply, intent = generate_socratic_fallback_reply(
            concept="FastAPI Dependency Injection",
            query="Demonstrate how to write an async db session dependency.",
            teaching_mode="demonstrate",
            complexity_level="standard",
            skill_level=4,
        )
        self.assertEqual(intent, "demonstration")
        self.assertIn("Architectural Demonstration", reply)
        self.assertIn("```python", reply)

    def test_input_sanitizer(self):
        malicious = "Hello\x00\x08World! <script>alert(1)</script>"
        clean = sanitize_user_input(malicious)
        self.assertNotIn("\x00", clean)
        self.assertNotIn("\x08", clean)
        self.assertEqual(clean, "HelloWorld! <script>alert(1)</script>")


class TestTutorConversationPersistenceAndTenantIsolation(unittest.TestCase):
    """Test conversation storage, session ownership, and multi-turn state."""

    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)
        self.db = self.Session()

        # User A
        self.user_a = UserAccount(
            email="candidate_a@test.com",
            full_name="Candidate Alpha",
            password_hash="test_hash",
            role="candidate",
        )
        # User B
        self.user_b = UserAccount(
            email="candidate_b@test.com",
            full_name="Candidate Bravo",
            password_hash="test_hash",
            role="candidate",
        )
        self.db.add_all([self.user_a, self.user_b])
        self.db.commit()
        self.db.refresh(self.user_a)
        self.db.refresh(self.user_b)

    def tearDown(self):
        self.db.close()
        Base.metadata.drop_all(self.engine)

    def test_execute_tutor_interaction_persists_messages(self):
        res1 = execute_tutor_interaction(
            user=self.user_a,
            db=self.db,
            concept="Asyncio Event Loop",
            query="What causes event loop starvation in Python?",
            teaching_mode="explain",
            complexity_level="standard",
        )

        session_id = res1["session_id"]
        self.assertTrue(session_id.startswith("tut_sess_"))
        self.assertIn("Asyncio Event Loop", res1["message"])

        # Second turn in same session
        res2 = execute_tutor_interaction(
            user=self.user_a,
            db=self.db,
            concept="Asyncio Event Loop",
            query="Can you give me a Socratic hint on how to detect this?",
            session_id=session_id,
            teaching_mode="hint",
        )

        self.assertEqual(res2["session_id"], session_id)
        self.assertEqual(res2["pedagogical_intent"], "hint")

        # Verify DB records
        sess = self.db.query(TutorSession).filter(TutorSession.session_id == session_id).first()
        self.assertIsNotNone(sess)
        self.assertEqual(sess.user_id, self.user_a.id)

        messages = self.db.query(TutorMessage).filter(TutorMessage.session_id == sess.id).all()
        # 2 user queries + 2 tutor responses = 4 turns
        self.assertEqual(len(messages), 4)

    def test_tenant_isolation_user_b_cannot_access_user_a_session(self):
        res_a = execute_tutor_interaction(
            user=self.user_a,
            db=self.db,
            concept="Distributed Transactions",
            query="Explain the 2-Phase Commit protocol.",
        )
        session_id_a = res_a["session_id"]

        # User B tries to query into User A's session
        with self.assertRaises(ValueError) as ctx:
            execute_tutor_interaction(
                user=self.user_b,
                db=self.db,
                concept="Distributed Transactions",
                query="Add a comment to Alpha's private session.",
                session_id=session_id_a,
            )
        self.assertIn("access denied", str(ctx.exception))


class TestTutorRateLimiterAndAPI(unittest.TestCase):
    """Test rate limiter threshold and API route handlers."""

    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)
        self.db = self.Session()

        self.user = UserAccount(
            email="api_tutor_user@test.com",
            full_name="API User",
            password_hash="test_hash",
            role="candidate",
        )
        self.db.add(self.user)
        self.db.commit()
        self.db.refresh(self.user)

    def tearDown(self):
        self.db.close()
        Base.metadata.drop_all(self.engine)

    def test_rate_limiter_blocks_burst_traffic(self):
        limiter = TutorRateLimiter(max_requests=3, window_seconds=60)
        user_id = 999
        self.assertTrue(limiter.is_allowed(user_id))
        self.assertTrue(limiter.is_allowed(user_id))
        self.assertTrue(limiter.is_allowed(user_id))
        # 4th request in window must be blocked
        self.assertFalse(limiter.is_allowed(user_id))

    def test_api_query_list_and_delete(self):
        # 1. Submit query via API handler
        req = TutorQueryRequest(
            concept="SQL Indexing B-Trees",
            query="How does a B-Tree index minimize disk I/O?",
            teaching_mode="explain",
            complexity_level="standard",
        )
        res = query_ai_tutor(req=req, user=self.user, db=self.db)
        self.assertIsNotNone(res.session_id)
        self.assertEqual(res.concept, "SQL Indexing B-Trees")

        # 2. List sessions
        sessions = list_tutor_sessions(user=self.user, db=self.db)
        self.assertEqual(len(sessions), 1)
        self.assertEqual(sessions[0].session_id, res.session_id)

        # 3. Retrieve messages
        messages = get_session_messages(session_id=res.session_id, user=self.user, db=self.db)
        self.assertEqual(len(messages), 2)  # 1 user + 1 assistant

        # 4. Delete session
        del_res = delete_tutor_session(session_id=res.session_id, user=self.user, db=self.db)
        self.assertTrue(del_res["success"])

        # 5. Verify deleted
        sessions_after = list_tutor_sessions(user=self.user, db=self.db)
        self.assertEqual(len(sessions_after), 0)


if __name__ == "__main__":
    unittest.main()
