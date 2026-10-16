# Beginner contribution ideas

A **good first contribution** to MotorPulse AI should be small, local, reproducible and easy to review. The ideas below deliberately focus on **documentation**, **tests**, **accessibility** and synthetic-only software behavior. They are contribution ideas, not pre-created GitHub issues; check open issues and `TODO.md` before starting so work is not duplicated.

## Boundaries first

- Use repository-generated or handwritten **synthetic-only** fixtures.
- **No hardware** access, PLC/SCADA integration, remote control, public-network exposure or production alarm behavior.
- Do not upload IMS/NASA archives, real machine telemetry, customer data, credentials or proprietary configurations.
- Do not turn synthetic metrics into claims about real diagnosis, failure probability, maintenance value or RUL.
- Every change should state clear **acceptance evidence**: a focused test, exact documentation check, or reproducible synthetic example.

## Small documentation tasks

### Check contributor links and command examples

Pick one contributor-facing guide and verify that every referenced local document exists and every command still matches an installed CLI entry point. Keep the change narrow; add a lightweight regression assertion when a stable public link or command should not drift again.

Acceptance evidence: name the checked guide, run its relevant `--help` command(s), and add/update a standard-library test if the contract is machine-checkable.

### Improve one troubleshooting case

Choose one reproducible local failure already supported by the software—such as port conflicts, write-once output collisions, disabled SQLite history or invalid synthetic config—and make the troubleshooting text more precise without changing behavior.

Acceptance evidence: cite the existing error/code in tests or source and show the updated troubleshooting entry maps to that behavior.

## Small test tasks

### Add a handwritten edge-case fixture

Add a minimal synthetic or handwritten fixture for a documented parser/validator boundary that is not currently obvious from existing tests. Keep the fixture tiny and do not copy external dataset rows.

Acceptance evidence: one focused regression test that fails for the unsupported/bad input and proves no unrelated files are overwritten.

### Strengthen a documentation contract

Find a stable public contract already described in `docs/`—for example a localhost API route, CLI command, safety caveat or model-card limitation—and add one precise assertion to the relevant documentation test. Avoid brittle assertions about prose that can legitimately change.

Acceptance evidence: explain which implemented behavior the assertion protects and run the focused test file plus the complete suite.

## Small accessibility tasks

### Improve one dashboard label or status message

Inspect the packaged local dashboard using keyboard navigation and a narrow viewport. Pick one control, table, status message or synthetic chart label whose programmatic label or explanatory copy can be made clearer without changing simulator semantics.

Acceptance evidence: add/update the existing HTML/JavaScript contract test and provide a synthetic-only screenshot only when it materially helps review.

### Improve missing-data explanation

Find one UI or documentation surface where `sensor_quality="missing"` or `"outlier"` could be mistaken for a healthy zero. Improve the copy while preserving the existing rule/model abstention behavior.

Acceptance evidence: a focused markup/documentation test that verifies the new explanation and confirms missing vibration is not represented as zero.

## How to propose one

Open the repository feature-request form and describe the exact problem, smallest change and acceptance evidence. Mention that it is intended as a beginner-sized contribution. If the work expands into a new data source, model family, public-network capability or hardware integration, stop and open a separate design discussion instead of silently broadening the patch.
