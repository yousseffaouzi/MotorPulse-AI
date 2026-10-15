"""MP-043: request validation, stable errors and safe failure semantics."""
from __future__ import annotations

from http.client import HTTPConnection
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Thread
import unittest

from motorpulse.__main__ import MotorPulseServer
from motorpulse.scenarios import DEFAULT_ASSETS, configuration_dict


class ApiValidationHardeningTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = MotorPulseServer(("127.0.0.1", 0), autostart=False)
        cls.port = cls.server.server_address[1]
        cls.thread = Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=3)
        assert not cls.thread.is_alive()

    def setUp(self):
        self.server.controller.configure(configuration_dict(DEFAULT_ASSETS))

    def raw_request(self, method, path, body=b"", headers=None):
        conn = HTTPConnection("127.0.0.1", self.port, timeout=3)
        try:
            conn.putrequest(method, path)
            for key, value in (headers or {}).items():
                conn.putheader(key, value)
            conn.endheaders(body)
            response = conn.getresponse()
            raw = response.read()
            return response.status, raw, dict(response.getheaders())
        finally:
            conn.close()

    def json_request(self, method, path, body):
        raw = json.dumps(body, separators=(",", ":")).encode("utf-8")
        return self.raw_request(method, path, raw, {
            "Content-Type": "application/json",
            "Content-Length": str(len(raw)),
        })

    def assert_json_error(self, result, status, code):
        actual, raw, headers = result
        self.assertEqual(actual, status, raw)
        self.assertIn("application/json", headers.get("Content-Type", ""))
        payload = json.loads(raw)
        self.assertEqual(payload["code"], code, payload)
        self.assertIsInstance(payload["error"], str)
        self.assertTrue(payload["error"])
        return payload

    def test_duplicate_and_nonstandard_json_are_rejected_before_mutation(self):
        baseline = self.server.controller.snapshot()
        for raw in (
            b'{"action":"step","action":"pause"}',
            b'{"action":NaN}',
            b'{"action":Infinity}',
            b'{"action":-Infinity}',
        ):
            with self.subTest(raw=raw):
                result = self.raw_request("POST", "/api/control", raw, {
                    "Content-Type": "application/json",
                    "Content-Length": str(len(raw)),
                })
                self.assert_json_error(result, 400, "invalid_json")
                self.assertEqual(self.server.controller.snapshot(), baseline)

    def test_excessive_json_nesting_fails_closed_as_invalid_json(self):
        baseline = self.server.controller.snapshot()
        raw = b"[" * 1100 + b"0" + b"]" * 1100
        result = self.raw_request("POST", "/api/control", raw, {
            "Content-Type": "application/json",
            "Content-Length": str(len(raw)),
        })
        self.assert_json_error(result, 400, "invalid_json")
        self.assertEqual(self.server.controller.snapshot(), baseline)

    def test_pathological_content_length_is_bounded_without_integer_conversion_error(self):
        baseline = self.server.controller.snapshot()
        result = self.raw_request("POST", "/api/control", headers={
            "Content-Type": "application/json",
            "Content-Length": "9" * 5000,
        })
        self.assert_json_error(result, 413, "invalid_request_size")
        self.assertEqual(self.server.controller.snapshot(), baseline)

    def test_common_request_and_route_errors_have_stable_machine_codes(self):
        self.assert_json_error(
            self.raw_request("POST", "/api/control", b"{}", {
                "Content-Type": "text/plain", "Content-Length": "2",
            }), 415, "unsupported_media_type")
        self.assert_json_error(
            self.raw_request("POST", "/api/control", headers={
                "Content-Type": "application/json",
            }), 411, "length_required")
        self.assert_json_error(
            self.raw_request("POST", "/api/control", headers={
                "Content-Type": "application/json", "Content-Length": "0",
            }), 413, "invalid_request_size")
        self.assert_json_error(
            self.json_request("POST", "/api/control", {}),
            400, "invalid_control_request")
        self.assert_json_error(
            self.json_request("PUT", "/api/config", {"assets": []}),
            400, "invalid_configuration")
        self.assert_json_error(
            self.json_request("PUT", "/api/runtime", {"seed": 1}),
            400, "invalid_runtime_settings")
        self.assert_json_error(
            self.raw_request("GET", "/api/not-found"),
            404, "unknown_api_endpoint")

        self.json_request("POST", "/api/control", {"action": "start"})
        try:
            self.assert_json_error(
                self.json_request("POST", "/api/control", {"action": "step"}),
                409, "control_conflict")
        finally:
            self.json_request("POST", "/api/control", {"action": "pause"})

    def test_unsupported_api_methods_use_json_unknown_endpoint_contract(self):
        for method in ("DELETE", "PATCH", "OPTIONS"):
            with self.subTest(method=method):
                self.assert_json_error(
                    self.raw_request(method, "/api/status"),
                    404, "unknown_api_endpoint")

        status, raw, headers = self.raw_request("HEAD", "/api/status")
        self.assertEqual(status, 404)
        self.assertEqual(raw, b"")
        self.assertIn("application/json", headers.get("Content-Type", ""))
        self.assertGreater(int(headers["Content-Length"]), 0)

    def test_persistence_failure_returns_stable_503_without_state_advance(self):
        with TemporaryDirectory() as temp:
            server = MotorPulseServer(
                ("127.0.0.1", 0), autostart=False,
                database_path=Path(temp) / "history.sqlite3",
            )
            thread = Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                baseline = server.controller.snapshot()
                server.controller._storage._db.close()
                raw = b'{"action":"step"}'
                conn = HTTPConnection("127.0.0.1", server.server_address[1], timeout=3)
                try:
                    conn.putrequest("POST", "/api/control")
                    conn.putheader("Content-Type", "application/json")
                    conn.putheader("Content-Length", str(len(raw)))
                    conn.endheaders(raw)
                    response = conn.getresponse()
                    payload = json.loads(response.read())
                    self.assertEqual(response.status, 503, payload)
                    self.assertEqual(payload["code"], "persistence_unavailable")
                    self.assertNotIn(str(Path(temp)), json.dumps(payload))
                finally:
                    conn.close()
                self.assertEqual(server.controller.snapshot(), baseline)
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=3)
                self.assertFalse(thread.is_alive())


if __name__ == "__main__":
    unittest.main()
