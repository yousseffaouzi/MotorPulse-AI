# MotorPulse AI release record and procedure

## Published v0.1.1 evidence

MotorPulse AI `v0.1.1` is the published reproducibility patch on top of the `v0.1.0` alpha research release. It hardens Windows test behavior and checkout-independent synthetic provenance without adding product capability or broadening the scientific/security boundary.

The release was completed only after the release-preparation work was integrated and the exact intended release commit passed all eight permanent quality jobs.

- Release tag: annotated `v0.1.1`
- Annotated tag object: `2f8176f54364c0da7f57ce6698aa4906d781d4df`
- Tagged commit: `8d8e4c9f9855f18de0e78937efffead5521753e1`
- Exact-`main` GitHub Actions run: `39524346340` / run number `221`
- Quality result: **all eight quality jobs passed**
- Full-suite baseline: **528 tests**, including Windows Python 3.13 and Linux Python 3.11/3.12/3.13
- GitHub Release ID: `429574626`
- GitHub Release: <https://github.com/yousseffaouzi/MotorPulse-AI/releases/tag/v0.1.1>
- Published at: `2026-10-30T23:13:21Z`
- Release state: public, non-draft, non-prerelease

The package metadata for the published release is `0.1.1` with the Alpha classifier. This GitHub release does **not** imply publication to PyPI.

### v0.1.1 preparation evidence

MP-053 was merged into `main` specifically to harden Windows reproducibility:

- MP-053 pull request: `#72`
- Verified MP-053 head: `0aa56a6ffa560013205bf621484a0268f502ff97`
- MP-053 tree: `3119a0ed72e7f350f8317136f39d1afdd525184b`
- MP-053 PR Quality Gates run: `39520517680` / run number `217`
- PR quality result: **all eight quality jobs passed**
- Full-suite baseline: **528 tests**, including the permanent Windows Python 3.13 gate and Linux Python 3.11/3.12/3.13 jobs
- MP-053 merge commit on `main`: `76cd2421dbfc2c5d0f77528b41474d363f3bfecc`

MP-054 release preparation then updated package metadata, changelog/release contracts, roadmap evidence and readiness tests. PR `#74` passed all eight permanent jobs before merge, then the exact integrated release commit `8d8e4c9f9855f18de0e78937efffead5521753e1` passed the manually dispatched exact-`main` run `39524346340` before the tag was created.

The MP-053 changes make SQLite test-fixture cleanup Windows-safe, make benchmark generation LF/CRLF-stable, canonicalize MotorPulse source line endings before synthetic provenance hashing, and add the permanent Windows Python 3.13 full-suite gate. Production runtime behavior, dependencies, external-data policy, and the local-only security boundary are unchanged.

The permanent quality set for `v0.1.1` is eight jobs: Linux Python 3.11, 3.12 and 3.13; Windows Python 3.13; changed-code Ruff/format; dependency policy; fresh-clone reproducibility; and the optional container quick-start build/run security smoke.

The project treats both published `v0.1.0` and `v0.1.1` tags as immutable. Never move, delete-and-recreate, force-update, or otherwise rewrite either tag. Post-release documentation or tracker commits belong after the tag on a normal branch/PR and do not change the released source snapshot.

---

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

The package metadata for the published release was `0.1.0` with the Alpha classifier. This GitHub release does **not** imply publication to PyPI.

The project treats the published `v0.1.0` tag as immutable. Never move, delete-and-recreate, force-update, or otherwise rewrite the tag. Post-release documentation or tracker commits belong after the tag on a normal branch/PR and do not change the released source snapshot.

## Release boundary

**Do not tag a stacked feature branch.** A release tag may only be created from the exact intended integrated `main` commit after that exact commit passes the permanent quality gates and after explicit approval to tag/release.

For `v0.1.0`, this boundary was satisfied by commit `42311ffb2e26d3f75484076bb86a3e607275cde1` and GitHub Actions run `39336825312`. Candidate-branch verification was review evidence only; the milestone became complete only when the annotated tag and GitHub Release actually existed.

For `v0.1.1`, this boundary was satisfied by commit `8d8e4c9f9855f18de0e78937efffead5521753e1` and GitHub Actions run `39524346340`. The tag was created only after that exact integrated commit passed all eight permanent quality jobs.

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

For `v0.1.1`, the expected suite is **528 tests** and the permanent workflow must show **all eight quality jobs** green, including Windows Python 3.13.

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

That procedure is historical evidence, not an instruction to recreate the tag. If source changes after a future version is verified, rerun all permanent gates and tag the new verified commit instead; never move or force-rewrite a published release tag.

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

After publication, update release-status documentation and the roadmap through a normal branch and pull request. These bookkeeping commits are intentionally **after** the immutable release tags and must not be used to move or recreate either `v0.1.0` or `v0.1.1`.
