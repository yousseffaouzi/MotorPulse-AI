# MotorPulse AI

**Software-first predictive-maintenance lab for industrial motors and rotating equipment.**

> **Status:** pre-alpha simulated prototype. The current alerts are explainable rule-based baselines, **not** a trained predictive-maintenance AI model. All demo measurements are synthetic; no hardware is required.

## What you can run today
- Reproducible simulated vibration, temperature and RPM signals for three motors.
- Feature extraction: vibration RMS, peak-to-peak amplitude and crest factor.
- Transparent rule-based health classification with fault examples.
- Local REST endpoint and auto-refreshing browser dashboard.
- Unit tests via the Python standard library. **No Docker, cloud account, or hardware required.**

## Quick start
Requires Python 3.11+.

```bash
python -m motorpulse
# open http://127.0.0.1:8765
```

In another terminal, you can query a JSON snapshot:

```bash
curl http://127.0.0.1:8765/api/snapshot
```

Run tests:

```bash
python -m unittest discover -s tests -v
```

## Software architecture

```text
Synthetic multi-motor simulator -> Signal features -> Transparent baseline rules
                                      |                         |
                                      +------- JSON API -------+
                                               |
                                       Browser dashboard
```

- `motorpulse/sim.py` — reproducible synthetic source and baseline classification.
- `motorpulse/__main__.py` — localhost demo server.
- `web/index.html` — zero-build dashboard.
- `docs/ARCHITECTURE.md` — design choices and future extensibility.
- `TODO.md` — issue-ready tracker with explicit status.

## Telemetry contract (v1)

The JSON snapshot now includes `schema_version`, stable per-simulation-event IDs, UTC measurement timestamps, explicit sensor units, sample rate and sample count. See [docs/TELEMETRY.md](docs/TELEMETRY.md), [the JSON Schema](docs/snapshot.schema.json), and [a validated example](docs/examples/snapshot-v1.json). Existing dashboard measurement fields remain compatible. The timestamps are still wall-clock readings, not replayable simulated time (tracked under MP-018).

## Planned engineering work
1. Add configurable fault fixtures and labelled synthetic datasets.
2. Import publicly available NASA IMS bearing data *after confirming its reuse terms*; do not commit third-party data dumps.
3. Train and evaluate classical anomaly detectors against a reproducible baseline.
4. Add model cards, confusion matrices, robustness tests and clear failure modes.
5. Add persistent event storage, authenticated APIs, streaming, then hardware adapters in a **later, separate phase**.

## Safety and limitations
These scores are **not** validated failure probabilities or remaining useful life predictions. This demonstration is not industrial condition-monitoring equipment. Simulated data cannot establish real-world ML accuracy; independent field validation will be required.

## References
- NASA IMS bearings: https://data.nasa.gov/dataset/ims-bearings
- NASA Prognostics data repository: https://www.nasa.gov/intelligent-systems-division/discovery-and-systems-health/pcoe/pcoe-data-set-repository/

MIT-licensed software. See `LICENSE` and `CONTRIBUTING.md`.
