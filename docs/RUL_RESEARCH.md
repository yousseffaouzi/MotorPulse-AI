# MP-039 — Remaining Useful Life is a separate research track

**Status: research methodology and metadata checks only. NO TRAINED RUL MODEL. NO RUL PREDICTIONS.** The existing MP-010 anomaly detector, MP-038 alert-threshold selection and MP-011 first-alert delay do not yield physical time to failure. This protocol does not license or certify external bearing data and does not permit field maintenance decisions.

## Why MP-020 fault onset is not a failure time

MotorPulse's synthetic simulator schedules fault types, ramps and durations solely as generator controls. Fault onset, vibration excursions, anomaly scores, a rule warning, or reaching synthetic severity 1.0 **does not represent machine functional failure**. A simulated scenario can end with no residual damage. MP-011 measures synthetic onset-to-first-alert *detection delay*, not lead time to terminal failure. A countdown to the end of a simulation file is not RUL.

A future empirical RUL study needs independently observed terminal failure events or documented right-censored follow-up, an operational definition of functional failure, evidence sources, time origin, reviewed physical provenance and labels **before** any model training.

## Runnable versioned evidence contract (v1.0.0)

Use Python 3.11+ and the standard library only:

    python -m motorpulse.rul_research --protocol docs/examples/rul-protocol-v1.json --out-json /tmp/mp039-rul-audit.json --out-md /tmp/mp039-rul-audit.md

Installed command: **motorpulse-rul-audit**.

The example [rul-protocol-v1.json](examples/rul-protocol-v1.json) is **entirely fictional metadata** with invented event times, assets and evidence identifiers. It is not MotorPulse's simulation output or NASA IMS raw data. The audit intentionally returns **blocked**.

The root protocol contains study version, study identifier, data class, source, endpoint, train/validation/test split and trajectories. Its exact fields are strictly checked:

| Field | Meaning |
| --- | --- |
| rul_study_version | Strict 1.0.0 contract; unexpected fields/versions are refused |
| study_id | Human-readable study identifier |
| data_class | synthetic_method_fixture (blocked) or observed_run_to_failure (self-declared, NOT independently authenticated) |
| source | Dataset ID, citation, self-reported raw SHA-256 digest, rights review and terminal-event annotation review status |
| endpoint | Operational terminal failure definition, evidence kind, externally observed UTC timestamps, first-observation origin, seconds, censoring assumption |
| split | Asset-disjoint whole-trajectory train/validation/test group IDs |
| trajectories | Bounded records with asset identity, source group, acquisition period, endpoint/censoring status and source evidence reference |

Every trajectory requires a unique trajectory_id, asset_id, group_id, first_observed_utc, last_observed_utc, status, terminal_failure_utc, failure_evidence_ref, censoring_reason, and record_count. Exactly one outcome is allowed:

- **Observed terminal failure** (failure_observed): terminal event time on or after the last observed sensor sample, separately sourced evidence reference, and **no** censor reason. The external endpoint definition must be independently assessed to mean functional failure. Even if the event occurs after last sensor observation, no future information can enter a predictor.
- **Right-censored follow-up** (right_censored): terminal event time **null**, failure evidence **null**, and explicit reason administrative_end, lost_followup, sensor_loss, preventive_replacement, or competing_failure. Right censoring documents that failure was **not observed during follow-up**, not that the motor never fails.

Sensor loss, preventive replacement, and loss to follow-up may be informative; competing failure may require competing-risks methodology rather than naive noninformative right censoring. The auditor flags these for review.

The contract requires strict UTC timestamps (Z or +00:00), positive durations, unique run and trajectory identity, no overlapping same-asset trajectories, no crossing an asset between train/validation/test groups, at least one trajectory from every group, correct censor/event pairing, and bounded counts/files. A source SHA-256 **string is never verified against raw bytes by this tool**. No raw data is read or fetched, and no failure label or RUL is inferred.

## Audit outcomes are not modeling authorization

- **blocked**: synthetic input, unverified dataset rights, unverified failure annotations, synthetic failure endpoint or zero documented observed terminal failures.
- **metadata_complete_external_review_required**: supplied protocol fields satisfy preliminary structural checks. Independent source, endpoint, equipment, rights and label verification **still must occur**; metadata declarations alone are not trusted evidence.

Both statuses explicitly set provides_rul_estimates=false and allows_rul_model_training=false. The tool reports only declarations: number of trajectories, failures, censored cases, reason categories, split counts, declared elapsed seconds, provenance hashes and cautions. JSON/Markdown are write-once, deterministic and checksum linked. No industrial performance evidence is generated.

## Preregister future censor-aware metrics before modeling

| Measure | Required support and limitations |
| --- | --- |
| Censor-aware concordance | Comparable failure/censor pairs, tie policy, disjoint holdout; no comparable pairs = undefined |
| IPCW Brier score at preregistered horizons | Held-out survival probabilities, independent censor support, train-only censor estimator |
| Integrated IPCW Brier | Prespecified integration interval, positive censor support over the entire interval |
| Calibration by horizon | Predicted and censor-adjusted observed failure risk, adequate event counts, uncertainty bands |
| MAE among completed failures only (descriptive) | Does not cover censored runs, selection biased, never claim full-cohort RUL accuracy |

Report independent physical asset count, event/censor counts, follow-up distribution, missing/abstention counts, horizon coverage, uncertainty where estimable and JSON null for undefined metrics. A point RUL error on only completed lives does not establish general prognostic performance. No metric above is calculated in MP-039.

**Leakage safeguards:** split whole physical assets and trajectories before preprocessing; use only observations available at forecast time; never include terminal event/censor time, future interventions, configured simulator scenarios or full-life dataset-end features as model inputs. Fit preprocessing and censor estimators only on authorized training groups; tune on validation only; evaluate once on untouched physically separate test assets. Generator seed variability is not evidence of domain transfer.

## External prerequisites before any RUL model work

1. Identify independently licensed and reviewed observed run-to-failure or censored follow-up. Establish machine/bearing identity, raw data digests, rights and a reproducible provenance chain. Public catalog availability is not itself permission to redistribute raw or derived records.
2. Verify terminal failure evidence (instrumented run log, maintenance failure log or inspection outcome) and define functional failure, replacement, shutdown and end-of-test semantics separately. Do **not** label an experiment stop as failure by default.
3. Record observation start/end, actual terminal event or right-censoring cause, gaps/interventions and possible competing events.
4. Preregister horizons, censor assumptions, risk metrics, uncertainty, stratified evaluation and leakage controls. Require independent expert/rights review before authorizing real prognostic research.

**References:** NASA's [PCoE data repository](https://www.nasa.gov/intelligent-systems-division/discovery-and-systems-health/pcoe/pcoe-data-set-repository/) and [IMS Bearings metadata portal](https://data.nasa.gov/dataset/ims-bearings) describe a candidate experimental dataset, but neither automatically validates this project's labels or redistribution rights. [ISO 13381-1:2025](https://www.iso.org/standard/88029.html) publishes general prognostics-process guidance and requirements; MotorPulse does not claim compliance with the standard.

## Regression checks

    python -m unittest discover -s tests -p 'test_rul_research.py' -v
    python -m unittest discover -s tests -v

The tests check synthetic negative controls, terminal-event/censor contradictions, UTC chronology, source-group and asset leakage, same-asset overlap, rights/annotation status, fixed metric preregistration definitions, deterministic checksums, and write-once JSON/Markdown CLI behavior. They test metadata integrity, **not** prognostic accuracy. No external IMS records are imported by MP-039.
