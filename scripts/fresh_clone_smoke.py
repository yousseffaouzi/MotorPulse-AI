#!/usr/bin/env python3
"""MP-046 fresh-checkout install/run/export/evaluate acceptance smoke test.

The script uses only the Python standard library. It creates an isolated virtual
environment, installs the current checkout using the documented editable-install
path, then runs all installed commands from a temporary directory outside the
repository. No real sensors, external datasets, or non-loopback services are used.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import time
from urllib.error import URLError
from urllib.request import urlopen
import venv


REPOSITORY = Path(__file__).resolve().parents[1]
SERVER_URL = "http://127.0.0.1:8765"


def _run(command: list[str], *, cwd: Path, env: dict[str, str], timeout: int = 120) -> str:
    result = subprocess.run(
        command,
        cwd=cwd,
        env=env,
        text=True,
        capture_output=True,
        timeout=timeout,
        check=False,
    )
    if result.returncode != 0:
        rendered = " ".join(command)
        raise RuntimeError(
            f"command failed ({result.returncode}): {rendered}\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )
    return result.stdout


def _venv_paths(environment: Path) -> tuple[Path, Path]:
    if os.name == "nt":
        scripts = environment / "Scripts"
        return scripts / "python.exe", scripts
    scripts = environment / "bin"
    return scripts / "python", scripts


def _console(scripts: Path, name: str) -> Path:
    suffix = ".exe" if os.name == "nt" else ""
    executable = scripts / f"{name}{suffix}"
    if not executable.is_file():
        raise RuntimeError(f"installed console script is missing: {name}")
    return executable


def _wait_for_local_server(process: subprocess.Popen[str]) -> None:
    deadline = time.monotonic() + 15
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"local server exited early with code {process.returncode}")
        try:
            with urlopen(SERVER_URL + "/api/health", timeout=1) as response:
                payload = json.load(response)
            if response.status == 200 and payload.get("status") == "ok":
                with urlopen(SERVER_URL + "/", timeout=1) as response:
                    dashboard = response.read().decode("utf-8")
                if response.status != 200 or "MotorPulse AI" not in dashboard:
                    raise RuntimeError("installed server did not serve the packaged dashboard")
                return
        except (OSError, URLError, TimeoutError, json.JSONDecodeError) as exc:
            last_error = exc
            time.sleep(0.2)
    raise RuntimeError(f"local server did not become healthy: {last_error}")


def _validate_export(folder: Path) -> Path:
    manifest = folder / "manifest.json"
    events = folder / "events.jsonl"
    if not manifest.is_file() or not events.is_file() or events.stat().st_size == 0:
        raise RuntimeError(f"synthetic export is incomplete: {folder.name}")
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    if (
        payload.get("dataset_type") != "synthetic_motor_feature_events"
        or payload.get("synthetic_only") is not True
    ):
        raise RuntimeError(f"unexpected export provenance in {manifest}")
    return manifest


def main() -> int:
    repository = REPOSITORY.resolve()
    if not (repository / "pyproject.toml").is_file():
        raise RuntimeError("fresh-clone smoke test must run from a MotorPulse-AI checkout")

    with TemporaryDirectory(prefix="motorpulse-mp046-") as temporary:
        root = Path(temporary).resolve()
        environment = root / "venv"
        work = root / "work"
        work.mkdir()
        if repository == work or repository in work.parents:
            raise RuntimeError("acceptance commands must run outside the source checkout")

        venv.EnvBuilder(with_pip=True, clear=True).create(environment)
        python, scripts = _venv_paths(environment)
        clean_env = dict(os.environ)
        clean_env.pop("PYTHONPATH", None)
        clean_env["PYTHONNOUSERSITE"] = "1"

        _run(
            [str(python), "-m", "pip", "install", "--disable-pip-version-check", "-e", "."],
            cwd=repository,
            env=clean_env,
        )
        print("MP-046 install: ok")

        _run([str(python), "-m", "motorpulse", "--help"], cwd=work, env=clean_env)
        server_command = _console(scripts, "motorpulse-ai")
        _run([str(server_command), "--help"], cwd=work, env=clean_env)

        server_log = root / "server.log"
        with server_log.open("w", encoding="utf-8") as log:
            process = subprocess.Popen(
                [str(server_command), "--paused"],
                cwd=work,
                env=clean_env,
                text=True,
                stdout=log,
                stderr=subprocess.STDOUT,
            )
            try:
                _wait_for_local_server(process)
            except Exception as exc:
                log.flush()
                details = server_log.read_text(encoding="utf-8", errors="replace")
                raise RuntimeError(f"installed local server smoke failed: {exc}\n{details}") from exc
            finally:
                if process.poll() is None:
                    process.terminate()
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait(timeout=5)
        print("MP-046 local server: ok")

        datasets = work / "datasets"
        datasets.mkdir()
        exporter = _console(scripts, "motorpulse-export")
        manifests: list[Path] = []
        for seed in (11, 22, 33):
            output = datasets / f"eval-{seed}"
            _run(
                [
                    str(exporter),
                    "--out-dir",
                    str(output),
                    "--ticks",
                    "30",
                    "--seed",
                    str(seed),
                    "--format",
                    "jsonl",
                ],
                cwd=work,
                env=clean_env,
            )
            manifests.append(_validate_export(output))
        print("MP-046 synthetic export: ok")

        split = datasets / "eval-split.json"
        model = datasets / "eval-model.json"
        report = datasets / "eval-test-report.json"
        markdown = datasets / "eval-test-summary.md"
        manifest_args = [str(path) for path in manifests]

        _run(
            [
                str(_console(scripts, "motorpulse-split")),
                "--source",
                "synthetic",
                "--input",
                *manifest_args,
                "--seed",
                "42",
                "--out",
                str(split),
            ],
            cwd=work,
            env=clean_env,
        )
        _run(
            [
                str(_console(scripts, "motorpulse-anomaly")),
                "--split",
                str(split),
                "--input",
                *manifest_args,
                "--out",
                str(model),
            ],
            cwd=work,
            env=clean_env,
        )
        _run(
            [
                str(_console(scripts, "motorpulse-evaluate")),
                "--split",
                str(split),
                "--model",
                str(model),
                "--input",
                *manifest_args,
                "--partition",
                "test",
                "--out",
                str(report),
                "--markdown",
                str(markdown),
            ],
            cwd=work,
            env=clean_env,
        )

        if not all(path.is_file() and path.stat().st_size > 0 for path in (split, model, report, markdown)):
            raise RuntimeError("held-out evaluation pipeline did not create all documented artifacts")
        evaluation = json.loads(report.read_text(encoding="utf-8"))
        if evaluation.get("partition") != "test":
            raise RuntimeError("fresh-clone evaluation did not use the held-out test partition")
        if not evaluation.get("evaluation_sha256") or not evaluation.get("trained_model_sha256"):
            raise RuntimeError("fresh-clone evaluation is missing provenance hashes")
        if "synthetic" not in markdown.read_text(encoding="utf-8").lower():
            raise RuntimeError("evaluation summary is missing its synthetic-data limitation")
        print("MP-046 held-out evaluation: ok")

    print("MP-046 fresh-clone reproducibility: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
