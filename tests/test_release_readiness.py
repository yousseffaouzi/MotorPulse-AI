"""MP-055 post-release contracts for the published v0.1.1 patch."""

from __future__ import annotations

from pathlib import Path
import tomllib
import unittest


ROOT = Path(__file__).resolve().parents[1]


class ReleaseReadinessTests(unittest.TestCase):
    def test_version_is_semver_alpha_release(self):
        with (ROOT / "pyproject.toml").open("rb") as handle:
            project = tomllib.load(handle)["project"]
        self.assertEqual(project["version"], "0.1.1")
        self.assertIn("Development Status :: 3 - Alpha", project["classifiers"])
        self.assertNotIn("Development Status :: 2 - Pre-Alpha", project["classifiers"])

    def test_changelog_records_published_011_and_preserves_010_history(self):
        text = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
        for term in (
            "## [0.1.1] - 2026-10-30",
            "MP-053",
            "Windows Python 3.13",
            "39520517680",
            "39524346340",
            "528-test",
            "2f8176f54364c0da7f57ce6698aa4906d781d4df",
            "8d8e4c9f9855f18de0e78937efffead5521753e1",
            "429574626",
            "2026-10-30T23:13:21Z",
            "## [0.1.0] - 2026-10-16",
            "v0.1.0",
            "immutable",
            "synthetic",
            "CWRU",
            "no RUL",
        ):
            with self.subTest(term=term):
                self.assertIn(term, text)

    def test_release_guide_records_published_011_and_published_010(self):
        text = (ROOT / "docs" / "RELEASE.md").read_text(encoding="utf-8")
        for term in (
            "Published v0.1.1 evidence",
            "0aa56a6ffa560013205bf621484a0268f502ff97",
            "3119a0ed72e7f350f8317136f39d1afdd525184b",
            "39520517680",
            "76cd2421dbfc2c5d0f77528b41474d363f3bfecc",
            "2f8176f54364c0da7f57ce6698aa4906d781d4df",
            "8d8e4c9f9855f18de0e78937efffead5521753e1",
            "39524346340",
            "429574626",
            "2026-10-30T23:13:21Z",
            "all eight quality jobs passed",
            "528 tests",
            "Published v0.1.0 evidence",
            "42311ffb2e26d3f75484076bb86a3e607275cde1",
            "0e3caa376557663bdae14cf9fecced70706702c8",
            "39336825312",
            "418979228",
            "2026-10-20T23:24:54Z",
            "all seven quality jobs passed",
            "526 tests",
            "python -m unittest discover -s tests -v",
            "git tag -a v0.1.0",
            "never move or force-rewrite",
        ):
            with self.subTest(term=term):
                self.assertIn(term, text)
        self.assertNotIn("v0.1.1 patch-release candidate", text)

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

    def test_readme_links_published_011_release_materials(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        for target in (
            "CHANGELOG.md",
            "docs/RELEASE.md",
            "docs/BENCHMARK.md",
            "releases/tag/v0.1.1",
            "motorpulse-ai 0.1.1",
        ):
            with self.subTest(target=target):
                self.assertIn(target, readme)
        self.assertIn("2026-10-30", readme)
        self.assertIn("published", readme.lower())
        self.assertNotIn("release candidate, not published", readme.lower())
        self.assertNotIn("not yet tagged", readme.lower())

    def test_tracker_records_053_through_056_without_rewriting_010(self):
        todo = (ROOT / "TODO.md").read_text(encoding="utf-8")
        completed = (
            "| MP-051 | DONE | P2 | Tag a usable release | SemVer, CHANGELOG, "
            "reproducible demo and honest release caveats |"
        )
        self.assertIn(completed, todo)
        self.assertIn(
            "| MP-053 | DONE | P1 | Harden Windows test reproducibility |", todo
        )
        self.assertIn("| MP-054 | DONE | P2 | Prepare v0.1.1 patch release |", todo)
        self.assertIn(
            "| MP-055 | DONE | P2 | Finalize v0.1.1 post-release bookkeeping |",
            todo,
        )
        self.assertIn(
            "| MP-056 | DONE | P1 | Stabilize portable artifacts across Python patch upgrades |",
            todo,
        )
        self.assertNotIn("| MP-051 | TODO |", todo)
        self.assertNotIn("| MP-055 | IN PROGRESS |", todo)
        self.assertIn("v0.1.0", todo)
        self.assertIn("42311ffb2e26d3f75484076bb86a3e607275cde1", todo)
        self.assertIn("39336825312", todo)
        self.assertIn("39520517680", todo)
        self.assertIn("39524346340", todo)
        self.assertIn("41145370302", todo)
        self.assertIn("2f8176f54364c0da7f57ce6698aa4906d781d4df", todo)
        self.assertIn("8d8e4c9f9855f18de0e78937efffead5521753e1", todo)
        self.assertIn("429574626", todo)
        self.assertIn(
            "c10cfff19ae2c897b111e69595a34347280c107cf6c6d121bc77067b4ceb266f",
            todo,
        )


if __name__ == "__main__":
    unittest.main()
