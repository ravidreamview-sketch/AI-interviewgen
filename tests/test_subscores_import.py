"""
Regression Test Suite: SubScores Import Order and Annotation Evaluation
Verifies that:
1. `app.matching_service` imports cleanly without NameError: name 'SubScores' is not defined.
2. `SubScores` and `calculate_deterministic_score` are directly importable from `app.matching_service`.
3. `app.main` imports cleanly and initializes the FastAPI application.
4. `calculate_deterministic_score(SubScores(required_skills=80.0))` computes 80.0 correctly.
5. Function annotations for `calculate_deterministic_score` resolve properly under both eager and deferred evaluation.
"""

import sys
import unittest
from pydantic import BaseModel


class TestSubScoresImportRegression(unittest.TestCase):
    def test_01_matching_service_import_without_name_error(self):
        """Verifies app.matching_service imports cleanly without NameError."""
        # Force re-import check if already imported
        if "app.matching_service" in sys.modules:
            del sys.modules["app.matching_service"]

        try:
            import app.matching_service
            self.assertIsNotNone(app.matching_service)
        except NameError as e:
            self.fail(f"Importing app.matching_service raised NameError: {e}")

    def test_02_subscores_and_scoring_function_exported(self):
        """Verifies SubScores and calculate_deterministic_score are accessible from app.matching_service."""
        from app.matching_service import calculate_deterministic_score, SubScores

        self.assertTrue(issubclass(SubScores, BaseModel))
        self.assertTrue(callable(calculate_deterministic_score))

    def test_03_app_main_import_clean(self):
        """Verifies app.main imports cleanly without NameError or startup exception."""
        try:
            import app.main
            self.assertIsNotNone(app.main.app)
            self.assertEqual(app.main.app.title, "Ravi — AI Interview Question Generator API")
        except NameError as e:
            self.fail(f"Importing app.main raised NameError: {e}")

    def test_04_calculate_deterministic_score_computation(self):
        """Verifies calculate_deterministic_score calculates 80.0 for SubScores(required_skills=80.0)."""
        from app.matching_service import calculate_deterministic_score, SubScores

        sub_scores = SubScores(required_skills=80.0)
        score = calculate_deterministic_score(sub_scores)
        self.assertEqual(score, 80.0)

    def test_05_annotation_resolution(self):
        """Verifies type annotations on calculate_deterministic_score resolve to SubScores."""
        from app.matching_service import calculate_deterministic_score, SubScores

        annotations = calculate_deterministic_score.__annotations__
        self.assertIn("sub_scores", annotations)
        # Under __future__.annotations it is string 'SubScores', otherwise it is the class itself
        sub_type = annotations["sub_scores"]
        if isinstance(sub_type, str):
            self.assertEqual(sub_type, "SubScores")
        else:
            self.assertIs(sub_type, SubScores)

    def test_06_api_index_import_clean(self):
        """Verifies serverless entrypoint api.index imports app.matching_service and app without error."""
        try:
            import api.index
            self.assertIsNotNone(api.index.app)
        except NameError as e:
            self.fail(f"Importing api.index raised NameError: {e}")


if __name__ == "__main__":
    unittest.main()

