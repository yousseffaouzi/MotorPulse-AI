"""Local-only demonstration server: python -m motorpulse"""
import json
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from .controller import ControlConflict, SimulationController

ROOT = Path(__file__).resolve().parents[1] / "web"
MAX_CONTROL_BODY_BYTES = 4096


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def _json(self, status: int, data: dict) -> None:
        payload = json.dumps(data, allow_nan=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self):
        path = urlsplit(self.path).path
        if path == "/api/snapshot":
            self._json(200, self.server.controller.snapshot())
        elif path == "/api/status":
            self._json(200, self.server.controller.status())
        elif path == "/api/health":
            self._json(200, {"status": "ok", "source": "simulation"})
        elif path.startswith("/api/"):
            self._json(404, {"error": "Unknown API endpoint"})
        else:
            super().do_GET()

    def do_POST(self):
        if urlsplit(self.path).path != "/api/control":
            self._json(404, {"error": "Unknown API endpoint"})
            return
        # JSON is non-simple in browser requests: cross-origin callers require
        # a preflight, which this local server deliberately does not enable.
        content_type = self.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
        if content_type != "application/json":
            self._json(415, {"error": "Content-Type must be application/json"})
            return
        length_text = self.headers.get("Content-Length", "")
        if not length_text.isascii() or not length_text.isdecimal():
            self.close_connection = True
            self._json(411, {"error": "Content-Length is required"})
            return
        length = int(length_text)
        if not 0 < length <= MAX_CONTROL_BODY_BYTES:
            self.close_connection = True
            self._json(413, {"error": "Invalid control request size"})
            return
        try:
            body = json.loads(self.rfile.read(length).decode("utf-8"))
        except (ValueError, UnicodeError):
            self._json(400, {"error": "Invalid JSON"})
            return
        if (not isinstance(body, dict) or set(body) != {"action"}
                or not isinstance(body["action"], str)):
            self._json(400, {"error": 'Body must be {"action":"start|pause|step|reset"}'})
            return
        try:
            result = self.server.controller.control(body["action"])
        except ValueError as exc:
            self._json(400, {"error": str(exc)})
        except ControlConflict as exc:
            self._json(409, {"error": str(exc)})
        else:
            self._json(200, result)


class MotorPulseServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, server_address: tuple[str, int], *, seed: int = 42,
                 interval_seconds: float = 1.5, autostart: bool = True):
        super().__init__(server_address, Handler)
        self.controller = SimulationController(
            seed=seed, interval_seconds=interval_seconds, autostart=autostart,
        )

    def server_close(self) -> None:
        self.controller.close()
        super().server_close()


def main() -> None:
    with MotorPulseServer(("127.0.0.1", 8765)) as httpd:
        print("MotorPulse AI (synthetic demo): http://127.0.0.1:8765")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
