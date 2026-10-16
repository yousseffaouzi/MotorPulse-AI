# MotorPulse AI release procedure

This guide prepares the first usable research tag, `v0.1.0`. The release remains a **synthetic-only**, local-first research artifact. It is not field performance evidence, a production monitoring service, an industrial safety system, or a real-machine maintenance recommendation.

## Release boundary

**Do not tag a stacked feature branch.** Create `v0.1.0` only after the intended milestone pull requests are integrated into `main`, the exact integrated `main` commit passes all six quality jobs, and the release commit is reviewed. This preparation branch must not create a tag or GitHub Release.

The packaged server stays bound to `127.0.0.1`. It has no authentication layer because it is not intended for network exposure. No PLC integration, no remote control, no actuator path and no physical-equipment command is part of this release.

MotorPulse AI has **no RUL model**. The healthy-trained anomaly baseline is synthetic unusualness only; fixed rules are illustrative simulator thresholds. The dated metrics in `docs/BENCHMARK.md` are not field performance.

## 1. Verify the integrated source

From a clean checkout of the exact candidate commit on `main`:

```bash
python --version
python -m unittest discover -s tests -v
```

The expected release-candidate suite is 492 standard-library tests on each supported Python version: 3.11, 3.12 and 3.13. GitHub Actions must show **all six quality jobs** green: the three Python matrix jobs, changed-code Ruff/format, dependency policy, and fresh-clone reproducibility.

Confirm `pyproject.toml` contains version `0.1.0` and the Alpha development classifier. Verify no runtime or optional dependencies were introduced.

## 2. Reproduce the demo evidence

Read and reproduce the dated synthetic report:

- `docs/BENCHMARK.md`
- `docs/demo/benchmark-summary.svg`
- `docs/examples/experiment-v1.json`

The report is generated from repository synthetic data and a whole-run held-out evaluation. Preserve its provenance hashes and safety wording. Do not relabel its synthetic precision, recall, false-alarm rate or delay numbers as real-world performance.

Also review:

- `docs/MODEL_CARDS.md` for baseline intended use, failure modes and prohibited claims;
- `docs/SECURITY.md` for the localhost-only threat boundary;
- `docs/DATA_PROVENANCE.md` for external-data rights caveats;
- `CHANGELOG.md` for the candidate release summary.

## 3. Check release contents and data rights

Before tagging, inspect the diff and archive contents. Do not include proprietary machine telemetry, credentials, local SQLite databases, private files, original NASA IMS archive records, or IMS-derived samples whose redistribution has not been explicitly reviewed.

IMS tooling may be included as code and documentation, but repository publication of original or derived IMS data remains blocked until a documented rights/redistribution review authorizes it.

Confirm the release still has no hardware control path, No PLC connection, and no remote control feature. The local API and dashboard are research interfaces only.

## 4. Tag only the verified integrated commit

After explicit approval, while checked out at the exact green `main` commit:

```bash
git status --short
git rev-parse HEAD
git tag -a v0.1.0 -m "MotorPulse AI v0.1.0"
git push origin v0.1.0
```

Record the tagged commit SHA and the final GitHub Actions run in the release notes. If the source changes after verification, rerun all gates and tag the new verified commit instead; never move or force-rewrite a published release tag.

## 5. GitHub Release notes

A GitHub Release for `v0.1.0` should link the changelog, benchmark, model cards, install/testing guidance and demo SVG. State prominently that:

- results are synthetic-only and not field performance;
- the anomaly detector is not a failure probability or diagnosis;
- there is no RUL model;
- the server is unauthenticated and loopback-only;
- no PLC, actuator, sensor or remote-control integration is included;
- IMS archive/derived-data redistribution is not granted by this release.

The release should not attach third-party raw/derived datasets or claim validation on physical machinery.
