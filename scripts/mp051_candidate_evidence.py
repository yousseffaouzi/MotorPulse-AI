from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected exactly one anchor, found {count}")
    return text.replace(old, new, 1)


testing_path = ROOT / "docs" / "TESTING.md"
testing = testing_path.read_text(encoding="utf-8")
testing = replace_once(
    testing,
    "The suite contains **520 standard-library unittest test cases** (",
    "The suite contains **526 standard-library unittest test cases** (",
    "testing count",
)
testing = replace_once(
    testing,
    "10 local-only CWRU MAT/parser/provenance/card tests from MP-031, and 6 optional-container configuration/security/documentation tests from MP-052).",
    "10 local-only CWRU MAT/parser/provenance/card tests from MP-031, 6 optional-container configuration/security/documentation tests from MP-052, and 6 release-candidate readiness tests from MP-051).",
    "testing inventory",
)
section = """
## MP-051: v0.1.0 release-candidate preparation

Six standard-library contracts in `tests/test_release_readiness.py` pin the release-preparation boundary without pretending the release already exists. They require package version `0.1.0` with the Alpha classifier, a dated `CHANGELOG.md`, `docs/RELEASE.md`, README release navigation, the current 526-test/seven-gate baseline, synthetic-only/no-RUL/local-only safety caveats, IMS/CWRU redistribution uncertainty, and the optional-container/native-Python boundary. The tracker contract deliberately requires MP-051 to remain `TODO` until the real tag exists.

Candidate verification is not release completion. `v0.1.0` may be created only after the intended milestone work is integrated into `main`, the exact integrated `main` commit passes all seven permanent quality jobs, and explicit approval is given. The candidate branch must not create or move a tag, publish a GitHub Release, or weaken the localhost/security/data-rights boundaries.

Candidate evidence: GitHub Actions run `38843920706` passed all **seven** permanent quality jobs on human-authored head `f36f7ec1aa94dbcdbffa218a3d87280cc10b5e22`. The Python 3.11/3.12/3.13 matrix was green; the Python 3.13 log explicitly reported `Ran 526 tests` and `OK`. Fresh-clone reproducibility, changed-Python Ruff/format, dependency policy, and the live optional-container localhost/security smoke were also green. MP-051 remains TODO because no approved integrated-`main` tag has been created.

"""
anchor = "\nFor MP-035 portable JSON model artifacts, strict save/load and source validation:\n"
testing = replace_once(testing, anchor, "\n" + section + "For MP-035 portable JSON model artifacts, strict save/load and source validation:\n", "testing insertion")
testing_path.write_text(testing, encoding="utf-8")

todo_path = ROOT / "TODO.md"
todo = todo_path.read_text(encoding="utf-8")
mp052 = "- MP-052 implemented: added an **optional** Docker/Compose quick start without changing the MP-049 application bind. The image uses Python 3.13 slim, copies only the runtime package, installs no Python/OS dependencies, runs as non-root, and the supplied Compose service is read-only, drops all capabilities, enables `no-new-privileges`, mounts no host paths/devices/socket, and uses `network_mode: host` with **no port publishing** so MotorPulse continues listening on `127.0.0.1`. Six repository contracts keep native Python primary and pin the container/security/docs surface. GitHub Actions run `38842870063` passed **520/520** tests on Python 3.11/3.12/3.13 plus lint/format, dependency policy, fresh-clone reproducibility and the new live container build/run smoke, which verified localhost health/dashboard access and MP-049 `invalid_host_header` rejection. Host networking shares the host network stack and is an optional convenience, not a public deployment mode or security boundary.\n"
mp051 = "\n- MP-051 release-candidate preparation verified: package metadata is `0.1.0` / Alpha, `CHANGELOG.md` and `docs/RELEASE.md` carry the synthetic-only/security/data-rights caveats, and six readiness contracts keep the milestone incomplete until an actual tag exists. GitHub Actions run `38843920706` passed the **526-test** supported-Python matrix plus Ruff/format, dependency policy, fresh-clone reproducibility and the optional-container smoke on candidate head `f36f7ec1aa94dbcdbffa218a3d87280cc10b5e22`. **MP-051 intentionally remains TODO**: after explicit approval, `v0.1.0` must be created only from the exact integrated green `main` commit; no merge, tag or GitHub Release is claimed by candidate verification.\n"
todo = replace_once(todo, mp052, mp052 + mp051, "TODO MP-052 anchor")
todo_path.write_text(todo, encoding="utf-8")
