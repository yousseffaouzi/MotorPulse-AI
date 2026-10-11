# MotorPulse AI

**Software-first predictive-maintenance lab for industrial motors and rotating equipment.**

> **Status:** pre-alpha simulated prototype. The current alerts are explainable rule-based baselines, **not** a trained predictive-maintenance AI model. All demo measurements are synthetic; no hardware is required.

## What you can run today
- Reproducible simulated vibration, temperature and RPM signals for three motors.
- RPM-linked synthetic vibration at 1× and 2× shaft speed, plus illustrative bearing impacts.
- Feature extraction: vibration RMS, peak-to-peak amplitude and crest factor.
- Transparent rule-based health classification with fault examples.
- Local REST endpoints and a dashboard with Start/Pause/Step/Reset controls.
- Unit tests via the Python standard library. **No Docker, cloud account, or hardware required.**

## Quick start
Requires Python 3.11+.

```bash
python -m motorpulse
# open http://127.0.0.1:8765

# Optional reproducible configuration (virtual clock is separate from real speed):
python -m motorpulse --seed 42 --start-time-utc 2026-01-01T00:00:00Z --step-seconds 2 --interval-seconds 0.5
```

In another terminal, you can query a JSON snapshot:

```bash
curl http://127.0.0.1:8765/api/snapshot
curl http://127.0.0.1:8765/api/status

# Pause, then advance exactly one tick:
curl -X POST http://127.0.0.1:8765/api/control -H 'Content-Type: application/json' -d '{"action":"pause"}'
curl -X POST http://127.0.0.1:8765/api/control -H 'Content-Type: application/json' -d '{"action":"step"}'
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

- `motorpulse/signals.py` — synthetic RPM-related acceleration waveform fixtures.
- `motorpulse/sim.py` — reproducible synthetic source and baseline classification.
- `docs/SIGNALS.md` — sample-rate, Nyquist, harmonics, and modeling limitations.
- `motorpulse/controller.py` — thread-safe, timed simulator worker.
- `motorpulse/__main__.py` — localhost demo server.
- `docs/SIMULATION_CONTROL.md` — simulation controls and virtual clock configuration.
- `web/index.html` — zero-build dashboard.
- `docs/ARCHITECTURE.md` — design choices and future extensibility.
- `TODO.md` — issue-ready tracker with explicit status.

## Telemetry contract (v1)

The JSON snapshot now includes `schema_version`, stable per-simulation-event IDs, UTC measurement timestamps, explicit sensor units, sample rate and sample count. See [docs/TELEMETRY.md](docs/TELEMETRY.md), [the JSON Schema](docs/snapshot.schema.json), and [a validated example](docs/examples/snapshot-v1.json). Existing dashboard measurement fields remain compatible. Since MP-018, timestamps come from a deterministic **UTC virtual clock**, not the host wall clock. Tick 1 occurs at the configured start time (default: `2026-01-01T00:00:00+00:00`), and each tick advances by `--step-seconds` (default: 1.5). Reset reproduces the same complete JSON snapshot sequence. `--interval-seconds` controls execution speed only. The telemetry schema version remains 1.0.0.

## MP-019 signal sampling

Acceleration is generated at **1024 samples/second** over a **1-second window** (1024 samples; 1 Hz bin spacing). The shaft's 1× frequency is **RPM/60 Hz**, with a small 2× harmonic. The synthetic imbalance scenario increases 1× amplitude; bearing wear adds pulses at an **illustrative 4.8× ratio**, not a geometry-derived bearing defect frequency. The misalignment waveform is available as a test fixture, but is **not yet a selectable dashboard scenario** (MP-007). The timestamp is the virtual start of the acquisition window. Read [docs/SIGNALS.md](docs/SIGNALS.md) before interpreting these patterns.

## Developer CI

To limit GitHub Actions usage, tests run automatically on pull requests targeting `main` (not separately for feature pushes or merge pushes); manual runs remain available. Run `python -m unittest discover -s tests -v` locally first.

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
