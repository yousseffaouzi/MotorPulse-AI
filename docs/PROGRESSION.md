# MP-020 — Progressive synthetic fault trajectories

**Simulation only.** These curves demonstrate fault onset, progression and alert timing. They are not physical bearing wear laws, failure probabilities, remaining useful life (RUL) estimators or industrial maintenance thresholds. Real datasets such as NASA IMS will be evaluated separately.

## Configuration

The existing `GET /api/config` / `PUT /api/config` and dashboard editor support three **optional** fields on each asset:

- `progression`: `constant` (the backwards-compatible default), `linear`, or `exponential`.
- `start_severity`: number in [0,1], default 0, the strength at the fault onset for progressive profiles.
- `ramp_ticks`: integer [2,100000] for progressive profiles; null for constant.

Existing `severity` is the **target** (0–1), `onset_tick` is inclusive and `duration_ticks` is the optional number of active ticks. Progressive scenarios must have a non-healthy fault and positive target, `start_severity < severity`, `ramp_ticks >= 2`, and if a duration is specified `duration_ticks >= ramp_ticks`. Constant scenarios require `start_severity = 0` and `ramp_ticks = null`. The healthy fault requires severity 0.

Load a working demonstration:

```bash
curl -X PUT http://127.0.0.1:8765/api/config -H 'Content-Type: application/json' \
 --data-binary @docs/examples/scenarios-progressive.json
```

A valid config pauses and resets the in-memory simulator to tick 1. Invalid configurations return HTTP 400 without altering the current settings or snapshot. Reset reproduces the same numeric measurements, severity, phases and simulated timestamps.

## Ramp definition

Let `o` be onset, `r` the ramp length, `s0` the start and `s1` the target severity. For ticks `t` during the ramp, normalized ramp progress `p=(t-o)/(r-1)` ranges from 0 to 1.

- **constant:** effective strength is `s1` starting at onset.
- **linear:** `s(t)=s0+(s1-s0)*p`.
- **exponential:** `s(t)=s0+(s1-s0)*(exp(4p)-1)/(exp(4)-1)`.

A progressive fault reaches its target exactly at tick `o+r-1` and remains there until its optional duration ends. Before onset and after expiration, effective severity is 0. At zero strength the effective fault label is `healthy`, even if the fault is scheduled. There is no residual or cumulative physical wear after expiration.

The constant 4 is an arbitrary dimensionless curve parameter. The model does **not** claim experimental validation.

## Telemetry and dashboard

In addition to previous v1 fields, each new snapshot event includes `progression`, `start_severity`, `ramp_ticks`, `ramp_fraction` (0–1 position in the configured ramp, **not** the fault strength), and `fault_phase`: `healthy`, `scheduled`, `ramping`, `steady`, or `ended`. They are additive optional telemetry fields, so old v1 fixtures remain valid.

The browser displays current effective synthetic severity and a **planned profile preview**. It is not a measured historical trend; data persistence and real time-series plots remain MP-012/MP-013.

## Validation and further reading

```bash
python -m unittest discover -s tests -v
```

Tests cover linear and exponential boundaries, fault onset and expiration, nonzero starts, strict input validation, identical replay after reset, alert development and atomic API configuration errors.

- [NASA IMS Bearings](https://data.nasa.gov/dataset/ims-bearings)
- [NASA PCoE bearing datasets](https://www.nasa.gov/intelligent-systems-division/discovery-and-systems-health/pcoe/pcoe-data-set-repository/)
- El-Thalji and Jantunen (2015), *A summary of fault modelling and predictive health monitoring of rolling element bearings*, https://doi.org/10.1016/j.ymssp.2015.02.008
