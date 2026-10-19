## Summary

Describe the smallest coherent change and the roadmap/task ID when one applies.

## Acceptance evidence

List the exact tests, generated artifacts, screenshots, reports, or other reproducible evidence that supports completion.

```bash
python -m unittest discover -s tests -v
```

## Review checklist

- [ ] The change is focused and does not silently broaden MotorPulse beyond a local-first software research lab.
- [ ] Tests were added or updated for changed behavior, or the reason no test is needed is explained above.
- [ ] The complete relevant test suite passes on a supported Python version; CI is expected to cover Python 3.11/3.12/3.13.
- [ ] **Documentation impact:** public behavior, commands, schemas, limits, assumptions, or examples are updated when needed.
- [ ] **Data/provenance impact:** any dataset/source change documents origin, rights/reuse uncertainty, checksums and split/leakage implications.
- [ ] **Security/local-first impact:** no public bind, unsafe path handling, secret exposure, hardware actuation, PLC command, or remote-control path was introduced.
- [ ] **No real-world performance claim:** synthetic metrics are not described as field validation, failure probability, industrial reliability, maintenance advice, or RUL.
- [ ] **No third-party raw or derived dataset** is added unless repository redistribution rights have been explicitly reviewed and documented.
- [ ] Model/preprocessing changes preserve whole-run split boundaries, train-only fitting, held-out evaluation and source-linked artifacts.
- [ ] Generated outputs are reproducible and do not overwrite unrelated user files.

## UI / report evidence

For dashboard, chart, report, or other user-visible changes, add a synthetic-only screenshot or generated example when it materially helps review. Do not include real machine telemetry, credentials, private paths or copyrighted control configurations.
