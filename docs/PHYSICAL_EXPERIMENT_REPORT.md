# Physical experiment reporting (MP-073)

This offline report summarizes an existing MP-072 final-test result and its
bound MP-069 validation result after complete approval/source integrity replay.
It does not select a model, change thresholds or authorize another experiment.

JSON includes source fingerprints, training asset/session/window coverage and
separate validation/test counts, coverage fractions, review flags and minimum,
median and maximum scores. Flag fraction uses scored windows as denominator;
abstention and scored fractions use all windows. A zero denominator produces
null (Undefined in Markdown), never a fabricated zero. These are descriptive
window-level quantities, not independent sample counts, fault classification
metrics or calibrated failure probabilities. No accuracy or false-alarm rate
can be inferred without appropriate verified labels.

Use the MP-072 command arguments, replace the module with
`motorpulse.physical_experiment_report`, add
`--final-test-result final-test-result.json`, and set
`--out experiment-report.json`. Optional `--format markdown` produces a
human-readable report instead. Both formats are write-once, and JSON is the
canonical machine-readable representation. The API can replay-validate JSON
against all exact inputs. Render only reports returned by the trusted builder.

MP-072 integrity replay uses bounded temporary feature copies (1 GiB aggregate)
and recomputes the fixed experiment, including the test result. The operator
must not tune on the test partition. Reviewer identity is not authenticated;
neither the report nor the write-once file is an authorization or one-shot ledger.
The existing JSON reader size limit applies to saved result inputs, and larger
experiments may require a later streaming report implementation.

The reports omit per-window identities and raw measurements but still contain
private experiment information. They remain local_only_do_not_redistribute.
All tests use generated fixtures. No field performance or industrial safety
claims are made. MP-016 remains ON HOLD.
