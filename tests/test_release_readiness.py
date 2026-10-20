"""MP-051 post-release contracts for the published v0.1.0 research release."""

from __future__ import annotations

from pathlib import Path
import tomllib
import unittest


ROOT = Path(__file__).resolve().parents[1]


class ReleaseReadinessTests(unittest.TestCase):
    def test_version_is_semver_alpha_release(self):
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

    def test_release_guide_records_published_tag_and_exact_green_main(self):
        text = (ROOT / "docs" / "RELEASE.md").read_text(encoding="utf-8")
        for term in (
            "Published v0.1.0 evidence",
            "v0.1.0",
            "42311ffb2e26d3f75484076bb86a3e607275cde1",
            "0e3caa376557663bdae14cf9fecced70706702c8",
            "39336825312",
            "418979228",
            "2026-10-20T23:24:54Z",
            "all seven quality jobs",
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

    def test_readme_links_release_materials_and_marks_release_published(self):
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

    def test_tracker_marks_release_complete_after_published_tag(self):
        todo = (ROOT / "TODO.md").read_text(encoding="utf-8")
        completed = (
            "| MP-051 | DONE | P2 | Tag a usable release | SemVer, CHANGELOG, "
            "reproducible demo and honest release caveats |"
        )
        self.assertIn(completed, todo)
        self.assertNotIn("| MP-051 | TODO |", todo)
        self.assertIn("v0.1.0", todo)
        self.assertIn("42311ffb2e26d3f75484076bb86a3e607275cde1", todo)
        self.assertIn("39336825312", todo)


if __name__ == "__main__":
    unittest.main()
