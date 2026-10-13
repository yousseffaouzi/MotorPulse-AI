"""Local-only demonstration server: python -m motorpulse"""
import argparse
import json
import sqlite3
from datetime import datetime
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from .config_file import load_config_file
from .controller import ControlConflict, SimulationController
from .scenarios import AssetScenario, DEFAULT_ASSETS
from .sim import DEFAULT_START_TIME_UTC, parse_start_time_utc

ROOT = Path(__file__).resolve().parent / "web"
MAX_CONTROL_BODY_BYTES = 16384


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
        elif path == "/api/config":
            self._json(200, self.server.controller.configuration())
        elif path == "/api/health":
            self._json(200, {"status": "ok", "source": "simulation"})
        elif path.startswith("/api/"):
            self._json(404, {"error": "Unknown API endpoint"})
        else:
            super().do_GET()

    def _read_json_body(self) -> tuple[bool, object]:
        # Non-simple JSON requests require a preflight from cross-origin sites;
        # this local development server does not permit such preflights.
        content_type = self.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
        if content_type != "application/json":
            self._json(415, {"error": "Content-Type must be application/json"})
            return False, None
        length_text = self.headers.get("Content-Length", "")
        if not length_text.isascii() or not length_text.isdecimal():
            self.close_connection = True
            self._json(411, {"error": "Content-Length is required"})
            return False, None
        length = int(length_text)
        if not 0 < length <= MAX_CONTROL_BODY_BYTES:
            self.close_connection = True
            self._json(413, {"error": "Invalid JSON request size"})
            return False, None
        try:
            return True, json.loads(self.rfile.read(length).decode("utf-8"))
        except (ValueError, UnicodeError):
            self._json(400, {"error": "Invalid JSON"})
            return False, None

    def do_POST(self):
        if urlsplit(self.path).path != "/api/control":
            self._json(404, {"error": "Unknown API endpoint"})
            return
        valid, body = self._read_json_body()
        if not valid:
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
        except (sqlite3.Error, OSError) as exc:
            self._json(503, {"error": "SQLite persistence unavailable"})
        else:
            self._json(200, result)

    def do_PUT(self):
        if urlsplit(self.path).path != "/api/config":
            self._json(404, {"error": "Unknown API endpoint"})
            return
        valid, body = self._read_json_body()
        if not valid:
            return
        try:
            result = self.server.controller.configure(body)
        except (ValueError, TypeError) as exc:
            self._json(400, {"error": str(exc)})
        except ControlConflict as exc:
            self._json(409, {"error": str(exc)})
        except (sqlite3.Error, OSError) as exc:
            self._json(503, {"error": "SQLite persistence unavailable"})
        else:
            self._json(200, result)


class MotorPulseServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, server_address: tuple[str, int], *, seed: int = 42,
                 interval_seconds: float = 1.5, autostart: bool = True,
                 start_time_utc: datetime = DEFAULT_START_TIME_UTC,
                 step_seconds: float = 1.5,
                 assets: tuple[AssetScenario, ...] = DEFAULT_ASSETS,
                 database_path: str | Path | None = None):
        super().__init__(server_address, Handler)
        try:
            self.controller = SimulationController(
                seed=seed, interval_seconds=interval_seconds, autostart=autostart,
                start_time_utc=start_time_utc, step_seconds=step_seconds,
                assets=assets, database_path=database_path,
            )
        except BaseException:
            super().server_close()
            raise

    def server_close(self) -> None:
        self.controller.close()
        super().server_close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Local-only MotorPulse simulation lab")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--start-time-utc", type=parse_start_time_utc,
                        default=DEFAULT_START_TIME_UTC, metavar="UTC_ISO8601")
    parser.add_argument("--step-seconds", type=float, default=1.5,
                        help="virtual seconds advanced per tick (default: 1.5)")
    parser.add_argument("--interval-seconds", type=float, default=1.5,
                        help="wall-clock seconds between automatic ticks (default: 1.5)")
    parser.add_argument("--config", type=Path, metavar="FILE.json",
                        help="load a validated local motor/scenario JSON file before startup")
    parser.add_argument("--database", type=Path, metavar="PATH.sqlite3",
                        help="optional local persistent synthetic telemetry/alert SQLite file")
    parser.add_argument("--paused", action="store_true",
                        help="start paused at tick 1 for deterministic inspection")
    parser.add_argument("--port", type=int, default=8765, metavar="PORT",
                        help="localhost-only TCP port, 0 for a temporary port (default: 8765)")
    args = parser.parse_args()
    try:
        if not 0 <= args.port <= 65535:
            raise ValueError("--port must be an integer between 0 and 65535")
        assets = load_config_file(args.config) if args.config is not None else DEFAULT_ASSETS
        httpd = MotorPulseServer(("127.0.0.1", args.port), seed=args.seed,
                                start_time_utc=args.start_time_utc,
                                step_seconds=args.step_seconds,
                                interval_seconds=args.interval_seconds,
                                autostart=not args.paused, assets=assets,
                                database_path=args.database)
    except (OSError, ValueError, sqlite3.Error) as exc:
        parser.error(str(exc))
    with httpd:
        print(f"MotorPulse AI (synthetic demo): http://127.0.0.1:{httpd.server_address[1]}", flush=True)
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
