# Changelog

All notable project changes are documented here. MotorPulse AI follows semantic versioning for packaged releases.

## [0.1.1] - 2026-10-21

Patch-release candidate focused on Windows test reproducibility and checkout-independent synthetic provenance. This entry describes the intended `v0.1.1` contents; the tag must not be created until the release-prep work is merged and the exact integrated `main` commit passes the permanent quality gates.

### Fixed

- Added a permanent Windows Python 3.13 full-suite quality gate alongside the Linux 3.11/3.12/3.13 matrix; MP-053 PR run `39520517680` passed all eight quality jobs with **528 tests** on the supported full-suite jobs.
- Fixed Windows-only SQLite temporary-file cleanup failures in migration/storage test fixtures without changing production `SQLiteHistory` behavior.
- Canonicalized MotorPulse Python source line endings before source-provenance hashing so equivalent LF and CRLF checkouts produce the same synthetic export/run identity.
- Pinned deterministic benchmark Markdown/SVG and MotorPulse Python source files to LF where required for portable byte-stable provenance and generation checks.

### Boundaries

- No runtime or optional dependencies were added.
- No network exposure, authentication, hardware/PLC, actuator, remote-control, field-validation, RUL, or model-claim boundary changed.
- NASA IMS and CWRU redistribution restrictions remain unchanged; no third-party raw or derived measurements are added.
- The published `v0.1.0` tag remains immutable on its original release commit and is not moved or recreated by this patch release.

## [0.1.0] - 2026-10-16

First usable research release candidate for the local-first MotorPulse AI synthetic motor-monitoring lab.

### Included

- Deterministic multi-motor simulation with configurable healthy, imbalance, bearing-wear, misalignment and overload scenarios, progressive degradation, operating variability and injected sensor-quality problems.
- 1024 Hz / 1024-sample synthetic vibration windows with time-domain, spectral and rolling features, plus explainable illustrative rule alerts.
- Local dashboard and localhost-only HTTP API bound to `127.0.0.1`, optional read-only SSE live updates with polling fallback, optional SQLite v3 history/incident lifecycle, and strict bounded request/configuration parsing.
- Browser-only bounded synthetic history CSV/SVG exports, reproducible synthetic CSV/JSONL dataset export, dataset cards, whole-run leakage-resistant splits, healthy-only anomaly baseline, portable model artifacts, held-out evaluation, robustness/calibration studies and rule-versus-model explanations.
- Local-only IMS exploratory tooling with source/provenance checks. No original or derived IMS archive records are redistributed by the repository.
- Optional local-only CWRU MATLAB-v5 seeded-fault inspection with explicit metadata and provenance-only dataset cards. No original or derived CWRU measurements are bundled; redistribution rights remain unverified.
- Dated reproducible synthetic benchmark and self-contained demo media in `docs/BENCHMARK.md` and `docs/demo/benchmark-summary.svg`.
- Baseline disclosure and prohibited-claim guidance in `docs/MODEL_CARDS.md`, plus local-first security guidance, contributor templates, community issue forms and fresh-clone CI acceptance.
- Optional Docker/Compose quick start that preserves the application's `127.0.0.1` bind via host networking; native Python remains the primary supported path and Docker is not required.
- **526** standard-library tests across Python 3.11, 3.12 and 3.13, with changed-code Ruff/format, dependency-policy, fresh-clone reproducibility and live container quick-start security gates.

### Important limitations

- All benchmark metrics are synthetic research results, **not field performance** or evidence of physical machinery reliability.
- Rule thresholds are illustrative simulator defaults, not industrial alarm limits.
- The healthy-trained anomaly score is unusualness relative to scripted synthetic training data, not a failure probability or diagnosis.
- MotorPulse AI has **no RUL model**. MP-039 is metadata/audit methodology only and emits no remaining-useful-life predictions.
- No PLC, actuator, real-sensor, remote-control or production maintenance integration is provided.
- The HTTP service is unauthenticated and intentionally loopback-only; it is not approved for public-network exposure.
- The optional container uses host networking to retain the loopback bind. Host networking shares the host network stack and is not an additional authorization/security boundary.
- NASA IMS archive redistribution rights remain unresolved for repository publication; keep any local IMS data and derivatives out of commits/releases unless a documented rights review authorizes them.
- CWRU public downloads are not treated as an explicit redistribution license; keep original/derived CWRU measurements out of commits/releases unless a documented rights review authorizes them.

### Reproduce before release

Use `docs/RELEASE.md` for the final integrated-`main` verification and tag procedure. The candidate tag is `v0.1.0`; this preparation branch does **not** create it and is not itself a released tag.
