# MotorPulse AI release procedure

This guide prepares the first usable research tag, `v0.1.0`. The release remains a **synthetic-only**, local-first research artifact. It is not field performance evidence, a production monitoring service, an industrial safety system, or a real-machine maintenance recommendation.

## Release boundary

**Do not tag a stacked feature branch.** Create `v0.1.0` only after the intended milestone pull requests are integrated into `main`, the exact integrated `main` commit passes all seven quality jobs, and the release commit is reviewed. This candidate branch must not create a tag or GitHub Release.

The packaged server stays bound to `127.0.0.1`. It has no authentication layer because it is not intended for network exposure. No PLC integration, no remote control, no actuator path and no physical-equipment command is part of this release.

MotorPulse AI has **no RUL model**. The healthy-trained anomaly baseline is synthetic unusualness only; fixed rules are illustrative simulator thresholds. The dated metrics in `docs/BENCHMARK.md` are not field performance.

The optional container quick start is convenience tooling, not a deployment architecture. It uses host network mode only so MotorPulse can keep its loopback bind; host networking shares the host network stack. Docker is **not required** and native Python remains the primary supported path.

## 1. Verify the integrated source

From a clean checkout of the exact candidate commit on `main`:

```bash
python --version
python -m unittest discover -s tests -v
```

The expected release-candidate suite is **526 standard-library tests** on each supported Python version: 3.11, 3.12 and 3.13. GitHub Actions must show **all seven quality jobs** green: the three Python matrix jobs, changed-code Ruff/format, dependency policy, fresh-clone reproducibility, and the optional container quick-start build/run security smoke.

Confirm `pyproject.toml` contains version `0.1.0` and the Alpha development classifier. Verify no Python runtime or optional dependencies were introduced.

## 2. Reproduce the demo evidence

Read and reproduce the dated synthetic report:

- `docs/BENCHMARK.md`
- `docs/demo/benchmark-summary.svg`
- `docs/examples/experiment-v1.json`

The report is generated from repository synthetic data and a whole-run held-out evaluation. Preserve its provenance hashes and safety wording. Do not relabel its synthetic precision, recall, false-alarm rate or delay numbers as real-world performance.

Also review:

- `docs/MODEL_CARDS.md` for baseline intended use, failure modes and prohibited claims;
- `docs/SECURITY.md` for the localhost-only threat boundary;
- `docs/CONTAINER.md` for the optional host-network container tradeoff;
- `docs/DATA_PROVENANCE.md` and `docs/CWRU_INGESTION.md` for external-data rights caveats;
- `CHANGELOG.md` for the candidate release summary.

## 3. Check release contents and data rights

Before tagging, inspect the diff and archive contents. Do not include proprietary machine telemetry, credentials, local SQLite databases, private files, original NASA IMS archive records, IMS-derived samples whose redistribution has not been explicitly reviewed, or original/derived CWRU measurements without documented redistribution permission.

IMS and CWRU tooling may be included as code and documentation, but repository publication of original or derived measurements remains blocked under current project policy until a documented source-specific rights/redistribution review authorizes it. A public download link is not treated as an explicit redistribution grant.

Confirm the release still has no hardware control path, No PLC connection, and no remote control feature. The local API/dashboard and optional container are research/demo interfaces only.

## 4. Verify the container remains optional and local

If Docker is available on the verification host, run the checked-in optional quick start:

```bash
docker compose config
docker compose build
docker compose up -d
curl http://127.0.0.1:8765/api/health
docker compose down
```

The application itself must remain on `127.0.0.1`; do not change it to `0.0.0.0`, add Docker port publishing, tunnel it, or use a reverse proxy for this release. The permanent CI container job is the authoritative automated smoke check. Native Python must still work with no Docker installed.

## 5. Tag only the verified integrated commit

After **explicit approval**, while checked out at the exact green `main` commit:

```bash
git status --short
git rev-parse HEAD
git tag -a v0.1.0 -m "MotorPulse AI v0.1.0"
git push origin v0.1.0
```

Record the tagged commit SHA and the final GitHub Actions run in the release notes. If the source changes after verification, rerun all seven gates and tag the new verified commit instead; never move or force-rewrite a published release tag.

## 6. GitHub Release notes

A GitHub Release for `v0.1.0` should link the changelog, benchmark, model cards, install/testing guidance, container guide and demo SVG. State prominently that:

- results are synthetic-only and not field performance;
- the anomaly detector is not a failure probability or diagnosis;
- there is no RUL model;
- the server is unauthenticated and loopback-only;
- no PLC, actuator, sensor or remote-control integration is included;
- the optional container is not required and host network mode is not an authorization boundary;
- IMS and CWRU original/derived measurement redistribution is not granted by this release.

The release should not attach third-party raw/derived datasets or claim validation on physical machinery.
