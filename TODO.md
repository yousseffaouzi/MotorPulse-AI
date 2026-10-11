# MotorPulse AI — master task tracker

**Scope:** software-only; no hardware integration or production operations in this phase.

Legend: `DONE`, `IN PROGRESS`, `TODO`, `ON HOLD`.

| ID | Status | Priority | Task | Acceptance evidence |
|---|---|---|---|---|
| MP-001 | DONE | P0 | Publish initial architecture and constraints | `README.md`, `docs/ARCHITECTURE.md` |
| MP-002 | DONE | P0 | Implement synthetic motor generator | Deterministic scenarios in `motorpulse/sim.py` |
| MP-003 | DONE | P0 | Add rule-based baseline scoring | Test coverage and explainable alerts |
| MP-004 | DONE | P0 | Expose localhost JSON API and starter dashboard | `python -m motorpulse` |
| MP-005 | DONE | P0 | Add unit tests and CI workflow | `python -m unittest discover -s tests -v` |
| MP-006 | TODO | P0 | Formalize telemetry schema + event timestamps | Versioned sample JSON + tests |
| MP-007 | TODO | P0 | Build multi-scenario fault injection controls | Reproducible, documented scenarios |
| MP-008 | TODO | P1 | Add synthetic dataset export + dataset card | CLI CSV export + provenance |
| MP-009 | TODO | P1 | Build NASA IMS ingestion (respect dataset terms) | Ingestion tests against small fixtures |
| MP-010 | TODO | P1 | Establish ML baselines with proper train/test splits | Evaluation report + reproducible script |
| MP-011 | TODO | P1 | Compare false positive rate and detection delay | Metrics documented, limitations explained |
| MP-012 | TODO | P1 | Persist history with SQLite adapter | Schema migrations and integration tests |
| MP-013 | TODO | P2 | Improve charts, filtering and accessible UI | Browser smoke tests/screenshots |
| MP-014 | TODO | P2 | Add optional streaming endpoint | WebSocket/SSE integration tests |
| MP-015 | TODO | P2 | Publish demo video and benchmark report | README media links and dated evidence |
| MP-016 | ON HOLD | P3 | Real sensors, PLCs or edge deployment | Only after software validation and hardware approval |

Tracker is an initial plan, not evidence of production readiness.
