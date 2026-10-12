"""MP-022: standard-library packaging metadata and installed-static-UI smoke checks."""
from __future__ import annotations

from importlib.resources import files
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Thread
from urllib.request import urlopen
import json
import os
import subprocess
import sys
import tomllib
import unittest

from motorpulse.__main__ import MotorPulseServer, ROOT

REPOSITORY = Path(__file__).resolve().parents[1]


class PackagingTests(unittest.TestCase):
    def test_project_metadata_and_python_requirements(self):
        with (REPOSITORY / "pyproject.toml").open("rb") as stream:
            project = tomllib.load(stream)
        self.assertEqual(project["build-system"]["build-backend"], "setuptools.build_meta")
        self.assertEqual(project["project"]["name"], "motorpulse-ai")
        self.assertEqual(project["project"]["requires-python"], ">=3.11")
        self.assertEqual(project["project"]["dependencies"], [])
        self.assertEqual(project["project"]["scripts"]["motorpulse-ai"],
                         "motorpulse.__main__:main")
        self.assertEqual(project["project"]["scripts"]["motorpulse-export"],
                         "motorpulse.export:main")
        self.assertEqual(project["project"]["scripts"]["motorpulse-ims"],
                         "motorpulse.ims:main")
        self.assertEqual(project["project"]["scripts"]["motorpulse-ims-validate"],
                         "motorpulse.ims_validation:main")
        self.assertEqual(project["project"]["scripts"]["motorpulse-eda"],
                         "motorpulse.eda:main")
        self.assertEqual(project["project"]["scripts"]["motorpulse-split"],
                         "motorpulse.splits:main")
        self.assertEqual(project["project"]["scripts"]["motorpulse-card"],
                         "motorpulse.dataset_cards:main")
        self.assertEqual(project["project"]["scripts"]["motorpulse-anomaly"],
                         "motorpulse.anomaly:main")
        self.assertEqual(project["project"]["scripts"]["motorpulse-evaluate"],
                         "motorpulse.evaluation:main")
        self.assertEqual(project["project"]["scripts"]["motorpulse-experiment"],
                         "motorpulse.experiment:main")
        self.assertIn("web/index.html", project["tool"]["setuptools"]["package-data"]["motorpulse"])
        self.assertIn("cards/*.json", project["tool"]["setuptools"]["package-data"]["motorpulse"])
        for name in ("synthetic-v1.json", "ims-v1.json"):
            self.assertTrue(files("motorpulse").joinpath("cards", name).is_file())

    def test_browser_is_a_real_package_resource(self):
        resource = files("motorpulse").joinpath("web", "index.html")
        self.assertTrue(resource.is_file(), "Dashboard must be packaged for wheel installs")
        html = resource.read_text(encoding="utf-8")
        self.assertIn("<title>MotorPulse AI", html)
        self.assertIn("/api/snapshot", html)
        self.assertIn("/api/config", html)
        self.assertEqual(ROOT / "index.html", Path(str(resource)))

    def test_server_serves_packaged_dashboard(self):
        server = MotorPulseServer(("127.0.0.1", 0), autostart=False)
        worker = Thread(target=server.serve_forever, daemon=True)
        worker.start()
        try:
            url = f"http://127.0.0.1:{server.server_address[1]}"
            with urlopen(url + "/", timeout=3) as result:
                html = result.read().decode("utf-8")
                self.assertEqual(result.status, 200)
                self.assertIn("MotorPulse AI", html)
                self.assertIn("Apply scenarios", html)
            with urlopen(url + "/api/health", timeout=3) as result:
                self.assertEqual(json.load(result)["status"], "ok")
        finally:
            server.shutdown()
            server.server_close()
            worker.join(timeout=3)
            self.assertFalse(worker.is_alive())

    def test_command_line_help_from_unrelated_working_directory(self):
        with TemporaryDirectory() as directory:
            env = dict(os.environ)
            # Make source-mode import available even before 'pip install -e .'.
            env["PYTHONPATH"] = str(REPOSITORY)
            cmd = [sys.executable, "-m", "motorpulse", "--help"]
            result = subprocess.run(cmd, cwd=directory, env=env, text=True,
                                    capture_output=True, timeout=15, check=False)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("--start-time-utc", result.stdout)
            self.assertIn("--step-seconds", result.stdout)


if __name__ == "__main__":
    unittest.main()
