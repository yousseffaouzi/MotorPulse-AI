"""MP-054 release contracts for the v0.1.1 reproducibility patch candidate."""

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

    def test_changelog_records_011_patch_and_preserves_010_history(self):
        text = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
        for term in (
            "## [0.1.1] - 2026-10-21",
            "MP-053",
            "Windows Python 3.13",
            "39520517680",
            "528 tests",
            "## [0.1.0] - 2026-10-16",
            "v0.1.0",
            "immutable",
            "synthetic",
            "CWRU",
            "no RUL",
        ):
            with self.subTest(term=term):
                self.assertIn(term, text)

    def test_release_guide_records_patch_candidate_and_published_010(self):
        text = (ROOT / "docs" / "RELEASE.md").read_text(encoding="utf-8")
        for term in (
            "v0.1.1 patch-release candidate",
            "0aa56a6ffa560013205bf621484a0268f502ff97",
            "3119a0ed72e7f350f8317136f39d1afdd525184b",
            "39520517680",
            "76cd2421dbfc2c5d0f77528b41474d363f3bfecc",
            "all eight quality jobs passed",
            "528 tests",
            "Do not create `v0.1.1` from this preparation branch",
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

    def test_readme_links_published_010_release_materials(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        for target in (
            "CHANGELOG.md",
            "docs/RELEASE.md",
            "docs/BENCHMARK.md",
            "releases/tag/v0.1.0",
        ):
            with self.subTest(target=target):
                self.assertIn(target, readme)
        self.assertIn("0.1.0", readme)
        self.assertIn("published", readme.lower())
        self.assertNotIn("release candidate, not published", readme.lower())
        self.assertNotIn("not yet tagged", readme.lower())

    def test_tracker_records_053_and_054_without_rewriting_010(self):
        todo = (ROOT / "TODO.md").read_text(encoding="utf-8")
        completed = (
            "| MP-051 | DONE | P2 | Tag a usable release | SemVer, CHANGELOG, "
            "reproducible demo and honest release caveats |"
        )
        self.assertIn(completed, todo)
        self.assertIn(
            "| MP-053 | DONE | P1 | Harden Windows test reproducibility |", todo
        )
        self.assertIn(
            "| MP-054 | IN PROGRESS | P2 | Prepare v0.1.1 patch release |", todo
        )
        self.assertNotIn("| MP-051 | TODO |", todo)
        self.assertIn("v0.1.0", todo)
        self.assertIn("42311ffb2e26d3f75484076bb86a3e607275cde1", todo)
        self.assertIn("39336825312", todo)
        self.assertIn("39520517680", todo)


if __name__ == "__main__":
    unittest.main()
