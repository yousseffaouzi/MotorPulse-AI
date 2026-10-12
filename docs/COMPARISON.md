# MP-037 — Explainable rules versus anomaly model

MP-037 produces an **auditable, offline side-by-side report** of the *existing* MP-003 illustrative threshold rules and *frozen* MP-010 anomaly model on the **same MP-030 held-out synthetic windows**. It explains disagreements and samples concrete false-positive, false-negative and sensor-abstention examples. This is a numerical software demonstration, **not** causal fault explanation or field predictive maintenance.

## Reproduce on a fresh Python 3.11+ checkout

Use the strict, self-generated eight-asset example (which includes simulated healthy variations, scripted faults, late onsets, missing and outlier sensor intervals):

    python -m motorpulse.experiment --config docs/examples/robustness-experiment-v1.json --out-dir /tmp/mp037-experiment
    python -m motorpulse.comparison --experiment-dir /tmp/mp037-experiment --partition test --max-examples 4 --out-json /tmp/mp037-test.json --out-md /tmp/mp037-test.md

The installed CLI is **motorpulse-compare**. Use --partition validation for exploratory validation-set comparisons; **training** is forbidden. --max-examples may be 0 through 12 per outcome, defaults to 4, and never limits the number of windows used for **metrics**. Output files are exclusively created, without overwriting; report JSON has a stable checksum. No external dependencies, Internet access or sensor hardware are needed.

## Verification, frozen scoring and eligibility

1. Recheck the original MP-033 experiment index and every indexed stable file hash, MP-035 portable JSON artifact, MP-030 disjoint grouped train/validation/test plan, local source manifests and MP-032 dataset cards. The MP-036 verifier independently reproduces frozen MP-011 held-out metrics.
2. Re-load the source-linked artifact and replay **all** events from every complete held-out run. Events require original sampling and rolling-window metadata.
3. For *good*-sensor windows, recompute the original MP-003 classify rules from RMS, temperature and crest factor; reject events whose recorded health or reason list differs. Score the same event with the original MP-010 frozen model and training-fitted MP-034 feature scales and threshold. No learned quantities are refitted or tuned on validation/test labels.
4. For simulated missing/outlier sensor windows, show **both methods abstaining**, with **null score** and no invented negative/healthy prediction.
5. Cross-check the complete common-cohort confusion, AP and false alarms per virtual negative-window hour, *plus per-run metrics*, with the original MP-011 report before writing any MP-037 report. Undefined denominators remain JSON null.

The report includes complete confusion metrics and a nine-way event accounting: model-only false positive, rules-only false positive, both false positives; model-only true positive, rules-only true positive, both true positives; neither-alert false negative, neither-alert true negative, and shared sensor abstention. The nine counts exhaust every held-out event, and the error counts are checked against both confusion matrices.

**Ground truth** means the simulator's *effective* fault scenario at a tick. A future configured fault is not a positive class before it activates, including a zero-strength progressive-ramp tick. Neither model nor rules consume future-fault truth as features.

## What an explanation actually means

A good-sensor example includes a source run, event, asset, tick, simulated UTC timestamp, configured-versus-effective scenario, sensor quality, both separate decisions, model score, fixed training threshold, score margin, model feature accounting, and rule predicates/reasons.

The trained model uses **only five ordered numeric inputs**: RMS acceleration, crest factor, 80–400 Hz band RMS acceleration, temperature and speed (RPM). For feature i, let z_i = (x_i - mu_i) / s_i, where the mean mu_i and scale s_i were fitted on healthy good-sensor **training** events only:

    score^2 = sum(z_i^2 / 5)
    feature_fraction_i = z_i^2 / sum(z_j^2)

For each feature, the report preserves unit, observed value, training-only center and scale, signed standardized deviation, nonnegative contribution to score squared and fraction of squared distance (zero when the score is zero). Contributions are checked to sum numerically to score squared. A high contribution indicates **distance from the training center**, not a diagnosed mechanical cause, learned causal feature importance or failure probability.

Rule explanations show their **actual** descriptive triggers and fixed thresholds: RMS >=0.36 g, temperature >=82 degrees C and crest factor >=2.7 with RMS >=0.20 g; critical at RMS >=0.55 g or temperature >=92 degrees C. These are educational simulator defaults, not ISO 20816 industrial vibration alarm thresholds.

## Sampling and careful interpretation

Examples select the **first N observed windows per outcome**, in deterministic whole-run and original JSONL order. The report states each category's complete count; no sample is claimed to be random or statistically representative, and an empty bucket yields an empty list. Reports include a complete-partition comparison and provenance hashes, not a dump of all private/local telemetry.

False positives are alerts where **effective scripted truth is healthy**, not experimentally verified physical faults or confirmations of imminent breakdown. A model-only false positive can be driven by simulated operating variability; a rules-only false positive can result from a fixed illustrative threshold. Both cases can coexist with a future configured fault which is **not yet active**. All numerical rates use virtual synthetic time, and multiple seeded generator runs share common equations and physics assumptions.

MP-036 supplies regime-level descriptive slices; MP-037 adds per-window numerical decision accounts and bounded concrete examples. MP-038 can separately research **validation-only** threshold calibration without using test labels. Neither feature gives RUL, real maintenance lead time, verified fault diagnosis, domain transfer reliability, or guidance to connect real motors.
