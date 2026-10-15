"""MP-049 local-first security boundary regressions."""

from __future__ import annotations

from http.client import HTTPConnection
import json
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import threading
import unittest

from motorpulse.__main__ import MotorPulseServer
from motorpulse.config_file import load_config_file
from motorpulse.scenarios import DEFAULT_ASSETS, configuration_dict


ROOT = Path(__file__).resolve().parents[1]


class SecurityBoundaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = MotorPulseServer(("127.0.0.1", 0), autostart=False)
        cls.port = cls.server.server_address[1]
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=2)
        assert not cls.thread.is_alive(), "HTTP server shutdown should complete"

    def test_server_constructor_rejects_non_loopback_and_bad_ports(self):
        for address in (("0.0.0.0", 0), ("127.0.0.1", -1), ("127.0.0.1", 65536)):
            with self.subTest(address=address):
                server = None
                try:
                    server = MotorPulseServer(address, autostart=False)
                except ValueError:
                    continue
                except Exception as exc:
                    self.fail(
                        f"server boundary must reject with ValueError, got {type(exc).__name__}"
                    )
                finally:
                    if server is not None:
                        server.server_close()
                self.fail(f"server boundary accepted unsafe address {address!r}")

    def test_host_header_rejects_nonlocal_names(self):
        conn = HTTPConnection("127.0.0.1", self.port, timeout=3)
        try:
            conn.putrequest("GET", "/api/health", skip_host=True)
            conn.putheader("Host", "attacker.example")
            conn.endheaders()
            response = conn.getresponse()
            payload = json.loads(response.read())
        finally:
            conn.close()
        self.assertEqual(response.status, 400)
        self.assertEqual(payload["code"], "invalid_host_header")

        conn = HTTPConnection("127.0.0.1", self.port, timeout=3)
        try:
            conn.putrequest("GET", "/api/health", skip_host=True)
            conn.putheader("Host", f"localhost:{self.port}")
            conn.endheaders()
            response = conn.getresponse()
            payload = json.loads(response.read())
        finally:
            conn.close()
        self.assertEqual(response.status, 200)
        self.assertEqual(payload["source"], "simulation")

    def test_config_file_rejects_symlinked_paths(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            real_dir = root / "real"
            real_dir.mkdir()
            target = real_dir / "config.json"
            target.write_text(
                json.dumps(configuration_dict(DEFAULT_ASSETS)), encoding="utf-8"
            )
            file_link = root / "config-link.json"
            parent_link = root / "parent-link"
            try:
                file_link.symlink_to(target)
                parent_link.symlink_to(real_dir, target_is_directory=True)
            except (OSError, NotImplementedError) as exc:
                self.skipTest(f"symlinks unavailable on this platform: {exc}")
            for path in (file_link, parent_link / "config.json"):
                with self.subTest(path=path):
                    with self.assertRaisesRegex(ValueError, "symlink"):
                        load_config_file(path)

    def test_control_api_has_no_hardware_actions(self):
        for action in ("connect_plc", "remote_start", "write_hardware"):
            with self.subTest(action=action):
                body = json.dumps({"action": action}).encode("utf-8")
                conn = HTTPConnection("127.0.0.1", self.port, timeout=3)
                try:
                    conn.request(
                        "POST",
                        "/api/control",
                        body=body,
                        headers={"Content-Type": "application/json"},
                    )
                    response = conn.getresponse()
                    payload = json.loads(response.read())
                finally:
                    conn.close()
                self.assertEqual(response.status, 400)
                self.assertEqual(payload["code"], "invalid_control_request")

    def test_cli_exposes_no_bind_address_override(self):
        env = dict(os.environ)
        env["PYTHONPATH"] = str(ROOT)
        cp = subprocess.run(
            [sys.executable, "-m", "motorpulse", "--help"],
            cwd=ROOT,
            env=env,
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        self.assertEqual(cp.returncode, 0, cp.stderr)
        for option in ("--host", "--bind", "--listen"):
            with self.subTest(option=option):
                self.assertNotIn(option, cp.stdout)

    def test_security_guide_documents_local_only_threat_boundary(self):
        path = ROOT / "docs" / "SECURITY.md"
        self.assertTrue(path.is_file())
        text = path.read_text(encoding="utf-8")
        lower = text.lower()
        for term in (
            "127.0.0.1",
            "unauthenticated",
            "host header",
            "symlink",
            "16,384",
            "65,536",
            "no plc",
            "no remote control",
            "not an industrial safety system",
        ):
            with self.subTest(term=term):
                self.assertIn(term, lower)
        self.assertIn(
            "docs/SECURITY.md", (ROOT / "README.md").read_text(encoding="utf-8")
        )


if __name__ == "__main__":
    unittest.main()
