# Changelog

All notable project changes are documented here. MotorPulse AI follows semantic versioning for packaged releases.

## [0.1.0] - 2026-10-16

First usable research release candidate for the local-first MotorPulse AI synthetic motor-monitoring lab.

### Included

- Deterministic multi-motor simulation with configurable healthy, imbalance, bearing-wear, misalignment and overload scenarios, progressive degradation, operating variability and injected sensor-quality problems.
- 1024 Hz / 1024-sample synthetic vibration windows with time-domain, spectral and rolling features, plus explainable illustrative rule alerts.
- Local dashboard and localhost-only HTTP API bound to `127.0.0.1`, optional SQLite v3 history and incident lifecycle, and strict bounded request/configuration parsing.
- Reproducible synthetic CSV/JSONL export, dataset cards, whole-run leakage-resistant splits, healthy-only anomaly baseline, portable model artifacts, held-out evaluation, robustness/calibration studies and rule-versus-model explanations.
- Local-only IMS exploratory tooling with source/provenance checks. No original or derived IMS archive records are redistributed by the repository.
- Dated reproducible synthetic benchmark and self-contained demo media in `docs/BENCHMARK.md` and `docs/demo/benchmark-summary.svg`.
- Baseline disclosure and prohibited-claim guidance in `docs/MODEL_CARDS.md`, plus local-first security guidance, contributor templates and fresh-clone CI acceptance.
- **492** standard-library tests across Python 3.11, 3.12 and 3.13, with changed-code Ruff/format, dependency-policy and fresh-clone reproducibility gates.

### Important limitations

- All benchmark metrics are synthetic research results, **not field performance** or evidence of physical machinery reliability.
- Rule thresholds are illustrative simulator defaults, not industrial alarm limits.
- The healthy-trained anomaly score is unusualness relative to scripted synthetic training data, not a failure probability or diagnosis.
- MotorPulse AI has **no RUL model**. MP-039 is metadata/audit methodology only and emits no remaining-useful-life predictions.
- No PLC, actuator, real-sensor, remote-control or production maintenance integration is provided.
- The HTTP service is unauthenticated and intentionally loopback-only; it is not approved for public-network exposure.
- NASA IMS archive redistribution rights remain unresolved for repository publication; keep any local IMS data and derivatives out of commits/releases unless a documented rights review authorizes them.

### Reproduce before release

Use `docs/RELEASE.md` for the final integrated-`main` verification and tag procedure. The candidate tag is `v0.1.0`; this preparation branch does **not** create it.
