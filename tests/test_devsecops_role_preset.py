import re
import unittest
from pathlib import Path

from app.models import InterviewRequest


WORKSPACE = Path(__file__).resolve().parents[1]
EXPECTED_PRESET_IDS = (
    "ux",
    "product",
    "uiux",
    "frontend",
    "backend",
    "genai",
    "devsecops_engineer",
    "technical_implementation_engineer",
)


class TestDevSecOpsRolePreset(unittest.TestCase):
    def read_registry(self, filename, registry_name, selected_id_name):
        html = (WORKSPACE / filename).read_text(encoding="utf-8")
        start = html.index(f"const {registry_name} = {{")
        end = html.index(f"let {selected_id_name} =", start)
        return html, html[start:end]

    def assert_devsecops_registration(self, registry):
        ids = re.findall(r'^\s+\w+: \{\s+id: "([^"]+)"', registry, re.MULTILINE)
        self.assertEqual(ids, list(EXPECTED_PRESET_IDS))
        self.assertEqual(registry.count('id: "devsecops_engineer"'), 1)
        self.assertEqual(registry.count('title: "DevSecOps Engineer"'), 1)
        self.assertIn(
            'keywordsLine1: "CI/CD • Kubernetes • DevSecOps Security •"',
            registry,
        )
        self.assertIn(
            'keywordsLine2: "GitOps • Terraform • Monitoring"',
            registry,
        )
        for skill in (
            "CI/CD (GitHub Actions)",
            "Kubernetes & Docker",
            "DevSecOps Security (Trivy & Vault)",
            "GitOps",
            "Terraform (IaC)",
            "Monitoring & Observability (Prometheus/Grafana)",
            "AWS / GCP Multi-Region",
            "Zero-Downtime Deployments",
        ):
            self.assertIn(skill, registry)
        self.assertNotIn('title: "DevOps Engineer"', registry)

    def test_studio_registry_and_selection_autofill(self):
        html, registry = self.read_registry(
            "Interview-studio.html",
            "ROLE_PRESETS_DATA",
            "selectedRoleId",
        )
        self.assert_devsecops_registration(registry)

        self.assertIn("const isSelected = role.id === selectedRoleId;", html)
        self.assertIn("selectedRoleId = roleId;", html)
        self.assertIn("const roleData = ROLE_PRESETS_DATA[roleId];", html)
        self.assertIn("selectedFocusAreas = new Set(roleData.defaultSelectedFocus", html)
        self.assertIn("$('#role').value = role.title;", html)
        self.assertIn("role: role,", html)
        self.assertIn("role_id: roleId,", html)

    def test_mock_registry_selection_and_existing_devops_question_bank(self):
        html, registry = self.read_registry(
            "Mock-interview.html",
            "MOCK_ROLE_PRESETS_DATA",
            "selectedMockRoleId",
        )
        self.assert_devsecops_registration(registry)

        self.assertIn("const isSelected = role.id === selectedMockRoleId;", html)
        self.assertIn("selectedMockRoleId = roleId;", html)
        self.assertIn("$('#mockRole').value = roleData.defaultRoleInput || roleData.title;", html)
        self.assertIn('rLower.includes(\'devsecops\') || rLower.includes(\'devops\')', html)
        self.assertIn(
            "How do you enforce DevSecOps principles, container vulnerability scanning (Trivy)",
            html,
        )
        self.assertIn("role: role,", html)
        self.assertIn("role_id: selectedPreset?.id,", html)

    def test_question_generation_request_accepts_the_selected_preset_id(self):
        request = InterviewRequest(
            role="DevSecOps Engineer",
            role_id="devsecops_engineer",
            skills=["Kubernetes & Docker", "Terraform (IaC)"],
        )
        self.assertEqual(request.role_id, "devsecops_engineer")
        self.assertIsNone(InterviewRequest(role="UX Designer").role_id)


if __name__ == "__main__":
    unittest.main()
