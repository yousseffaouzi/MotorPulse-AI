from pathlib import Path

RUN_ID = "38841694707"
HEAD_SHA = "20e913f96d0e21623f8b2259a46a3d5bc4372652"


def replace_once(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    if text.count(old) != 1:
        raise SystemExit(f"anchor mismatch in {path}: {old[:100]!r}")
    path.write_text(text.replace(old, new), encoding="utf-8")


# Tracker: evidence paragraph + DONE row only after the verified six-gate run.
todo = Path("TODO.md")
mp014 = (
    "- MP-014 implemented: added localhost-only standard-library `GET /api/stream` Server-Sent Events carrying atomic read-only synthetic snapshot/status state, with retry metadata and latest-state reconnect semantics but no replay buffer. The dashboard prefers EventSource and automatically retains the existing 1.5-second snapshot/status polling as fallback on unsupported/error/reconnect paths. Six regressions cover headers, non-mutation, explicit-step reconnect, local Host rejection and dashboard fallback contracts. GitHub Actions run `38830266363` passed the **504-test** supported-Python matrix plus lint/format, dependency policy and fresh-clone reproducibility; no CORS/public bind, WebSocket dependency, hardware integration or remote control was added.\n"
)
mp031 = (
    "\n- MP-031 implemented: added an optional, standard-library, **local-only** CWRU MATLAB-v5 adapter for user-supplied files, with bounded real-double vector parsing, optional zlib-compressed elements, explicit channel/bearing/fault/load/rate metadata, summary-only output, source/report SHA-256 provenance and a local-only dataset card. Seeded EDM fault conditions remain explicitly distinct from run-to-failure trajectories, failure time, failure probability and RUL; filenames are never used to infer labels. Ten regressions use only handwritten MATLAB-v5 bytes. Official CWRU pages were reviewed for source/test metadata, but an explicit dataset redistribution license was not established, so original/derived measurement redistribution remains **unverified and blocked by project policy**. GitHub Actions run `38841694707` passed **514/514** tests on Python 3.11/3.12/3.13 plus lint/format, dependency policy and fresh-clone reproducibility. The adapter has not been validated on a real CWRU archive file.\n"
)
replace_once(todo, mp014, mp014 + mp031)
replace_once(
    todo,
    "| MP-031 | TODO | P2 | Optional CWRU data adapter | Reuse terms and dataset card; distinguish seeded faults from run-to-failure |",
    "| MP-031 | DONE | P2 | Optional CWRU data adapter | Reuse terms and dataset card; distinguish seeded faults from run-to-failure |",
)

# Testing: suite count, inventory, and explicit evidence/limitations.
testing = Path("docs/TESTING.md")
replace_once(
    testing,
    "The suite contains **504 standard-library unittest test cases** (",
    "The suite contains **514 standard-library unittest test cases** (",
)
replace_once(
    testing,
    "6 bounded dashboard-export tests from MP-044, and 6 localhost SSE/reconnect/fallback tests from MP-014).",
    "6 bounded dashboard-export tests from MP-044, 6 localhost SSE/reconnect/fallback tests from MP-014, and 10 local-only CWRU MAT/parser/provenance/card tests from MP-031).",
)
anchor = (
    "Implementation evidence: GitHub Actions run `38830266363` passed all six permanent quality jobs on head `1fd033b6700af43c3d9e4516b0b9d6c5f931b65d`. The complete suite ran **504 tests** on Python 3.11, 3.12 and 3.13 (with the existing MP-015 Python-3.13-only benchmark byte-regeneration assertion skipped by design on 3.11/3.12); changed-code Ruff/format, dependency policy and fresh-clone reproducibility were also green.\n"
)
section = f'''\n## MP-031: local-only CWRU seeded-fault adapter\n\nTen standard-library regressions in `tests/test_cwru.py` pin the optional CWRU boundary. The tests construct handwritten MATLAB-v5 bytes in temporary directories; they do **not** download, embed or derive from CWRU measurements. Coverage includes ordinary and zlib-compressed matrix elements, strict explicit metadata, no filename-inferred labels, bounded fail-closed MAT parsing, summary-only reports, write-once offline CLI output, packaged template/run cards and unresolved redistribution rights.\n\n`motorpulse-cwru` accepts one user-supplied local MATLAB-v5 file plus a separate metadata JSON identifying the exact channel and seeded experimental condition. Output contains hashes and bounded descriptive summaries, never the raw sample vector or absolute local path. CWRU seeded EDM fault metadata is explicitly **not run-to-failure**: failure time, failure probability and RUL remain null. `motorpulse-card --source cwru` produces a path-free local-only provenance card and deliberately omits measurement summary values.\n\nOfficial CWRU Bearing Data Center pages were reviewed for source URLs and experiment metadata, but this project did not establish an explicit dataset-specific redistribution license there. Original or derived CWRU measurement publication therefore remains `unverified_for_redistribution` / `local_only_do_not_redistribute` under project policy. Passing these tests does not prove compatibility with every real CWRU MAT file or validate industrial diagnostic performance.\n\nImplementation evidence: GitHub Actions run `{RUN_ID}` passed all six permanent quality jobs on head `{HEAD_SHA}`. The complete suite ran **514/514** on Python 3.11, 3.12 and 3.13; changed-code Ruff/format, dependency policy and fresh-clone reproducibility were also green.\n'''
replace_once(testing, anchor, anchor + section)

# README: discoverability only; no new capability or claim.
readme = Path("README.md")
replace_once(
    readme,
    "- Optional bounded IMS-style **local-only** ASCII record importer using user-declared sampling metadata and no assumed defect labels.\n",
    "- Optional bounded IMS-style **local-only** ASCII record importer using user-declared sampling metadata and no assumed defect labels.\n- Optional bounded CWRU **local-only** MATLAB-v5 adapter using explicit seeded-fault metadata; no filename-inferred labels, run-to-failure claims, or bundled measurements.\n",
)
replace_once(
    readme,
    "- Versioned **dataset cards** for synthetic events and IMS source metadata, with local provenance-bound run cards and explicit licensing limitations.\n",
    "- Versioned **dataset cards** for synthetic events, IMS source metadata, and local-only CWRU seeded-fault metadata, with provenance-bound run cards and explicit licensing limitations.\n",
)
replace_once(
    readme,
    "- `motorpulse/ims.py` / `docs/IMS_INGESTION.md` — bounded, local, user-supplied IMS-style ASCII ingestion and provenance-only reports; no copied real archive data.\n",
    "- `motorpulse/ims.py` / `docs/IMS_INGESTION.md` — bounded, local, user-supplied IMS-style ASCII ingestion and provenance-only reports; no copied real archive data.\n- `motorpulse/cwru.py` / `docs/CWRU_INGESTION.md` — bounded, local, user-supplied CWRU MATLAB-v5 seeded-fault inspection with explicit metadata, summary-only reports and unresolved redistribution rights.\n",
)
