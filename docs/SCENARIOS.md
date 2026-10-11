# MP-007 — Configurable fault scenarios

MotorPulse AI is a **local-only, synthetic** simulation. Fault labels, severity and sensor magnitudes are teaching assumptions, not validated diagnostic evidence or failure probabilities. This release does not estimate remaining useful life.

## Config format and controls

Get the currently configured motors with `GET /api/config`. Replace the **entire** set with `PUT /api/config`, with `Content-Type: application/json` and the following body:

```json
{
  "assets": [
    {"asset_id":"MTR-01","name":"Conveyor motor","scenario":"healthy","severity":0,"onset_tick":1,"duration_ticks":null},
    {"asset_id":"MTR-02","name":"Pump motor","scenario":"imbalance","severity":0.6,"onset_tick":3,"duration_ticks":10},
    {"asset_id":"MTR-03","name":"Fan motor","scenario":"bearing_wear","severity":1,"onset_tick":1,"duration_ticks":null}
  ]
}
```

The **browser dashboard** exposes the same controls. You can also submit a saved JSON configuration:

```bash
curl -X PUT http://127.0.0.1:8765/api/config -H 'Content-Type: application/json' --data-binary @docs/examples/scenarios-v1.json
```

Rules: 1–12 unique `asset_id` values (uppercase letters, digits, underscores and hyphens; initial letter required), display names 1–80 characters, one of five supported scenario names, finite severity from 0 to 1, onset tick from 1 to 100000, duration null (indefinite) or 1–100000 ticks. `healthy` requires severity 0. Unknown fields, invalid configurations and duplicate IDs return 400 **without altering the active simulation**. A valid update pauses and resets the virtual clock to tick 1 while preserving seed and clock settings.

The *effective* fault applies from `onset_tick` (inclusive) through `onset_tick + duration_ticks` (exclusive); otherwise readings are healthy. The `scenario` and `severity` telemetry fields represent the **effective** state, while `configured_scenario`, `configured_severity`, `onset_tick`, and `duration_ticks` preserve the scheduled settings. `Reset` replays the same configuration, not the original defaults. Values stay constant during an active fault; gradual degradation remains MP-020.

## Simplified fault fixtures

| Scenario | Fault strength at severity 1 | Modeling assumption |
|---|---|---|
| healthy | 0 | 1x = 0.12 g, 2x = 0.015 g, temperature near 47°C |
| imbalance | 1x = 0.62 g | 1x acceleration scales toward synthetic imbalance; temperature +13°C at strength 1 |
| bearing_wear | 1x = 0.22 g and illustrative bumps | 4.8x phase-repeating impulses scaled linearly by severity; temperature +35°C |
| misalignment | 2x = 0.28 g | Increased 2x component; temperature +9°C |
| overload | 1x = 0.20 g | Simplified thermal overload; temperature +50°C |

For all fault scenarios, sine amplitude changes linearly between the healthy and fault assumptions as severity varies from 0 to 1. Noise comes from the same reproducible generator and all frequencies remain tied to RPM. These values are not physically calibrated; bearing 4.8x is invented, not calculated from bearing geometry. See [SIGNALS.md](SIGNALS.md).

**Limitations:** Multiple clients share one local in-memory configuration. Nothing persists across process restarts. Physical fault progression, run-specific identifiers, event history and security for network deployment are separate roadmap items.
