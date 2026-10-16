"""MP-014 contracts for optional localhost SSE with polling fallback.

Reconnect reads the latest local state; the server does not claim buffered event replay.
"""

from __future__ import annotations

from http.client import HTTPConnection
import json
from pathlib import Path
import threading
import unittest

from motorpulse.__main__ import MotorPulseServer


ROOT = Path(__file__).resolve().parents[1]
HTML = ROOT / "motorpulse" / "web" / "index.html"


class StreamingHTTPTests(unittest.TestCase):
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
        assert not cls.thread.is_alive()

    def setUp(self):
        self.server.controller.control("reset")

    def _first_event(self) -> tuple[dict[str, str], dict]:
        conn = HTTPConnection("127.0.0.1", self.port, timeout=3)
        conn.request("GET", "/api/stream", headers={"Accept": "text/event-stream"})
        response = conn.getresponse()
        self.assertEqual(response.status, 200)
        headers = {key.lower(): value for key, value in response.getheaders()}
        lines = []
        while True:
            raw = response.fp.readline()
            self.assertTrue(raw, "SSE stream closed before first event")
            line = raw.decode("utf-8").rstrip("\r\n")
            if not line:
                break
            lines.append(line)
        conn.close()
        fields = {}
        for line in lines:
            key, _, value = line.partition(":")
            fields[key] = value.lstrip()
        self.assertEqual(fields.get("event"), "state")
        self.assertIn("id", fields)
        self.assertIn("retry", fields)
        return headers, json.loads(fields["data"])

    def test_sse_headers_payload_and_read_only_semantics(self):
        before = self.server.controller.snapshot()
        headers, payload = self._first_event()
        after = self.server.controller.snapshot()
        self.assertEqual(headers["content-type"], "text/event-stream; charset=utf-8")
        self.assertEqual(headers["cache-control"], "no-store")
        self.assertEqual(headers["x-content-type-options"], "nosniff")
        self.assertEqual(payload["source"], "simulation")
        self.assertEqual(payload["snapshot"], before)
        self.assertEqual(payload["status"]["tick"], before["tick"])
        self.assertEqual(after, before, "opening a stream must never advance simulation")

    def test_disconnect_then_reconnect_observes_explicit_step(self):
        _, first = self._first_event()
        self.assertEqual(first["snapshot"]["tick"], 1)
        self.server.controller.control("step")
        _, second = self._first_event()
        self.assertEqual(second["snapshot"]["tick"], 2)
        self.assertEqual(second["status"]["tick"], 2)

    def test_stream_requires_local_host_header(self):
        conn = HTTPConnection("127.0.0.1", self.port, timeout=3)
        try:
            conn.putrequest("GET", "/api/stream", skip_host=True)
            conn.putheader("Host", "example.com")
            conn.endheaders()
            response = conn.getresponse()
            self.assertEqual(response.status, 400)
            payload = json.loads(response.read())
            self.assertEqual(payload["code"], "invalid_host_header")
        finally:
            conn.close()


class StreamingDashboardContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = HTML.read_text(encoding="utf-8")

    def test_dashboard_uses_eventsource_and_keeps_polling_fallback(self):
        for term in (
            "new EventSource('/api/stream')",
            "stream.addEventListener('state'",
            "stream.onerror",
            "startPollingFallback",
            "stopPollingFallback",
            "setInterval",
            "refresh();refreshMode()",
        ):
            with self.subTest(term=term):
                self.assertIn(term, self.html)

    def test_stream_payload_updates_snapshot_and_status_without_control_action(self):
        self.assertIn("applySnapshot(payload.snapshot)", self.html)
        self.assertIn("applyStatus(payload.status)", self.html)
        stream_block = self.html.split("new EventSource('/api/stream')", 1)[1]
        self.assertNotIn("sendControl(", stream_block.split("</script>", 1)[0])

    def test_dashboard_labels_stream_as_optional_and_local(self):
        self.assertIn("Live updates: connecting", self.html)
        self.assertIn("polling fallback", self.html.lower())
        self.assertIn("localhost", self.html.lower())


if __name__ == "__main__":
    unittest.main()
