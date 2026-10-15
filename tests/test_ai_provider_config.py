import json
import os
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from pathlib import Path

from app.services import AIProviderError, generate_ai_questions, get_ai_provider_status


class TestAIProviderConfig(unittest.TestCase):
    def test_provider_status_prefers_gemini_without_exposing_keys(self):
        with patch.dict(
            os.environ,
            {"GEMINI_API_KEY": "gemini-secret", "GROQ_API_KEY": "groq-secret"},
            clear=True,
        ):
            self.assertEqual(get_ai_provider_status(), ("Gemini", True))

        with patch.dict(os.environ, {"GROQ_API_KEY": "groq-secret"}, clear=True):
            self.assertEqual(get_ai_provider_status(), ("Groq", True))

        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(get_ai_provider_status(), ("Not configured", False))

    def test_missing_provider_has_clear_error(self):
        with (
            patch.dict(os.environ, {}, clear=True),
            self.assertLogs("ravi.ai_provider", level="ERROR") as captured,
        ):
            with self.assertRaises(AIProviderError) as raised:
                generate_ai_questions("Help me prepare.")

        self.assertEqual(raised.exception.category, "not_configured")
        self.assertIn("GEMINI_API_KEY or GROQ_API_KEY", str(raised.exception))
        self.assertIn("required_key_present=NO", "\n".join(captured.output))

    def test_gemini_provider_returns_generated_text(self):
        response = MagicMock()
        response.__enter__.return_value.read.return_value = json.dumps({
            "candidates": [{"content": {"parts": [{"text": "Prepare concise examples."}]}}],
        }).encode("utf-8")

        with (
            patch.dict(os.environ, {"GEMINI_API_KEY": "gemini-secret"}, clear=True),
            patch("app.services.urllib.request.urlopen", return_value=response) as urlopen,
        ):
            result = generate_ai_questions("Help me prepare.")

        self.assertEqual(result, "Prepare concise examples.")
        request = urlopen.call_args.args[0]
        self.assertNotIn("gemini-secret", request.full_url)
        self.assertEqual(request.get_header("X-goog-api-key"), "gemini-secret")

    def test_groq_provider_returns_generated_text(self):
        client = MagicMock()
        client.chat.completions.create.return_value.choices = [
            SimpleNamespace(message=SimpleNamespace(content="Practice clear examples."))
        ]
        groq_module = SimpleNamespace(Groq=MagicMock(return_value=client))

        with (
            patch.dict(os.environ, {"GROQ_API_KEY": "groq-secret"}, clear=True),
            patch.dict(sys.modules, {"groq": groq_module}),
        ):
            result = generate_ai_questions("Help me prepare.")

        self.assertEqual(result, "Practice clear examples.")
        groq_module.Groq.assert_called_once_with(api_key="groq-secret")
        self.assertEqual(
            client.chat.completions.create.call_args.kwargs["model"],
            "openai/gpt-oss-120b",
        )

    def test_provider_failure_logs_no_api_key(self):
        api_key = "do-not-log-this-key"
        with (
            patch.dict(os.environ, {"GEMINI_API_KEY": api_key}, clear=True),
            patch(
                "app.services.urllib.request.urlopen",
                side_effect=RuntimeError(f"request URL included {api_key}"),
            ),
            self.assertLogs("ravi.ai_provider", level="WARNING") as captured,
        ):
            with self.assertRaises(AIProviderError) as raised:
                generate_ai_questions("Help me prepare.")

        self.assertEqual(raised.exception.category, "provider_error")
        self.assertNotIn(api_key, "\n".join(captured.output))

    def _groq_client_for_error(self, error):
        client = MagicMock()
        client.chat.completions.create.side_effect = error
        return client, SimpleNamespace(Groq=MagicMock(return_value=client))

    def test_groq_authentication_error_is_classified_without_leaking_key(self):
        api_key = "private-groq-key"

        class UnauthorizedError(Exception):
            status_code = 401

        client, groq_module = self._groq_client_for_error(UnauthorizedError(api_key))
        with (
            patch.dict(os.environ, {"GROQ_API_KEY": api_key}, clear=True),
            patch.dict(sys.modules, {"groq": groq_module}),
            self.assertLogs("ravi.ai_provider", level="WARNING") as captured,
        ):
            with self.assertRaises(AIProviderError) as raised:
                generate_ai_questions("Help me prepare.")

        self.assertEqual(raised.exception.status_code, 503)
        self.assertEqual(raised.exception.category, "authentication")
        self.assertNotIn(api_key, str(raised.exception) + "\n".join(captured.output))
        self.assertIn("status=401", "\n".join(captured.output))
        self.assertEqual(client.chat.completions.create.call_count, 2)

    def test_groq_rate_limit_is_classified(self):
        class RateLimitError(Exception):
            status_code = 429

        _, groq_module = self._groq_client_for_error(RateLimitError("rate limited"))
        with (
            patch.dict(os.environ, {"GROQ_API_KEY": "test-key"}, clear=True),
            patch.dict(sys.modules, {"groq": groq_module}),
            self.assertLogs("ravi.ai_provider", level="WARNING"),
        ):
            with self.assertRaises(AIProviderError) as raised:
                generate_ai_questions("Help me prepare.")

        self.assertEqual(raised.exception.status_code, 503)
        self.assertEqual(raised.exception.category, "rate_limit_or_quota")

    def test_groq_invalid_model_error_is_classified(self):
        class NotFoundError(Exception):
            status_code = 404

        _, groq_module = self._groq_client_for_error(NotFoundError("model not found"))
        with (
            patch.dict(os.environ, {"GROQ_API_KEY": "test-key"}, clear=True),
            patch.dict(sys.modules, {"groq": groq_module}),
            self.assertLogs("ravi.ai_provider", level="WARNING"),
        ):
            with self.assertRaises(AIProviderError) as raised:
                generate_ai_questions("Help me prepare.")

        self.assertEqual(raised.exception.status_code, 502)
        self.assertEqual(raised.exception.category, "model_or_request_configuration")

    def test_gemini_timeout_and_malformed_response_are_safe_errors(self):
        with (
            patch.dict(os.environ, {"GEMINI_API_KEY": "test-key"}, clear=True),
            patch("app.services.urllib.request.urlopen", side_effect=TimeoutError()),
            self.assertLogs("ravi.ai_provider", level="WARNING"),
        ):
            with self.assertRaises(AIProviderError) as raised:
                generate_ai_questions("Help me prepare.")
        self.assertEqual(raised.exception.status_code, 504)
        self.assertEqual(raised.exception.category, "timeout")

        response = MagicMock()
        response.__enter__.return_value.read.return_value = b"not-json"
        with (
            patch.dict(os.environ, {"GEMINI_API_KEY": "test-key"}, clear=True),
            patch("app.services.urllib.request.urlopen", return_value=response),
            self.assertLogs("ravi.ai_provider", level="WARNING"),
        ):
            with self.assertRaises(AIProviderError) as malformed:
                generate_ai_questions("Help me prepare.")
        self.assertEqual(malformed.exception.status_code, 502)
        self.assertEqual(malformed.exception.category, "malformed_response")

    def test_mock_interview_frontend_uses_ai_api_contract_without_offline_success(self):
        html_path = Path(__file__).parents[1] / "app" / "private_pages" / "Mock-interview.html"
        html = html_path.read_text(encoding="utf-8")
        self.assertIn("fetch('/api/generate'", html)
        self.assertIn("fetch('/api/interview/start'", html)
        self.assertIn("number_of_questions: targetCount", html)
        self.assertIn("interview_type: type", html)
        self.assertIn("X-AI-Error-Category", html)
        self.assertIn("AI question regeneration failed", html)
        handler_start = html.index("async function generateAndPreviewQuestions()")
        handler_end = html.index("// Render the Staged Questions", handler_start)
        generation_handler = html[handler_start:handler_end]
        self.assertNotIn("interviewQuestions = []", generation_handler)
        self.assertNotIn("renderPreviewQuestionsList();", generation_handler[generation_handler.index("} catch (err) {"):])
        self.assertNotIn("Using role offline synthesis", html)


if __name__ == "__main__":
    unittest.main()
