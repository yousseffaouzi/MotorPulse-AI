# Contributing

This project is at the early software-only prototype stage. Contributions to documentation, accessible UI, synthetic test scenarios, automated tests and simulation fidelity are welcome.

1. Open an issue explaining the desired change.
2. Fork the repository and create a focused feature branch.
3. From a local Python 3.11+ environment, optionally run `python -m pip install -e .`; add or update tests and run `python -m unittest discover -s tests -v`. See [the installation guide](docs/INSTALL.md), [model assumptions](docs/MODEL_ASSUMPTIONS.md), and [dataset cards](docs/DATASET_CARDS.md) before changing sensor features, labeling claims, provenance or source-license status.
4. Open a pull request with screenshots or example outputs if UI/telemetry changes.

Please don't submit proprietary machine telemetry, credentials, private datasets or copyrighted industrial control configurations. IMS archives and **real-data-derived reports or feature tables** must remain outside GitHub until rights are verified. Update `motorpulse/cards/*.json`, card validation and tests together when changing provenance conventions. ML contributions must enforce [whole-run splits](docs/SPLITS.md) and [healthy-only training boundaries](docs/ANOMALY_BASELINE.md); never fit preprocessing or thresholds on held-out records. Evaluation changes must preserve the [MP-011 shared eligibility and denominator contracts](docs/EVALUATION.md), separating sensor abstentions from true-positive/false-positive classifications.
