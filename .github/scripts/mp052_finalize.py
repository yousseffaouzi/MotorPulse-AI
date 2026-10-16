from pathlib import Path

RUN_ID = "38842870063"
HEAD_SHA = "b9da0018a1329e2a8c5a782564216daa0cf6c347"


def replace_once(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    if text.count(old) != 1:
        raise SystemExit(f"anchor mismatch in {path}: {old[:120]!r}")
    path.write_text(text.replace(old, new), encoding="utf-8")


todo = Path("TODO.md")
mp031 = (
    "- MP-031 implemented: added an optional, standard-library, **local-only** CWRU MATLAB-v5 adapter for user-supplied files, with bounded real-double vector parsing, optional zlib-compressed elements, explicit channel/bearing/fault/load/rate metadata, summary-only output, source/report SHA-256 provenance and a local-only dataset card. Seeded EDM fault conditions remain explicitly distinct from run-to-failure trajectories, failure time, failure probability and RUL; filenames are never used to infer labels. Ten regressions use only handwritten MATLAB-v5 bytes. Official CWRU pages were reviewed for source/test metadata, but an explicit dataset redistribution license was not established, so original/derived measurement redistribution remains **unverified and blocked by project policy**. GitHub Actions run `38841694707` passed **514/514** tests on Python 3.11/3.12/3.13 plus lint/format, dependency policy and fresh-clone reproducibility. The adapter has not been validated on a real CWRU archive file.\n"
)
mp052 = (
    "\n- MP-052 implemented: added an **optional** Docker/Compose quick start without changing the MP-049 application bind. The image uses Python 3.13 slim, copies only the runtime package, installs no Python/OS dependencies, runs as non-root, and the supplied Compose service is read-only, drops all capabilities, enables `no-new-privileges`, mounts no host paths/devices/socket, and uses `network_mode: host` with **no port publishing** so MotorPulse continues listening on `127.0.0.1`. Six repository contracts keep native Python primary and pin the container/security/docs surface. GitHub Actions run `38842870063` passed **520/520** tests on Python 3.11/3.12/3.13 plus lint/format, dependency policy, fresh-clone reproducibility and the new live container build/run smoke, which verified localhost health/dashboard access and MP-049 `invalid_host_header` rejection. Host networking shares the host network stack and is an optional convenience, not a public deployment mode or security boundary.\n"
)
replace_once(todo, mp031, mp031 + mp052)
replace_once(
    todo,
    "| MP-052 | TODO | P2 | Optional containerized quick start | Simple Dockerfile/Compose; native Python remains supported |",
    "| MP-052 | DONE | P2 | Optional containerized quick start | Simple Dockerfile/Compose; native Python remains supported |",
)

testing = Path("docs/TESTING.md")
replace_once(
    testing,
    "The suite contains **514 standard-library unittest test cases** (",
    "The suite contains **520 standard-library unittest test cases** (",
)
replace_once(
    testing,
    "6 localhost SSE/reconnect/fallback tests from MP-014, and 10 local-only CWRU MAT/parser/provenance/card tests from MP-031).",
    "6 localhost SSE/reconnect/fallback tests from MP-014, 10 local-only CWRU MAT/parser/provenance/card tests from MP-031, and 6 optional-container configuration/security/documentation tests from MP-052).",
)
anchor = (
    "Implementation evidence: GitHub Actions run `38841694707` passed all six permanent quality jobs on head `20e913f96d0e21623f8b2259a46a3d5bc4372652`. The complete suite ran **514/514** on Python 3.11, 3.12 and 3.13; changed-code Ruff/format, dependency policy and fresh-clone reproducibility were also green.\n"
)
section = f'''\n## MP-052: optional local-only container quick start\n\nSix standard-library contracts in `tests/test_container_quickstart.py` keep the optional container path subordinate to the native Python workflow. They pin the minimal Python 3.13 slim image, non-root execution, no package installation in the image, host-network Compose mode with no port mapping, read-only filesystem, dropped capabilities, `no-new-privileges`, no volumes/devices/Docker socket, bounded build context, native-Python fallback documentation and the permanent CI smoke-job definition. The Python contracts themselves do not require Docker.\n\nThe permanent quality workflow now has a seventh `Container quick start` job on Ubuntu. It validates and builds `compose.yaml`, starts the checked-in image, polls `http://127.0.0.1:8765/api/health`, loads the packaged dashboard and sends an explicit non-local `Host: example.com` request that must still fail with `invalid_host_header`. This proves the optional wrapper preserves the MP-049 application-level loopback/Host contract on the tested CI platform.\n\nThe Compose design deliberately uses `network_mode: host` rather than changing MotorPulse to listen on `0.0.0.0`. There is no port publishing. Host networking shares the host network stack and therefore has less network isolation than Docker's default bridge mode; `docs/CONTAINER.md` requires Docker Engine host-network support or Docker Desktop 4.34+ with host networking enabled, and keeps native Python as the primary path. No container result establishes public-deployment safety, industrial validation, failure probability or RUL validity.\n\nImplementation evidence: GitHub Actions run `{RUN_ID}` passed all **seven** permanent quality jobs on head `{HEAD_SHA}`. The complete suite ran **520/520** on Python 3.11, 3.12 and 3.13 (with the existing MP-015 Python-3.13-only benchmark byte-regeneration assertion skipped by design on 3.11/3.12); changed-code Ruff/format, dependency policy, fresh-clone reproducibility and the live container build/run security smoke were green.\n'''
replace_once(testing, anchor, anchor + section)
