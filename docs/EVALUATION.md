# MP-011 — Held-out detection metrics (synthetic evaluation only)

MotorPulse AI now evaluates a **frozen, trained MP-010 anomaly detector** and the **existing rule-based health logic** on exactly the same *eligible* events from MP-030's disjoint, whole-run **validation or test** partitions.

These are **software-generated experiments with scripted fault truth**, not evidence of physical machinery reliability, calibrated failure probability, predictive failure time, or remaining useful life (**RUL**). No original IMS archive is bundled or used for supervised evaluation; real IMS per-window fault labels, native physical units and derived-data redistribution rights are still unverified.

The evaluator never retrains a model, chooses a feature, changes a threshold, or uses validation/test labels for parameter fitting. MP-034 now independently verifies the model's [train-only fitted preprocessing](FEATURE_PIPELINE.md), exact source-run SHA-256s, feature/sampling contract and parameter consistency before scoring. Data leakage is checked through group identity, source integrity, split-plan hash, training provenance and model checksum, though shared simulator assumptions across seeds still constrain how strongly any result generalizes.

## 1. Reproducible end-to-end example

From the repository root on Python 3.11+ (no external dependencies), use **new output directories**:

```bash
mkdir -p datasets

python -m motorpulse.export --out-dir datasets/eval-11 --ticks 30 --seed 11 --format jsonl
python -m motorpulse.export --out-dir datasets/eval-22 --ticks 30 --seed 22 --format jsonl
python -m motorpulse.export --out-dir datasets/eval-33 --ticks 30 --seed 33 --format jsonl

python -m motorpulse.splits --source synthetic \
  --input datasets/eval-11/manifest.json datasets/eval-22/manifest.json \
          datasets/eval-33/manifest.json \
  --seed 42 --out datasets/eval-split.json

python -m motorpulse.anomaly \
  --split datasets/eval-split.json \
  --input datasets/eval-11/manifest.json datasets/eval-22/manifest.json \
          datasets/eval-33/manifest.json \
  --out datasets/eval-model.json

python -m motorpulse.evaluation \
  --split datasets/eval-split.json \
  --model datasets/eval-model.json \
  --input datasets/eval-11/manifest.json datasets/eval-22/manifest.json \
          datasets/eval-33/manifest.json \
  --partition test \
  --out datasets/eval-test-report.json \
  --markdown datasets/eval-test-summary.md
```

The installed command is `motorpulse-evaluate`. Omit `--markdown` to write JSON only. The full verified partition is evaluated even though the illustrative event preview is limited to 30 rows by default in the Python API. Output files are exclusively created: no existing artifact is replaced.

This pipeline rechecks each supplied synthetic export's JSONL/CSV file SHA-256 and exact byte lengths and rejects altered/missing run identities, forged split checksums, duplicate train/test groups, model hash mismatches, and non-training MP-010 model provenance. You must provide **all** original export manifests in the plan, not just the held-out files. The CLI refuses evaluating on the training partition.

## 2. Truth, eligibility, and rules

**Synthetic event-level ground truth:** an eligible window is positive exactly when its effective `scenario != "healthy"`, **not** when the configuration has a fault scheduled for a later tick (`configured_scenario`). In a progressive ramp, the first zero-strength tick can still have effective `scenario="healthy"`. The first tick with a *positive effective* scenario is the observed episode onset. We do not infer a real fault onset from this.

**Sensor quality:** `sensor_quality="good"` defines the shared evaluation cohort. Missing and injected outlier windows are **abstentions**, excluded from both rule and trained-model confusion denominators and PR ranking, with separate counts in `comparison_cohort.abstentions`. Their model score is null, not zero; they are neither classified healthy nor counted as detected faults. Abstentions still occupy time inside fault episodes.

**Thresholds:**
- Trained anomaly score: alert if standardized MP-010 `score > threshold`, where the threshold is frozen at the **training-only empirical 99th percentile**. This baseline is not a failure probability.
- Existing uncalibrated rules: `health="warning"` or `"critical"` means alert; `"normal"` means no alert. `"unavailable"` and `"suspect"` are compatible with unscorable sensor quality only and are not treated as healthy.
- Scaler means, scale floors, score threshold and feature allowlist cannot be re-estimated from held-out windows. The evaluator rejects source-run and model mismatches. `scenario`, `fault_phase`, label metadata and existing rule health are **evaluation fields only**, not model input features.

The default comparison includes all motors and test-run windows with good synthetic sensors. Both methods are evaluated on **exactly the same eligible windows**, not on arbitrarily filtered sets that make one system look better.

## 3. Metrics and correct denominators

Let TP, FP, TN and FN denote event-level counts on the shared eligible cohort, with scripted synthetic positive truth.

| Metric | Formula | When undefined |
|---|---|---|
| Precision | TP / (TP + FP) | No positive predictions |
| Recall / sensitivity | TP / (TP + FN) | No actual positives |
| Specificity | TN / (TN + FP) | No actual negatives |
| False-positive rate (FPR) | FP / (FP + TN) | No actual negatives |
| F1 | 2 TP / (2 TP + FP + FN) | No positives and no false alarms |
| Average precision (PR-AP) | Sum over distinct-score thresholds of Δrecall × precision | No eligible positive or no eligible negative events; only defined for the trained score |
| False alarms / simulated negative hour | FP / (Σ eligible negative-window step_seconds / 3600) | No eligible negative window exposure |

Undefined rates are **JSON null**, not a fabricated 0. The Markdown summary displays **undefined**. AP is a *non-interpolated average precision* computed over **descending raw anomaly scores** with exact score ties grouped before incrementing recall. This is not trapezoidal PR-AUC, and AP is **not** defined for rule outputs that only provide categorical health alerts.

**False alarms/hour** has a deliberately narrow denominator: each eligible *negative* synthetic event contributes one nominal virtual simulation step (often 1.5 simulated seconds). Overlapping measurement windows and different assets make this a **synthetic negative-window exposure convention**, not independently elapsed calendar/machine operation time. Never compare it directly with industrial false-alarm rates.

Where supported, the report includes breakdowns by **run**, **motor**, **nominal/variable operating regime**, and positive-only synthetic fault type (`imbalance`, `bearing_wear`, `misalignment`, `overload`). Fault-type rows supply **positive-only recall**; they do **not** invent per-fault specificity or precision. Small subgroup denominators are explicitly included, and missing groups are not manufactured.

## 4. Detection delay and missed synthetic episodes

Consecutive positive effective-scenario ticks on the *same source run, same motor, same fault type* form one episode. Normal/healthy ticks end an episode, while missing/outlier sensor events **do not** break it. The first positive tick, not the scheduled `onset_tick` configuration or future fault, defines observed onset.

- **Detected**: at least one good-sensor positive window has a trained anomaly score *strictly above* the training threshold.
- **Missed**: no such alert is observed before the episode ends (or the evaluation run ends). An episode with no eligible sensor windows is counted separately as `abstained_only`.
- **Delay**: `(first_model_alert_tick − first_positive_tick) × virtual_step_seconds`. A detection at onset has **0 seconds** delay. A missed episode's delay is **null**.
- **No physical lead-time estimate**: alerts before the synthetic onset are false positives, not measured maintenance lead time. An episode starting before a partition's beginning or continuing past its end is *observation-boundary censored*; this code does not reconstruct hidden pre-history.

The report provides detected/missed episode counts and mean/median delays **among detected episodes only**; missed episodes are not assigned zero, infinity, or made-up failure times. The output includes only synthetic metadata; no real IMS derived records are processed.

## 5. Output contracts and scientific interpretation

The JSON report includes `evaluation_version`, `partition`, `trained_model_sha256`, `split_plan_sha256`, source/run SHA-256 provenance, training/evaluated run IDs, the *frozen* threshold, eligibility/abstention counts, `overall.model`, `overall.rules`, by-run/motor/regime breakdowns, per-fault positive-only recall and synthetic episode details. `evaluation_sha256` hashes deterministic report content.

Evaluation is bounded to **60,000 held-out synthetic event windows** per report and keeps all metrics local. Each evaluated source is also bound to its actual MP-032 dataset-card ID and file digest; results never silently change the model. The machine-readable source IDs are reproducibility references, not proof of independently validated real hardware.

The two methods share an eligibility denominator, but a better synthetic precision/recall value **does not** prove predictive maintenance effectiveness. Results depend on seeded scripts, scenario mix, operating-load regimes, fault strengths and rules that were authored for the same artificial generator. No uncertainty interval or physical validation is claimed in MP-011; MP-033/MP-034 will formalize experiment reproducibility and improved leak-resistant feature pipelines.

Run checks locally (all data generated on the spot):

```bash
python -m unittest discover -s tests -p 'test_evaluation.py' -v
python -m unittest discover -s tests -v
```

The 21 regression tests cover numerical confusion matrices and PR-AP/tie handling, zero-positive/zero-negative edge cases, false alarms, onset/delay/missed episodes, quality abstentions, frozen training parameters, source/split tamper rejection, deterministic replay, operating-regime breakdowns and non-overwriting CLI outputs.

MP-035 adds [portable source-verified model artifacts](MODEL_ARTIFACTS.md), accepted by the `--model` CLI flag alongside legacy MP-010 model JSON; strict loading checks source/split/processor provenance before scoring. MP-033 now provides [strict-config reproducible experiments](EXPERIMENTS.md), running the same frozen MP-011 held-out evaluation on validation and test with a source-linked SHA-256 artifact index.

**References:** [MP-008 synthetic exports](DATASET.md), [MP-010 trained baseline](ANOMALY_BASELINE.md), [MP-030 leakage-aware group splits](SPLITS.md), [MP-032 dataset cards](DATASET_CARDS.md), and [data provenance / IMS rights](DATA_PROVENANCE.md).

## MP-036 robustness slices

For frozen-model, common-cohort comparisons across controlled synthetic speed/load, noise/drift, fault strength/onset and sensor quality, see [ROBUSTNESS.md](ROBUSTNESS.md). MP-036 verifies and reproduces the MP-011 held-out overall metrics before producing stress slices; no recalibration or source mutation is allowed. Window-only slices intentionally suppress episode-delay metrics to avoid spurious onsets.

## MP-037 — Same-window rule and model explanations

The [MP-037 comparison guide](COMPARISON.md) describes event-by-event provenance, independently rechecked original rule reasons, five-feature arithmetic distance accounting, nine alert/disagreement outcome categories and bounded concrete synthetic false-positive examples. Every reported event belongs to a verified held-out MP-030 complete-run partition, and both methods abstain on suspect/missing sensor windows. Report metrics are independently checked against the original MP-011 results. No new model fitting or test-set threshold tuning occurs.
