# MP-038 — Validation-only anomaly threshold calibration (synthetic research)

The MP-010 baseline trains a single standardized Euclidean-distance anomaly score on **synthetic healthy good-sensor training runs only**. Its original MP-035 portable JSON model contains a *training-only in-sample 99th-percentile* alarm threshold. MP-038 explores an alternative, independent **validation-only operating point**, then applies it unchanged to the untouched test run(s). It **does not refit the model or replace its original train-calibrated threshold**.

## Reproduction

Python 3.11+ with no runtime dependencies, no network or hardware. Create **new** directories and output file names:

    python -m motorpulse.experiment --config docs/examples/robustness-experiment-v1.json --out-dir /tmp/mp038-experiment

    python -m motorpulse.calibration --experiment-dir /tmp/mp038-experiment --target-fpr 0.05 --out-json /tmp/mp038-calibration.json --out-md /tmp/mp038-calibration.md

Installed command: motorpulse-calibrate. Input is an existing **complete** MP-033 experiment with an intact index, model artifact, exact source manifests and dataset cards. Exports and experimental data remain purely synthetic. The existing original train-threshold MP-011 validation/test metrics are not altered.

## Selection design: validation only, test never tunes

1. Verify the MP-033 indexed source artifacts, MP-030 label-blind **whole-run** split, MP-032 cards, MP-034 train-only processor and MP-035 immutable portable trained model. First replay **validation only**, checking original MP-011 metrics, source counts, source hashes and original MP-003 rule results.
2. Mark an event positive **only** when its effective scripted synthetic fault is active; configured future fault or zero-strength ramps are **not** positives. Exclude missing/outlier sensors from **both** decision metrics. Scores come exclusively from the frozen model's five numeric features and training-fitted scales. No labels, rules or fault annotations enter scoring.
3. Given an empirical target validation FPR q in [0, 1], let N be the number of **eligible validation negatives**. The maximum count of allowed false positives is floor(q*N). Sort validation-negative scores descending, and choose the (allowed_fp+1)-th largest score as the threshold (or zero if every validation negative is permitted as an alarm). The decision is strictly **score > threshold**. This is the *lowest nonnegative cutoff* meeting the count budget, maximizing recall among such feasible cutoffs. Equal-score ties remain indivisible. If the validation sample has no eligible negatives, calibration fails rather than invent an FPR.
4. Report the selected threshold, target, allowed versus achieved validation false positives, original training threshold, validation metrics and a bounded descriptive validation-only tradeoff curve of at most 35 candidate cutoffs. For a one-class validation set, undefined class metrics appear as JSON null.
5. Only **after selection** read test truth to compute the original and new threshold operating-point metrics. The original model/checksums remain unchanged. No test-set class labels, rules, observations or failures influence threshold selection.

A selection at q=0 gives a threshold at least as large as the highest eligible validation-negative score and therefore no *observed validation* false positives. It is **not a guarantee of zero alerts** in new data, physical motors, or even the held-out synthetic test. q=1 means the lowest permitted threshold, zero; strict 'greater than' can still leave zero-valued scores unalerted. A target FPR is not a calibrated failure probability.

## Output and caution

The versioned JSON report contains source, split, original model, artifact and feature processor SHA-256 references, selection methodology, full shared sensor-good cohort counts and abstentions, original training-threshold baseline metrics, selected-threshold validation and test metrics, and original unmodified rule statistics. It also includes the list of representative validation-only threshold tradeoff points, source code/runtime metadata, scientific limitations and a deterministic report checksum. The Markdown report summarizes all comparisons.

Both methods' FPR and false alarms per **simulated eligible negative-window exposure hour** use *effective scripted synthetic truth*. Scores do not learn from validation/test labels; only the separate threshold is chosen using validation negatives. AP is a score-ranking metric and therefore invariant to the selected decision cutoff (when defined). Different partitions may have very different synthetic class prevalence. A favorable validation target might fail to hold on the untouched test partition or on unseen data.

The tool does not download or redistribute NASA IMS or CWRU data, claim field-calibrated reliability, predict physical failure, estimate maintenance lead time or RUL. The generator's repeated seeds do not establish real-world machine independence. Synthetic threshold validation is an educational operating-point comparison, not deployment guidance. For numerical rule explanations, use [COMPARISON.md](COMPARISON.md); for operating-condition slices use [ROBUSTNESS.md](ROBUSTNESS.md).

The report is write-once: both new output paths must be unused, and partial files created by the tool are removed on failure without deleting existing user files. The original training artifact is always read-only.
