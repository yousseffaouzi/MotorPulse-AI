"""MP-045: fail-closed dependency policy for the local-first package.

This executable policy remains available when GitHub Dependency Review cannot run
because the repository Dependency graph is disabled.
"""

from __future__ import annotations

from pathlib import Path
import tomllib
import unittest


ROOT = Path(__file__).resolve().parents[1]
PYPROJECT = ROOT / "pyproject.toml"
APPROVED_BUILD_REQUIREMENTS = ["setuptools>=77.0.3", "wheel"]


class DependencyPolicyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with PYPROJECT.open("rb") as handle:
            cls.config = tomllib.load(handle)

    def test_runtime_and_optional_dependencies_are_empty(self):
        project = self.config["project"]
        self.assertEqual(project.get("dependencies", []), [])
        self.assertFalse(project.get("optional-dependencies", {}))

    def test_build_dependencies_match_reviewed_requirements(self):
        requirements = self.config["build-system"]["requires"]
        self.assertEqual(requirements, APPROVED_BUILD_REQUIREMENTS)


if __name__ == "__main__":
    unittest.main()
