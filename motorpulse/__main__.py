"""Local-only demonstration server: python -m motorpulse"""
import json
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Lock
from .sim import MotorSimulator

ROOT = Path(__file__).resolve().parents[1] / "web"
SIM = MotorSimulator()
LOCK = Lock()


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def do_GET(self):
        if self.path == "/api/snapshot":
            with LOCK:
                snapshot = SIM.step()
            payload = json.dumps(snapshot).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
        elif self.path == "/api/health":
            payload = b'{"status":"ok","source":"simulation"}'
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
        else:
            super().do_GET()


def main():
    httpd = ThreadingHTTPServer(("127.0.0.1", 8765), Handler)
    print("MotorPulse AI (synthetic demo): http://127.0.0.1:8765")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()


if __name__ == "__main__":
    main()
