import json
import os
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.services import generate_ai_questions, get_ai_provider_status


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
            with self.assertRaisesRegex(
                RuntimeError,
                "AI provider is not configured.*GEMINI_API_KEY or GROQ_API_KEY",
            ):
                generate_ai_questions("Help me prepare.")

        self.assertIn("GEMINI_API_KEY or GROQ_API_KEY", "\n".join(captured.output))

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
        self.assertIn("key=gemini-secret", urlopen.call_args.args[0].full_url)

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
            with self.assertRaisesRegex(RuntimeError, "Configured AI provider request failed"):
                generate_ai_questions("Help me prepare.")

        self.assertNotIn(api_key, "\n".join(captured.output))


if __name__ == "__main__":
    unittest.main()
