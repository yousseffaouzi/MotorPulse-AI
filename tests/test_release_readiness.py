"""MP-051 release-candidate contracts; preparation must never imply a published tag."""

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

    def test_changelog_has_dated_010_entry_current_counts_and_caveats(self):
        text = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
        for term in (
            "## [0.1.0] - 2026-10-16",
            "synthetic",
            "localhost",
            "526",
            "CWRU",
            "container",
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
            "all seven quality jobs",
            "526",
            "python -m unittest discover -s tests -v",
            "docs/BENCHMARK.md",
            "docs/demo/benchmark-summary.svg",
            "git tag -a v0.1.0",
            "Do not tag a stacked feature branch",
            "explicit approval",
            "does **not complete MP-051**",
        ):
            with self.subTest(term=term):
                self.assertIn(term, text)

    def test_release_guide_preserves_safety_data_and_container_boundaries(self):
        text = (ROOT / "docs" / "RELEASE.md").read_text(encoding="utf-8")
        for term in (
            "synthetic-only",
            "127.0.0.1",
            "No PLC",
            "no remote control",
            "not field performance",
            "IMS",
            "CWRU",
            "redistribution",
            "no RUL model",
            "container",
            "host network",
            "not required",
        ):
            with self.subTest(term=term):
                self.assertIn(term, text)

    def test_readme_links_release_materials_and_marks_candidate_not_published(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        for target in ("CHANGELOG.md", "docs/RELEASE.md", "docs/BENCHMARK.md"):
            with self.subTest(target=target):
                self.assertIn(target, readme)
        self.assertIn("0.1.0", readme)
        self.assertIn("not published", readme.lower())

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
