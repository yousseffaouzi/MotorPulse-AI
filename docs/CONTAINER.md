# MP-052 — Optional local-only container quick start

The **native Python workflow remains the primary supported path** for MotorPulse AI. Docker is optional and **not required** for installation, testing, simulation, export, evaluation or development.

This container quick start exists for contributors who already use Docker and want an isolated, disposable demo process. It does not add a cloud deployment mode, public listener, authentication layer, hardware access, PLC integration or production service guarantee.

## Why this uses host networking

MotorPulse's MP-049 security contract requires the application itself to bind only to `127.0.0.1`; non-loopback server construction is rejected. A normal Docker bridge/published-port setup forwards traffic to the container's network interface, not to a service listening only on the container's loopback interface. MP-052 therefore does **not** weaken the application to listen on a container-wide `0.0.0.0` address.

Instead, `compose.yaml` uses:

```yaml
network_mode: host
```

There is **no port publishing**. With host networking, the container shares the host network stack, so MotorPulse's existing `127.0.0.1:8765` listener remains a localhost listener from the user's point of view.

This is a deliberate tradeoff: host networking has less network isolation than Docker's default bridge mode because the container shares the host network stack. The quick-start service therefore also runs non-root, uses a read-only root filesystem, drops all Linux capabilities, enables `no-new-privileges`, mounts no host directories or devices, and does not receive the Docker socket. Build and run only repository code you trust.

## Prerequisites

- Docker Engine on Linux with host networking support; or
- Docker Desktop **4.34 or later** with **Enable host networking** turned on in Docker Desktop settings.

Docker Desktop host networking is opt-in. If it is unavailable, disabled, incompatible with your security configuration, or undesirable for your environment, use the native Python quick start instead:

```bash
python -m motorpulse
# open http://127.0.0.1:8765
```

No Docker configuration change is required for the native path.

## Start the optional container

From the repository root:

```bash
docker compose up --build
```

Then open:

```text
http://127.0.0.1:8765
```

Or verify the local health endpoint:

```bash
curl http://127.0.0.1:8765/api/health
```

Expected JSON contains `"status":"ok"` and `"source":"simulation"`.

Stop and remove the disposable container with:

```bash
docker compose down
```

## What the image contains

`Dockerfile` starts from the official Python 3.13 slim Bookworm image and copies only the `motorpulse/` runtime package. It does not run `pip install`, install OS packages, add a reverse proxy, or add a third-party Python runtime dependency. The process runs as numeric non-root UID/GID `65532:65532` and starts the same `python -m motorpulse` module used by the native workflow.

The Docker build context excludes `.git`, local virtual environments, tests, documentation, local `data/` and `datasets/`, SQLite/database files, archives and package build outputs.

## Persistence and files

The supplied Compose quick start is intentionally **ephemeral** and read-only. It does not mount a database, configuration directory or output directory from the host. This avoids silently broadening local filesystem access and keeps MP-052 focused on a disposable dashboard/API demo.

If you need SQLite history, synthetic export files, local IMS/CWRU inspection, experiment artifacts or editable source workflows, use the documented native Python commands. Do not add arbitrary host mounts or the Docker socket merely to bypass the quick-start boundary.

## Local security checks

Permanent CI builds the image, starts it with the checked-in Compose file, verifies `/api/health` and the packaged dashboard through `127.0.0.1`, and confirms that an HTTP request carrying `Host: example.com` is still rejected with the MP-049 `invalid_host_header` response.

Host networking does **not** make MotorPulse a supported public-network service. Do not change the server to `0.0.0.0`, do not port-forward it, and do not use this container configuration as an authorization boundary. MotorPulse remains an unauthenticated local research/demo application with synthetic data and no physical-control capability.

## Limitations

- The optional image is a convenience wrapper around the same local Python application, not a deployment architecture.
- Docker itself, the Python base image and Docker Desktop/Engine are external tooling; MotorPulse's Python runtime remains standard-library-only.
- Host networking support and enablement differ by Docker platform/version. Native Python remains supported when the container path is unsuitable.
- No container test establishes real-world diagnostic accuracy, physical safety, failure probability or RUL validity.
