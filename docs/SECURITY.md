# MotorPulse AI — Local-first security boundary (MP-049)

MotorPulse AI is an **unauthenticated**, local-only, software simulation and research lab. Its security model is intentionally narrow: the bundled HTTP server is for a trusted user on the same machine, not for LAN, Internet, multi-user, production or safety-critical exposure.

This document describes the implemented boundary. It is not a penetration-test report, certification, deployment architecture or claim that the application is secure for industrial use.

## Network boundary

The HTTP server binds to **`127.0.0.1` only**. Both the command-line launcher and the `MotorPulseServer` constructor enforce that address; there is no `--host`, `--bind` or `--listen` option that can opt into a wider interface. Port `0` is permitted for an operating-system-assigned local test port; otherwise valid TCP ports are 1 through 65,535.

HTTP requests must also carry a local **Host header**: `127.0.0.1` or `localhost`, optionally with a valid port. API requests with a missing, duplicate or non-local Host header fail with HTTP 400 and machine code `invalid_host_header`. This reduces accidental use through arbitrary hostnames while preserving ordinary local browser and test clients.

The service is **unauthenticated**. Any process or browser context that can reach the user's loopback listener can attempt requests. Loopback binding and Host checks are defense-in-depth for this local research tool; they are not a substitute for authentication, authorization, TLS, origin isolation or a production reverse proxy.

Do not port-forward the listener, publish it from a container, expose it through a tunnel or reverse proxy, or otherwise make it reachable from another machine. A networked or multi-user deployment would require a separate security design and review.

## HTTP request and query limits

Mutation endpoints accept JSON only and enforce the MP-043 parser boundary:

- maximum request body: **16,384 bytes**;
- required decimal `Content-Length` within that bound;
- UTF-8 JSON only;
- duplicate object keys rejected;
- `NaN`, `Infinity` and other non-standard JSON constants rejected;
- maximum JSON nesting depth: 64;
- unsupported API routes/methods fail closed with stable machine-readable error codes.

History and incident query parsing separately uses strict allowlists, bounded pagination and bounded query text. API responses use `Cache-Control: no-store` and `X-Content-Type-Options: nosniff`.

These controls limit accidental and hostile local input sizes. They do not make the server safe for hostile Internet traffic.

## Local files and paths

Startup scenario configuration is a local UTF-8 JSON file with a maximum size of **65,536 bytes**. The loader rejects a symlinked config file and any symlink component in its parent path before reading. It does not fetch URLs, interpret YAML, execute code or write back to the config file.

Optional SQLite persistence is also local-only and already rejects unsafe symlink paths and missing parent directories. Research/export commands use their own strict readers, provenance checks and write-once or non-overwrite rules where documented.

MotorPulse does not provide a sandbox around arbitrary local directories. Run it as an ordinary user in a directory whose filesystem permissions you trust; do not give it elevated privileges merely to access data or output paths.

## Control boundary

The live HTTP control surface changes **simulation state only**. The accepted control actions are `start`, `pause`, `step` and `reset`; configuration/runtime endpoints change only synthetic scenarios, seeds and simulated clocks. Incident acknowledgement records a local review label when SQLite history is enabled.

There is **no PLC** integration, **no remote control** of physical equipment, no GPIO/serial/fieldbus actuator interface, no SCADA command channel and no machinery shutdown/start capability. Unknown control actions are rejected as invalid requests.

MP-016 keeps real sensors, PLC, edge and remote deployment explicitly on hold pending separate evaluation and security approval.

## Safety and scientific claims

MotorPulse AI is **not an industrial safety system**. Its synthetic health rules, anomaly scores, incident lifecycle and research reports must not be used as protection logic or maintenance authorization for real machinery.

The project does not provide field-validated fault diagnosis, calibrated failure probability, guaranteed alarm rates, physical failure-time prediction or Remaining Useful Life. Model and dataset hashes support reproducibility/integrity checks only; they are not signatures, trust attestations or validation certificates.

## Operator checklist

Keep the server on `127.0.0.1`, use a normal unprivileged account, keep local config/database/output directories under your control, and stop the process when the local session is complete. Treat unexpected Host-header, request-validation or storage errors as reasons to investigate rather than bypass the checks.

For route/error details see [API.md](API.md); for startup/runtime configuration see [CONFIG_FILE.md](CONFIG_FILE.md); for common local failures see [TROUBLESHOOTING.md](TROUBLESHOOTING.md).