"""MP-052 contracts for the optional local-only container quick start.

These tests inspect repository/container configuration only. The permanent CI
container-smoke job performs the actual Docker build/run check; the Python test
suite itself must remain runnable on hosts without Docker.
"""

from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
DOCKERFILE = ROOT / "Dockerfile"
COMPOSE = ROOT / "compose.yaml"
DOCKERIGNORE = ROOT / ".dockerignore"
GUIDE = ROOT / "docs" / "CONTAINER.md"
WORKFLOW = ROOT / ".github" / "workflows" / "test.yml"
README = ROOT / "README.md"


class ContainerQuickStartContracts(unittest.TestCase):
    def test_dockerfile_is_stdlib_only_non_root_and_loopback_aware(self):
        text = DOCKERFILE.read_text(encoding="utf-8")
        self.assertIn("FROM python:3.13-slim-bookworm", text)
        self.assertIn("PYTHONDONTWRITEBYTECODE=1", text)
        self.assertIn("COPY motorpulse /app/motorpulse", text)
        self.assertIn("USER 65532:65532", text)
        self.assertIn('["python", "-m", "motorpulse"]', text)
        self.assertIn('["--port", "8765"]', text)
        self.assertIn("http://127.0.0.1:8765/api/health", text)
        for forbidden in ("pip install", "apt-get", "apk add", "curl ", "wget ", "EXPOSE "):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, text)

    def test_compose_uses_host_network_without_port_mapping_or_host_mounts(self):
        text = COMPOSE.read_text(encoding="utf-8")
        for required in (
            "network_mode: host",
            "read_only: true",
            "cap_drop:",
            "- ALL",
            "no-new-privileges:true",
            "init: true",
        ):
            with self.subTest(required=required):
                self.assertIn(required, text)
        for forbidden in ("ports:", "volumes:", "devices:", "privileged:", "/var/run/docker.sock"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, text)

    def test_build_context_excludes_local_data_state_and_repository_metadata(self):
        text = DOCKERIGNORE.read_text(encoding="utf-8")
        for entry in (
            ".git",
            "data/",
            "datasets/",
            "*.sqlite3",
            "*.db",
            ".venv/",
            "__pycache__/",
        ):
            with self.subTest(entry=entry):
                self.assertIn(entry, text)

    def test_guide_explains_security_tradeoff_and_native_fallback(self):
        text = GUIDE.read_text(encoding="utf-8")
        for term in (
            "docker compose up --build",
            "http://127.0.0.1:8765",
            "network_mode: host",
            "Docker Desktop 4.34",
            "Enable host networking",
            "native Python",
            "127.0.0.1",
            "no port publishing",
            "shares the host network stack",
            "not required",
        ):
            with self.subTest(term=term):
                self.assertIn(term, text)
        self.assertNotIn("0.0.0.0", text)

    def test_ci_builds_runs_and_checks_local_security_boundary(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        for term in (
            "Container quick start",
            "docker compose build",
            "docker compose up -d",
            "/api/health",
            "invalid_host_header",
            "docker compose down",
        ):
            with self.subTest(term=term):
                self.assertIn(term, text)

    def test_readme_keeps_native_python_primary_and_container_optional(self):
        text = README.read_text(encoding="utf-8")
        self.assertIn("docs/CONTAINER.md", text)
        self.assertIn("optional container", text.lower())
        self.assertIn("native Python", text)
        self.assertIn("No Docker", text)


if __name__ == "__main__":
    unittest.main()
