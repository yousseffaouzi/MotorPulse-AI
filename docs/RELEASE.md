# MotorPulse AI v0.1.0 release record

MotorPulse AI `v0.1.0` is the first published alpha research release of the local-first synthetic motor-monitoring lab. It remains a **synthetic-only** research artifact. It is not field performance evidence, a production monitoring service, an industrial safety system, a real-machine maintenance recommendation, a calibrated failure-probability model, or a remaining-useful-life product.

## Published v0.1.0 evidence

The release was completed only after the intended work was integrated into `main` and the exact integrated commit passed all seven permanent quality jobs.

- Release tag: annotated `v0.1.0`
- Annotated tag object: `0e3caa376557663bdae14cf9fecced70706702c8`
- Tagged commit: `42311ffb2e26d3f75484076bb86a3e607275cde1`
- Tagged tree: `066e61d9d9b5beb9ef6a09a3288cf6d8073589bc`
- Exact-`main` GitHub Actions run: `39336825312`
- Quality result: **all seven quality jobs passed**
- Supported-Python test suite: **526 tests** on Python 3.11, 3.12 and 3.13
- GitHub Release ID: `418979228`
- GitHub Release: <https://github.com/yousseffaouzi/MotorPulse-AI/releases/tag/v0.1.0>
- Published at: `2026-10-20T23:24:54Z`
- Release state: public, non-draft, non-prerelease

The package metadata remains `0.1.0` with the Alpha classifier. This GitHub release does **not** imply publication to PyPI.

The project treats the published `v0.1.0` tag as immutable. Never move, delete-and-recreate, force-update, or otherwise rewrite the tag. Post-release documentation or tracker commits belong after the tag on a normal branch/PR and do not change the released source snapshot.

## Release boundary

**Do not tag a stacked feature branch.** A release tag may only be created from the exact intended integrated `main` commit after that exact commit passes the permanent quality gates and after explicit approval to tag/release.

For `v0.1.0`, this boundary was satisfied by commit `42311ffb2e26d3f75484076bb86a3e607275cde1` and GitHub Actions run `39336825312`. Candidate-branch verification was review evidence only; the milestone became complete only when the annotated tag and GitHub Release actually existed.

The packaged server stays bound to `127.0.0.1`. It has no authentication layer because it is not intended for network exposure. No PLC integration, no remote control, no actuator path and no physical-equipment command is part of this release.

MotorPulse AI has **no RUL model**. The healthy-trained anomaly baseline is synthetic unusualness only; fixed rules are illustrative simulator thresholds. The dated metrics in `docs/BENCHMARK.md` are not field performance.

The optional container quick start is convenience tooling, not a deployment architecture. It uses host network mode only so MotorPulse can keep its loopback bind; host networking shares the host network stack. Docker is **not required** and native Python remains the primary supported path.

## 1. Verify the integrated source

For a future release, start from a clean checkout of the exact candidate commit on `main`:

```bash
python --version
python -m unittest discover -s tests -v
```

For `v0.1.0`, the expected suite was **526 standard-library tests** on each supported Python version: 3.11, 3.12 and 3.13. GitHub Actions had to show **all seven quality jobs** green: the three Python matrix jobs, changed-code Ruff/format, dependency policy, fresh-clone reproducibility, and the optional container quick-start build/run security smoke.

Confirm `pyproject.toml` contains the intended semantic version and development classifier. Verify no unintended Python runtime or optional dependencies were introduced.

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
- `CHANGELOG.md` for the release summary.

## 3. Check release contents and data rights

Before tagging any future release, inspect the diff and archive contents. Do not include proprietary machine telemetry, credentials, local SQLite databases, private files, original NASA IMS archive records, IMS-derived samples whose redistribution has not been explicitly reviewed, or original/derived CWRU measurements without documented redistribution permission.

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

The application itself must remain on `127.0.0.1`; do not change it to `0.0.0.0`, add Docker port publishing, tunnel it, or use a reverse proxy as a supported deployment path. The permanent CI container job is the authoritative automated smoke check. Native Python must still work with no Docker installed.

## 5. Historical v0.1.0 tag procedure

After **explicit approval**, `v0.1.0` was created from the exact green `main` commit with an annotated tag:

```bash
git status --short
git rev-parse HEAD
git tag -a v0.1.0 -m "MotorPulse AI v0.1.0"
git push origin v0.1.0
```

That procedure is historical evidence, not an instruction to recreate the tag. If source changes after a future version is verified, rerun all seven gates and tag the new verified commit instead; never move or force-rewrite a published release tag.

## 6. GitHub Release notes

A GitHub Release should link the changelog, benchmark, model cards, install/testing guidance, container guide and demo SVG. State prominently that:

- results are synthetic-only and not field performance;
- the anomaly detector is not a failure probability or diagnosis;
- there is no RUL model;
- the server is unauthenticated and loopback-only;
- no PLC, actuator, sensor or remote-control integration is included;
- the optional container is not required and host network mode is not an authorization boundary;
- IMS and CWRU original/derived measurement redistribution is not granted by the release.

The release must not attach third-party raw/derived datasets or claim validation on physical machinery.

## 7. Post-release bookkeeping

After publication, update release-status documentation and the roadmap through a normal branch and pull request. These bookkeeping commits are intentionally **after** the immutable release tag and must not be used to move or recreate `v0.1.0`.
