"""MP-047 documentation contracts for the public contributor surface.

These tests pin implemented entry points and safety boundaries, not prose style.
"""

from __future__ import annotations

from pathlib import Path
import tomllib
import unittest


ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


class DocumentationContractTests(unittest.TestCase):
    def test_readme_links_documentation_entry_points(self):
        readme = _read(ROOT / "README.md")
        for target in (
            "docs/API.md",
            "docs/CLI.md",
            "docs/TROUBLESHOOTING.md",
            "docs/ARCHITECTURE.md",
            "docs/CONFIG_FILE.md",
        ):
            with self.subTest(target=target):
                self.assertIn(target, readme)
                self.assertTrue((ROOT / target).is_file())

    def test_api_reference_lists_current_http_surface_and_limits(self):
        api = _read(DOCS / "API.md")
        routes = (
            ("GET", "/api/health"),
            ("GET", "/api/snapshot"),
            ("GET", "/api/status"),
            ("GET", "/api/stream"),
            ("GET", "/api/config"),
            ("PUT", "/api/config"),
            ("PUT", "/api/runtime"),
            ("POST", "/api/control"),
            ("GET", "/api/history/sessions"),
            ("GET", "/api/history/snapshots"),
            ("GET", "/api/history/events"),
            ("GET", "/api/history/alerts"),
            ("GET", "/api/history/incidents"),
            ("GET", "/api/history/transitions"),
            ("POST", "/api/incidents/acknowledge"),
        )
        for method, path in routes:
            with self.subTest(method=method, path=path):
                self.assertIn(f"| {method} | `{path}` |", api)
        for contract in (
            "16384",
            "64",
            "unknown_api_endpoint",
            "text/event-stream",
            "polling",
            "does not buffer or replay missed frames",
        ):
            with self.subTest(contract=contract):
                self.assertIn(contract, api)

    def test_cli_tutorial_covers_every_installed_console_script(self):
        with (ROOT / "pyproject.toml").open("rb") as handle:
            scripts = tomllib.load(handle)["project"]["scripts"]
        cli = _read(DOCS / "CLI.md")
        for command in scripts:
            with self.subTest(command=command):
                self.assertIn(f"`{command}`", cli)
        self.assertIn("held-out", cli.lower())
        self.assertIn("synthetic", cli.lower())

    def test_architecture_has_current_online_and_offline_flow_diagrams(self):
        architecture = _read(DOCS / "ARCHITECTURE.md")
        self.assertGreaterEqual(architecture.count("```mermaid"), 2)
        for term in (
            "127.0.0.1",
            "SQLite v3",
            "history_api.py",
            "whole-run",
            "healthy-only",
            "held-out",
            "No hardware control",
        ):
            with self.subTest(term=term):
                self.assertIn(term, architecture)

    def test_configuration_and_troubleshooting_distinguish_failure_surfaces(self):
        config = _read(DOCS / "CONFIG_FILE.md")
        for term in (
            "65,536",
            "16,384",
            "PUT /api/config",
            "PUT /api/runtime",
            "duplicate",
        ):
            with self.subTest(term=term):
                self.assertIn(term, config)

        troubleshooting = _read(DOCS / "TROUBLESHOOTING.md")
        for term in (
            "127.0.0.1",
            "port 8765",
            "--database",
            "400",
            "409",
            "503",
            "persistence_unavailable",
            "history_unavailable",
            "No real sensors",
        ):
            with self.subTest(term=term):
                self.assertIn(term, troubleshooting)


if __name__ == "__main__":
    unittest.main()
