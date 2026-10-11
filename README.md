# MotorPulse AI

**Software-first predictive-maintenance lab for industrial motors and rotating equipment.**

> **Status:** pre-alpha simulated prototype. The current alerts are explainable rule-based baselines, **not** a trained predictive-maintenance AI model. All demo measurements are synthetic; no hardware is required.

## What you can run today
- Reproducible simulated vibration, temperature and RPM signals for three motors.
- RPM-linked synthetic vibration at 1× and 2× shaft speed, plus illustrative bearing impacts.
- Five configurable synthetic scenarios: healthy, imbalance, bearing wear, misalignment, and overload; per-asset severity, onset, optional duration, and local JSON startup files.
- Feature extraction: vibration RMS, peak-to-peak amplitude, crest factor, Hann-windowed spectral features and 5-tick rolling summaries.
- Synthetic speed/load variability, vibration noise/drift, missing sensor intervals and outliers with explicit sensor-quality states.
- Transparent rule-based health classification with fault examples.
- Local REST endpoints and a dashboard with Start/Pause/Step/Reset controls.
- Unit tests via the Python standard library. **No Docker, cloud account, or hardware required.**

## Quick start
Requires Python 3.11+. **From a fresh clone**, you can run directly without installing:

```bash
python -m motorpulse
# open http://127.0.0.1:8765
```

Or install locally for development (macOS/Linux; on Windows activate the corresponding PowerShell virtual environment):

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e .
motorpulse-ai
```

The `motorpulse-ai` command and `python -m motorpulse` are equivalent; the dashboard is included with the installed package. To run at a different virtual clock speed:

```bash
python -m motorpulse --seed 42 --start-time-utc 2026-01-01T00:00:00Z --step-seconds 2 --interval-seconds 0.5
```

See [docs/INSTALL.md](docs/INSTALL.md) for wheel builds, offline options, cross-directory verification, and troubleshooting.

To **launch with a saved motor configuration**, e.g. a reproducible progressive-fault demo:

```bash
python -m motorpulse --config docs/examples/scenarios-progressive.json --paused
```

You may also add `--seed 72 --start-time-utc 2026-05-20T12:00:00Z --step-seconds 2.5 --port 8766`. The `--paused` flag leaves the simulator at tick 1 for deterministic inspection. Paths are relative to the current directory. See [docs/CONFIG_FILE.md](docs/CONFIG_FILE.md) for strict validation and examples.

In another terminal, you can query a JSON snapshot:

```bash
curl http://127.0.0.1:8765/api/snapshot
curl http://127.0.0.1:8765/api/status

# Pause, then advance exactly one tick:
curl -X POST http://127.0.0.1:8765/api/control -H 'Content-Type: application/json' -d '{"action":"pause"}'
curl -X POST http://127.0.0.1:8765/api/control -H 'Content-Type: application/json' -d '{"action":"step"}'
```

Run the complete standard-library test suite locally (64 prior tests plus packaging tests):

```bash
python -m unittest discover -s tests -v
```

For API contract tests only:

```bash
python -m unittest discover -s tests -p 'test_contracts.py' -v
```

See [docs/TESTING.md](docs/TESTING.md) for endpoint behavior, request validation, concurrency, replay coverage and known limitations.

## Software architecture

```text
Synthetic multi-motor simulator -> Signal features -> Transparent baseline rules
                                      |                         |
                                      +------- JSON API -------+
                                               |
                                       Browser dashboard
```

- `motorpulse/signals.py` — synthetic RPM-related acceleration waveform fixtures.
- `motorpulse/spectral.py` — dependency-free FFT, one-sided band power and harmonic peak estimates.
- `docs/SPECTRAL.md` — spectral frequency/units conventions, rollup definitions and limits.
- `docs/OPERATIONS.md` — operational variability, missing/outlier sensor behavior and caveats.
- `motorpulse/sim.py` — reproducible synthetic source and baseline classification.
- `docs/SIGNALS.md` — sample-rate, Nyquist, harmonics, and modeling limitations.
- `docs/SCENARIOS.md` — configuration API, fault types, severity and timing semantics.
- `motorpulse/config_file.py` / `docs/CONFIG_FILE.md` — bounded UTF-8 JSON startup loading and CLI guidance.
- `motorpulse/controller.py` — thread-safe, timed simulator worker.
- `motorpulse/__main__.py` — localhost demo server.
- `docs/SIMULATION_CONTROL.md` — simulation controls and virtual clock configuration.
- `motorpulse/web/index.html` — dashboard embedded in source and installed wheels.
- `docs/ARCHITECTURE.md` — design choices and future extensibility.
- `TODO.md` — issue-ready tracker with explicit status.
- `docs/TESTING.md` — API, replay, schema and concurrent-request regression test guide.
- `pyproject.toml` — installation metadata, console script and package asset inclusion.

## Telemetry contract (v1)

The JSON snapshot now includes `schema_version`, stable per-simulation-event IDs, UTC measurement timestamps, explicit sensor units, sample rate and sample count. See [docs/TELEMETRY.md](docs/TELEMETRY.md), [the JSON Schema](docs/snapshot.schema.json), and [a validated example](docs/examples/snapshot-v1.json). Existing dashboard measurement fields remain compatible. Since MP-018, timestamps come from a deterministic **UTC virtual clock**, not the host wall clock. Tick 1 occurs at the configured start time (default: `2026-01-01T00:00:00+00:00`), and each tick advances by `--step-seconds` (default: 1.5). Reset reproduces the same complete JSON snapshot sequence. `--interval-seconds` controls execution speed only. The telemetry schema version remains 1.0.0.

## MP-019 signal sampling

Acceleration is generated at **1024 samples/second** over a **1-second window** (1024 samples; 1 Hz bin spacing). The shaft's 1× frequency is **RPM/60 Hz**, with a small 2× harmonic. The synthetic imbalance scenario increases 1× amplitude; bearing wear adds pulses at an **illustrative 4.8× ratio**, not a geometry-derived bearing defect frequency. The misalignment scenario is also selectable in the dashboard. All fault amplitudes remain educational fixtures. The timestamp is the virtual start of the acquisition window. Read [docs/SIGNALS.md](docs/SIGNALS.md) before interpreting these patterns.

## Configurable fault scenarios (MP-007)

Use the dashboard to choose a fault for each motor and adjust its severity (0–1), onset tick, and optional duration. Clicking **Apply scenarios** atomically replaces the in-memory configuration, pauses, and resets the simulation to tick 1. These values are **illustrative**, not industrial severity calibration. The original seed and virtual clock settings are preserved.

For scripts, read `GET /api/config` and replace all assets with `PUT /api/config` using `Content-Type: application/json` (1–12 motors, validation before mutation). You can load a reproducible example:

```bash
curl -X PUT http://127.0.0.1:8765/api/config -H 'Content-Type: application/json' --data-binary @docs/examples/scenarios-v1.json
```

See [docs/SCENARIOS.md](docs/SCENARIOS.md) for behavior, input constraints and limitations. By default a scenario holds constant severity while active, preserving older configurations. MP-020 adds optional linear or exponential severity ramps.

## Progressive degradation simulation (MP-020)

The dashboard now supports `constant`, `linear`, and `exponential` **synthetic** fault progression. For a ramp, set target `severity`, `start_severity`, and `ramp_ticks` (at least 2, including both endpoints). Onset and optional duration work as before. The motor cards show current severity, phase, and a **configured trajectory preview** (not historical sensor readings). Reset deterministically replays the same ramp.

```bash
curl -X PUT http://127.0.0.1:8765/api/config -H 'Content-Type: application/json' --data-binary @docs/examples/scenarios-progressive.json
```

See [docs/PROGRESSION.md](docs/PROGRESSION.md) for exact ramp equations, validation, and limitations. These curves are illustrative only; no field calibration or remaining-useful-life model is claimed.

## Python packaging (MP-022)

MotorPulse AI is packaged as **motorpulse-ai 0.1.0.dev0** (development-only metadata; **not published to PyPI**). All runtime modules are standard-library-only; installing or building the wheel needs Python packaging tools. The single source of truth for the dashboard is now `motorpulse/web/index.html`, so it works after installing from a wheel even when launched from another working directory. See [docs/INSTALL.md](docs/INSTALL.md) for instructions and smoke checks.

## Spectral and rolling indicators (MP-023)

Per motor, the dashboard now shows Hann-windowed **1×/2× shaft peak amplitudes (g peak)**, **80–400 Hz acceleration band RMS (g RMS)**, and a **five-simulation-tick average of vibration RMS**. The frequency bin spacing is 1 Hz at the default 1024 Hz / 1024 sample window. An efficient dependency-free radix-2 FFT keeps the zero-runtime-dependency promise. The simulation history is per motor and only advances when a new synthetic tick is produced, never from polling; reset replays the same values. These indicators are *not* validated diagnostic thresholds or trained predictions. Full definitions: [docs/SPECTRAL.md](docs/SPECTRAL.md).

## Local scenario configuration (MP-024)

The CLI accepts `--config <local-file.json>` with the same validated `assets` schema as the existing configuration API. It rejects duplicate JSON keys, oversized or malformed files, invalid fault settings, and non-finite numbers **before opening the server**. `--paused` and `--port` allow isolated local testing. Runtime dependencies remain zero, and all options bind only to `127.0.0.1`. Documentation: [docs/CONFIG_FILE.md](docs/CONFIG_FILE.md).

## Operational variability and sensor events (MP-025)

Motors now support configured speed/load fluctuations, sensor noise, drift, missing vibration windows and outlier injections. The simulator keeps machine fault truth separate from the sensor status: missing vibration yields JSON `null` and `health="unavailable"`, while an injected outlier is `health="suspect"`. Neither automatically proves a motor defect. The dashboard shows these statuses and avoids displaying missing features as zero.

```bash
python -m motorpulse --config docs/examples/operations-v1.json --paused
```

Step through the simulation to inspect onset and recovery. Parameter limits, provenance, and simplified physical assumptions: [docs/OPERATIONS.md](docs/OPERATIONS.md).

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
