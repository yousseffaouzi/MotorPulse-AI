"""MP-051 release-preparation contracts; these tests do not create a Git tag."""

from __future__ import annotations

from pathlib import Path
import tomllib
import unittest


ROOT = Path(__file__).resolve().parents[1]


class ReleaseReadinessTests(unittest.TestCase):
    def test_candidate_version_is_semver_alpha_release(self):
        with (ROOT / "pyproject.toml").open("rb") as handle:
            project = tomllib.load(handle)["project"]
        self.assertEqual(project["version"], "0.1.0")
        self.assertIn("Development Status :: 3 - Alpha", project["classifiers"])
        self.assertNotIn("Development Status :: 2 - Pre-Alpha", project["classifiers"])

    def test_changelog_has_dated_010_entry_and_caveats(self):
        text = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
        for term in (
            "## [0.1.0] - 2026-10-16",
            "synthetic",
            "localhost",
            "492",
            "docs/BENCHMARK.md",
            "docs/MODEL_CARDS.md",
            "no RUL",
        ):
            with self.subTest(term=term):
                self.assertIn(term, text)

    def test_release_guide_requires_integrated_green_main_before_tag(self):
        text = (ROOT / "docs" / "RELEASE.md").read_text(encoding="utf-8")
        for term in (
            "v0.1.0",
            "main",
            "all six quality jobs",
            "python -m unittest discover -s tests -v",
            "docs/BENCHMARK.md",
            "docs/demo/benchmark-summary.svg",
            "git tag -a v0.1.0",
            "Do not tag a stacked feature branch",
        ):
            with self.subTest(term=term):
                self.assertIn(term, text)

    def test_release_guide_preserves_safety_and_data_boundaries(self):
        text = (ROOT / "docs" / "RELEASE.md").read_text(encoding="utf-8")
        for term in (
            "synthetic-only",
            "127.0.0.1",
            "No PLC",
            "no remote control",
            "not field performance",
            "IMS",
            "redistribution",
            "no RUL model",
        ):
            with self.subTest(term=term):
                self.assertIn(term, text)

    def test_readme_links_release_materials(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        for target in ("CHANGELOG.md", "docs/RELEASE.md", "docs/BENCHMARK.md"):
            with self.subTest(target=target):
                self.assertIn(target, readme)

    def test_tracker_does_not_claim_release_complete_before_tag(self):
        todo = (ROOT / "TODO.md").read_text(encoding="utf-8")
        pending = (
            "| MP-051 | TODO | P2 | Tag a usable release | SemVer, CHANGELOG, "
            "reproducible demo and honest release caveats |"
        )
        self.assertIn(pending, todo)
        self.assertNotIn("| MP-051 | DONE |", todo)


if __name__ == "__main__":
    unittest.main()
