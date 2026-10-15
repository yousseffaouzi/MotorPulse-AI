"""MP-050 community onboarding and contribution-template contracts."""

from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class CommunityTemplateTests(unittest.TestCase):
    def test_issue_and_pull_request_templates_exist(self):
        for relative in (
            ".github/ISSUE_TEMPLATE/bug_report.yml",
            ".github/ISSUE_TEMPLATE/feature_request.yml",
            ".github/ISSUE_TEMPLATE/config.yml",
            ".github/PULL_REQUEST_TEMPLATE.md",
        ):
            with self.subTest(relative=relative):
                self.assertTrue((ROOT / relative).is_file())

    def test_bug_template_requests_reproduction_without_sensitive_data(self):
        text = (ROOT / ".github/ISSUE_TEMPLATE/bug_report.yml").read_text(
            encoding="utf-8"
        )
        for term in (
            "Python version",
            "Reproduction steps",
            "Expected behavior",
            "Actual behavior",
            "synthetic",
            "Do not include proprietary telemetry",
            "credentials",
            "physical equipment",
        ):
            with self.subTest(term=term):
                self.assertIn(term, text)

    def test_feature_template_preserves_project_scope_and_safety(self):
        text = (ROOT / ".github/ISSUE_TEMPLATE/feature_request.yml").read_text(
            encoding="utf-8"
        )
        for term in (
            "Problem or research need",
            "Acceptance evidence",
            "local-first",
            "synthetic",
            "No PLC",
            "no remote control",
            "industrial guarantee",
        ):
            with self.subTest(term=term):
                self.assertIn(term, text)

    def test_pull_request_template_requires_quality_and_claim_checks(self):
        text = (ROOT / ".github/PULL_REQUEST_TEMPLATE.md").read_text(encoding="utf-8")
        for term in (
            "python -m unittest discover -s tests -v",
            "Documentation impact",
            "Data/provenance impact",
            "Security/local-first impact",
            "No real-world performance claim",
            "No third-party raw or derived dataset",
        ):
            with self.subTest(term=term):
                self.assertIn(term, text)

    def test_contributor_guide_links_current_safety_and_reproducibility_docs(self):
        text = (ROOT / "CONTRIBUTING.md").read_text(encoding="utf-8")
        for target in (
            "docs/INSTALL.md",
            "docs/TESTING.md",
            "docs/SECURITY.md",
            "docs/MODEL_CARDS.md",
            "docs/BENCHMARK.md",
            "docs/BEGINNER_TASKS.md",
        ):
            with self.subTest(target=target):
                self.assertIn(target, text)
        self.assertIn("Do not submit real or proprietary machine telemetry", text)
        self.assertIn("whole-run", text)
        self.assertIn("held-out", text)

    def test_beginner_tasks_are_current_safe_and_not_completed_milestones(self):
        path = ROOT / "docs" / "BEGINNER_TASKS.md"
        self.assertTrue(path.is_file())
        text = path.read_text(encoding="utf-8")
        for term in (
            "good first contribution",
            "documentation",
            "tests",
            "accessibility",
            "synthetic-only",
            "No hardware",
            "acceptance evidence",
        ):
            with self.subTest(term=term):
                self.assertIn(term, text)
        for completed in ("MP-006", "MP-017", "MP-018", "MP-019", "MP-020"):
            with self.subTest(completed=completed):
                self.assertNotIn(completed, text)


if __name__ == "__main__":
    unittest.main()
