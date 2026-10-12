# MP-036 — Frozen synthetic regime robustness

MP-036 is a **post-hoc, repeatable analysis of existing MP-033 held-out synthetic experiments**, not a new trained model. It scores complete held-out source runs through the existing MP-011 evaluator and the original MP-035 portable model; source manifests, MP-030 split plan, train-only MP-034 feature processor, dataset cards, experiment index and exact stable-file hashes are verified before a robustness report is created.

## Reproduce

Python 3.11+, no runtime dependencies, offline only. Run from the repository root, with a newly created directory for the experiment and two new report paths:

    python -m motorpulse.experiment --config docs/examples/robustness-experiment-v1.json --out-dir /tmp/mp036-experiment
    python -m motorpulse.robustness --experiment-dir /tmp/mp036-experiment --partition test --out-json /tmp/mp036-test.json --out-md /tmp/mp036-test.md

Installed commands are motorpulse-experiment and motorpulse-robustness. For an exploratory validation-only slice, use --partition validation with different output paths. Training partition scoring is forbidden. The generated example uses distinct seeded **complete run groups** and a **predeclared asset scenario matrix**; the same seed/config/split algorithm reproduces the same data and source-bound model on the same runtime. Different generator seeds are not evidence of independent physical machines.

The analysis never injects altered data into an already trained source fingerprint. To test a different stress matrix, edit a **new MP-033 experiment configuration**, regenerate the whole source/split/model set, and treat the resulting independently trained model as a *different experiment*, not the same frozen model. Within each one experiment, the model, fit parameters, threshold and complete train/validation/test source memberships remain unchanged for every compared test condition. Results cannot support between-experiment model robustness claims.

## Conditions and metric semantics

The versioned JSON output contains by_stress slices for each of:

- Configured speed variation: 0, (0, 0.1], (0.1, 0.2] as fractions.
- Configured load variation: 0, (0, 0.15], (0.15, 0.3].
- Configured waveform noise: 0, (0, 0.05], (0.05, 0.1] in synthetic g settings.
- Configured per-tick drift: zero, negative/positive low, negative/positive high, threshold 0.0005 g/tick.
- Joint speed/load regimes, configured fault family, configured severity bucket, progression type and fault onset at tick 1 versus later.
- Effective synthetic fault type, *effective* severity bucket and effective fault phase at each tick, plus observed sensor quality. **Scheduled future faults are not positive labels** until the simulator's effective scenario becomes active.

For each slice, record total windows, source-run and track counts, eligible shared good-sensor windows, missing/outlier abstentions, and model/rule confusion counts, precision, recall, specificity, F1, FPR, non-interpolated score-ranked AP where defined and false alarms per **simulated negative-window exposure hour**. Rule-based AP is deliberately null: rules do not provide an ML ranking score.

Unlike configured scenario or run-level condition, window-level effective-fault, fault-strength, fault-phase and sensor-quality slices **do not compute episode delay**. Cutting a time series into discontiguous windows would fabricate new apparent fault onsets. Only slices containing complete, unaltered asset time tracks calculate first-effective-fault alert delays and missed/abstention-only episode counts. Even there, observed first-positive-tick delays are **not real failure lead times**. Episodes ending at a holdout boundary may be censored.

One-class slices correctly report null precision/recall/FPR/AP as applicable; no 0% or 100% is fabricated for an undefined denominator. A no-eligible-window sensor-quality slice has both method sample sizes equal to zero. Different bins can have different class prevalence and sample size. A change in error rate **does not establish a causal operating-condition effect**.

## Integrity and limitations

MP-035 artifact loading verifies source byte hashes, MP-030 train-group membership, run-specific dataset cards, MP-034 processor checksum, MP-010 training-only calibration and contract. MP-036 additionally verifies the MP-033 experiment file index and cross-checks overall confusion/coverage and episode counts with the unmodified MP-011 held-out report before emitting its own checksum. Reports are write-once files; a failure never replaces unrelated user files.

The synthetic example is a scripted educational comparison. Simulator seeded runs reuse the same underlying formulas; they are not domain-independent operating sites. No NASA IMS or CWRU raw data or redistribution, no unverified field labels, no hardware, no cloud services, no field-calibrated fault probability, no predictive maintenance recommendation or physical RUL. A checksum is an integrity check, not a cryptographic signature.

MP-037 will add human-readable side-by-side explanations and concrete false-positive examples; MP-038 may explore validation-only threshold tradeoffs without touching the test split.

## Follow-on MP-037: concrete disagreements and false positives

[MP-037](COMPARISON.md) complements these aggregate regime slices by reporting same-window decisions, original rule checks, numeric model distance decomposition and source-verified concrete false-positive examples. Both tools retain the frozen training threshold, shared good-sensor denominator, and strict synthetic-only limitations.
