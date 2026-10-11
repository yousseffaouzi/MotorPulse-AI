"""MP-024: validated JSON startup configs and deterministic CLI launches."""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from urllib.request import Request, urlopen

from motorpulse.config_file import MAX_CONFIG_BYTES, load_config_file
from motorpulse.scenarios import DEFAULT_ASSETS, AssetScenario, configuration_dict

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "docs/examples/scenarios-progressive.json"


class FileConfigurationTests(unittest.TestCase):
    def test_existing_progressive_example_is_loadable(self):
        assets = load_config_file(EXAMPLE)
        self.assertEqual(len(assets), 3)
        self.assertEqual(assets[1].progression, "linear")
        self.assertEqual(assets[2].progression, "exponential")
        self.assertEqual(assets[1].onset_tick, 3)
        self.assertEqual(assets[2].duration_ticks, 24)

    def test_default_roundtrip_and_json_utf8(self):
        with TemporaryDirectory() as temp:
            path = Path(temp) / "motors.json"
            path.write_text(json.dumps(configuration_dict(DEFAULT_ASSETS),
                                       ensure_ascii=False), encoding="utf-8")
            self.assertEqual(load_config_file(path), DEFAULT_ASSETS)

    def test_reject_invalid_json_and_duplicate_keys(self):
        for content in (
            b"", b"{broken", b"[]", b"null", b"\xff\xfe",
            b'{"assets":[],"assets":[]}',
            b'{"assets":[{"asset_id":"MTR-10","asset_id":"MTR-11",'
            b'"name":"Bad","scenario":"healthy"}]}',
            b'{"assets":[{"asset_id":"MTR-10","name":"Bad",'
            b'"scenario":"imbalance","severity":NaN}]}',
            b'{"assets":[{"asset_id":"MTR-10","name":"Bad",'
            b'"scenario":"imbalance","severity":Infinity}]}',
        ):
            with self.subTest(content=content[:35]):
                with TemporaryDirectory() as temp:
                    path = Path(temp) / "bad.json"
                    path.write_bytes(content)
                    with self.assertRaises(ValueError):
                        load_config_file(path)

    def test_reject_invalid_scenarios(self):
        bad = [
            {"assets": []},
            {"assets": [{"asset_id": "x", "name": "Invalid", "scenario": "healthy"}]},
            {"assets": [{"asset_id": "MTR-10", "name": "Invalid", "scenario": "unknown"}]},
            {"assets": [{"asset_id": "MTR-10", "name": "Invalid",
                         "scenario": "imbalance", "severity": 2.0}]},
            {"assets": [{"asset_id": "MTR-10", "name": "Invalid",
                         "scenario": "imbalance", "severity": .8,
                         "progression": "linear", "ramp_ticks": 1}]},
        ]
        with TemporaryDirectory() as temp:
            path = Path(temp) / "config.json"
            for config in bad:
                with self.subTest(config=config):
                    path.write_text(json.dumps(config), encoding="utf-8")
                    with self.assertRaises(ValueError):
                        load_config_file(path)

    def test_reject_missing_directory_and_oversized(self):
        with TemporaryDirectory() as temp:
            path = Path(temp) / "large.json"
            path.write_bytes(b" " * (MAX_CONFIG_BYTES + 1))
            with self.assertRaisesRegex(ValueError, "exceeds"):
                load_config_file(path)
            with self.assertRaises(ValueError):
                load_config_file(Path(temp) / "missing.json")
            with self.assertRaises(ValueError):
                load_config_file(temp)

    def test_importing_file_does_not_modify_it(self):
        original = EXAMPLE.read_bytes()
        self.assertGreater(len(load_config_file(EXAMPLE)), 0)
        self.assertEqual(EXAMPLE.read_bytes(), original)


class CLILaunchTests(unittest.TestCase):
    @staticmethod
    def env():
        result = dict(os.environ)
        result["PYTHONPATH"] = str(ROOT)
        return result

    def test_help_lists_new_options(self):
        cp = subprocess.run([sys.executable, "-m", "motorpulse", "--help"],
                            cwd=ROOT, env=self.env(), capture_output=True, text=True,
                            timeout=15, check=False)
        self.assertEqual(cp.returncode, 0, cp.stderr)
        for option in ("--config", "--paused", "--port", "--seed",
                       "--start-time-utc", "--step-seconds", "--interval-seconds"):
            self.assertIn(option, cp.stdout)

    def test_invalid_file_or_port_fails_without_server_start(self):
        for args in (["--config", "missing.json"], ["--port", "-1"],
                     ["--port", "70000"], ["--config", "docs/INSTALL.md"]):
            with self.subTest(args=args):
                cp = subprocess.run([sys.executable, "-m", "motorpulse", *args],
                                    cwd=ROOT, env=self.env(), text=True,
                                    capture_output=True, timeout=15, check=False)
                self.assertEqual(cp.returncode, 2, cp.stdout + cp.stderr)
                self.assertIn("error:", cp.stderr)

    def test_cli_relative_config_replays_across_processes(self):
        with TemporaryDirectory() as tmp:
            source = EXAMPLE.read_bytes()
            (Path(tmp) / "config.json").write_bytes(source)
            flags = [
                "--config", "config.json", "--paused", "--port", "0",
                "--seed", "72", "--start-time-utc", "2026-05-20T12:00:00Z",
                "--step-seconds", "2.5", "--interval-seconds", "30",
            ]
            def run_once():
                process = subprocess.Popen(
                    [sys.executable, "-u", "-m", "motorpulse", *flags],
                    cwd=tmp, env=self.env(), text=True, stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE)
                try:
                    line = process.stdout.readline().strip()
                    match = re.search(r"127\.0\.0\.1:(\d+)$", line)
                    self.assertIsNotNone(match, f"startup failed: {line}; exit {process.poll()}")
                    root = "http://127.0.0.1:" + match.group(1)
                    with urlopen(root + "/api/status", timeout=5) as response:
                        status = json.load(response)
                    with urlopen(root + "/api/config", timeout=5) as response:
                        config = json.load(response)
                    with urlopen(root + "/api/snapshot", timeout=5) as response:
                        first = json.load(response)
                    with urlopen(root + "/api/snapshot", timeout=5) as response:
                        self.assertEqual(json.load(response), first)
                    request = Request(root + "/api/control",
                                      data=b'{"action":"step"}',
                                      headers={"Content-Type": "application/json"},
                                      method="POST")
                    with urlopen(request, timeout=5):
                        pass
                    with urlopen(root + "/api/snapshot", timeout=5) as response:
                        second = json.load(response)
                    return status, config, first, second
                finally:
                    process.terminate()
                    try:
                        process.communicate(timeout=5)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.communicate(timeout=5)

            a = run_once()
            b = run_once()
            self.assertEqual(a, b)
            status, config, first, second = a
            self.assertEqual(status["state"], "paused")
            self.assertEqual(status["tick"], 1)
            self.assertEqual(len(config["assets"]), 3)
            self.assertEqual(first["recorded_at_utc"], "2026-05-20T12:00:00+00:00")
            self.assertEqual(second["recorded_at_utc"], "2026-05-20T12:00:02.500000+00:00")
            self.assertEqual(second["tick"], 2)


if __name__ == "__main__":
    unittest.main()
