import unittest
from pathlib import Path
from unittest.mock import patch

from app.evaluator_service import evaluate_candidate_answer
from app.models import InterviewRequest
from app.prompts import (
    interview_prompt,
    technical_implementation_role_guidance,
)


class TestTechnicalImplementationRole(unittest.TestCase):
    def test_studio_registers_fresher_role_and_all_focus_areas(self):
        studio_html = (
            Path(__file__).resolve().parents[1] / "Interview-studio.html"
        ).read_text(encoding="utf-8")

        self.assertIn('id: "technical_implementation_engineer"', studio_html)
        self.assertIn('title: "Technical Implementation Engineer"', studio_html)
        self.assertIn(
            "SQL & Databases • APIs & Postman •",
            studio_html,
        )
        self.assertIn(
            "Integration • Testing • Troubleshooting • Technical Support",
            studio_html,
        )
        self.assertIn(
            "defaultExp: \"Intern / Fresher\"",
            studio_html,
        )
        for focus in (
            "SQL & Database Operations",
            "APIs & Postman",
            "Implementation & Integrations",
            "Testing & Quality Assurance",
            "Troubleshooting & Production Support",
            "Communication & Documentation",
        ):
            self.assertIn(focus, studio_html)

        mock_html = (
            Path(__file__).resolve().parents[1] / "Mock-interview.html"
        ).read_text(encoding="utf-8")
        self.assertIn('id: "technical_implementation_engineer"', mock_html)
        self.assertIn('defaultExp: "Fresher"', mock_html)
        self.assertIn(
            'defaultRoleInput: "Technical Implementation Engineer"',
            mock_html,
        )

    def test_initial_question_prompt_covers_role_skills_and_scenarios(self):
        prompt = interview_prompt(
            InterviewRequest(
                role="Technical Implementation Engineer",
                experience="Intern / Fresher",
                skills=[
                    "SQL & Database Operations",
                    "APIs & Postman",
                    "Implementation & Integrations",
                    "Testing & Quality Assurance",
                    "Troubleshooting & Production Support",
                    "Communication & Documentation",
                ],
                difficulty="Medium",
                number_of_questions=8,
            )
        )
        normalized_prompt = prompt.casefold()

        for topic in (
            "select, insert, update, delete",
            "inner/left",
            "count, sum, avg",
            "http vs https",
            "json and xml",
            "postman collections",
            "http 200",
            "http 401/500",
            "duplicate records",
            "environment-specific test failures",
            "hypothetical answers",
        ):
            self.assertIn(topic, normalized_prompt)

    def test_role_guidance_is_fresher_appropriate_and_role_scoped(self):
        guidance = technical_implementation_role_guidance(
            "Technical Implementation Engineer"
        )
        self.assertIn("Do not assume professional employment", guidance)
        self.assertIn("Accept well-reasoned hypothetical answers", guidance)
        self.assertIn("Accept equivalent correct SQL syntax", guidance)
        self.assertEqual(
            technical_implementation_role_guidance("Backend Developer"),
            "",
        )

    def test_evaluator_does_not_invent_fresher_experience_on_fallback(self):
        captured_prompt = []

        def unavailable_evaluator(prompt):
            captured_prompt.append(prompt)
            raise RuntimeError("evaluation provider unavailable")

        with patch(
            "app.evaluator_service.generate_ai_questions",
            side_effect=unavailable_evaluator,
        ):
            result = evaluate_candidate_answer(
                question="How would you investigate a transaction missing from a database?",
                answer="I would check the request ID, database filters, and environment.",
                role="Technical Implementation Engineer",
                seniority="Intern / Fresher",
            )

        self.assertIn("Do not assume professional employment", captured_prompt[0])
        self.assertEqual(result["overall_score"], 42)
        self.assertNotIn("In my previous role", result["model_answer"])
        self.assertIn("could not be verified", result["verdict_summary"])


if __name__ == "__main__":
    unittest.main()
