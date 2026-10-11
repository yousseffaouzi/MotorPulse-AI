# IMS bearing data — provenance, access and reuse review (MP-027)

**Reviewed:** 2026-10-11 (UTC) · **Status:** METADATA REVIEW COMPLETE; RAW-DATA / DERIVATIVE REDISTRIBUTION **ON HOLD** pending a dataset-specific rights review. No original archive has been downloaded, inspected, or committed by MotorPulse AI. This is a project policy rather than a legal ruling.

The machine-readable source card is [sources/ims-bearings.source.json](sources/ims-bearings.source.json). Read [MODEL_ASSUMPTIONS.md](MODEL_ASSUMPTIONS.md) to distinguish this *real experimental bearing dataset* from MotorPulse AI's wholly **synthetic** motor simulation.

## Official record and citation

- Original provider: **Center for Intelligent Maintenance Systems (IMS), University of Cincinnati**; the PCoE citation also credits Rexnord Technical Services.
- Distributor: **NASA Ames Prognostics Center of Excellence (PCoE)**, not the original experimenter.
- [NASA PCoE data repository](https://www.nasa.gov/intelligent-systems-division/discovery-and-systems-health/pcoe/pcoe-data-set-repository/), section **4. Bearings**. This is the source of the prescribed dataset citation, donation credit and repository-acknowledgment request.
- [NASA Open Data: IMS Bearings](https://data.nasa.gov/dataset/ims-bearings) — catalog entry, `other-license-specified` badge and legacy ZIP resource.
- [U.S. data.gov mirror](https://catalog.data.gov/dataset/ims-bearings) — catalog metadata, including a general U.S. government-works URL.
- [NASA Science Data licensing guidance](https://science.data.nasa.gov/about/license) — source/rights verification guidance where NASA is not the original producer.
- [PHM Society NASA repository mirror](https://data.phmsociety.org/nasa/) — a mirror, **not the original data producer**.

### Citation for future publications

J. Lee, H. Qiu, G. Yu, J. Lin, and Rexnord Technical Services (2007). IMS, University of Cincinnati. *Bearing Data Set*. NASA Prognostics Data Repository, NASA Ames Research Center, Moffett Field, CA.

Credit **both** the dataset contributors and the PCoE repository when referencing the experimental data. Cite the original data rather than a third-party Kaggle or GitHub copy.

## Rights findings — keep evidence and uncertainty separate

| Question | Review finding | Status |
|---|---|---|
| Can someone locate the archive on NASA's public site? | Yes; NASA lists a downloadable bearing archive and credits IMS at University of Cincinnati | **Confirmed metadata** |
| Does NASA request donor/repository acknowledgment? | Yes; the PCoE repository asks researchers who publish using its data to acknowledge both | **Confirmed** |
| Does the catalog provide a clear dataset-specific CC0/CC-BY/SPDX grant? | No explicit dataset-specific standardized grant established by this review: the website badge is `other-license-specified` | **Unverified** |
| Does a metadata link to U.S. government-works guidance establish ownership of IMS-donated data? | Not necessarily; the original provider is external. NASA advises independently verifying associated rights for non-NASA-source data | **Insufficient to grant redistribution** |
| May MotorPulse AI bundle original ZIPs, reconstructed waveforms, or derived tables in GitHub? | **Not yet approved** under project policy; seek dataset-specific terms/permission | **HOLD** |
| Can we direct users to the original NASA-hosted archives with proper citation? | Yes; links and instructions are offered without republishing the data | **Approved for documentation** |
| Did this milestone download data or discover a license file inside the ZIP? | No; this review used publicly visible metadata only | **Not performed** |

A *public download*, a repository-acknowledgment request, and NASA's general licensing guidance are **not substitutes for a dataset-specific license grant**. This document intentionally does not declare the archive public-domain, CC0, CC-BY, or freely redistributable. Distribution of **derived features** also awaits review; aggregating data does not automatically resolve downstream reuse rights.

The [NASA Science Data licensing guidance](https://science.data.nasa.gov/about/license) distinguishes NASA-origin mission data from other materials whose ownership or usage rights should be independently checked. The [PCoE source page](https://www.nasa.gov/intelligent-systems-division/discovery-and-systems-health/pcoe/pcoe-data-set-repository/) states the data are donated and disclaims liability; its acknowledgment request does not by itself specify a redistribution license.

### Permission clarification (not sent)

Before distributing the archive or derived datasets, request written clarification from the repository/dataset rights holders. NASA PCoE lists `christopher.a.teubert@nasa.gov` and `chetan.s.kulkarni@nasa.gov` as dataset-repository contacts as of the review date. Ask whether **open-source GitHub publication**, **rehosting original files**, **distribution of per-window features** and **commercial reuse** are permitted, and what citation/license notices apply. Record the reply, sender, date, scope and source URL, then update the source card. **No contact has been made by this project in this milestone.**

## Archive locations and optional user-side acquisition

The following URLs are **documented upstream resources**, not copies distributed by MotorPulse AI:

- NASA catalog ZIP: `https://data.nasa.gov/docs/legacy/IMS.zip`
- NASA PCoE listed file: `https://phm-datasets.s3.amazonaws.com/NASA/4.+Bearings.zip`

The resources may be different **packagings**, revisions or mirrors. Do **not** assume equal sizes, byte hashes, ZIP structure or licenses. Their contents and reachability at download time still require verification.

**Only after reviewing applicable terms**, a contributor who personally needs the data can run the following commands *locally*, without committing anything. This command is **an instruction, not a claim that this review downloaded the data**:

```bash
mkdir -p data/raw/ims
curl --fail --location --show-error \
  'https://phm-datasets.s3.amazonaws.com/NASA/4.+Bearings.zip' \
  --output data/raw/ims/4.Bearings.zip

python - <<'PY'
from pathlib import Path
import hashlib
p = Path("data/raw/ims/4.Bearings.zip")
h = hashlib.sha256()
with p.open("rb") as stream:
    for chunk in iter(lambda: stream.read(1024 * 1024), b""):
        h.update(chunk)
print("archive_name:", p.name)
print("bytes:", p.stat().st_size)
print("sha256:", h.hexdigest())
PY
```

Store the **actual** acquisition timestamp, obtained filename, number of bytes, SHA-256 and exact download URL in a separate local acquisition log. Do **not** replace the source card's `null` archive hash/size/date with guessed values or hashes copied from an unrelated mirror. Check nested archives, embedded READMEs, notices and any license file before processing; extraction of unfamiliar archives requires normal path-traversal/size protections.

The repository ignores `data/raw/` and `data/external/` to reduce the risk of accidentally committing third-party original data. This is not a security control: contributors must still review `git status` before committing, including forced additions and other paths.

## Data and benchmark verification plan (MP-009 / MP-028)

The following are **expected investigation items, not findings from an inspected archive**:

1. Confirm that recordings are divided into multiple run-to-failure experiments and map **physical bearing**, **test/run**, **acquisition channel**, and **record/timestamp** uniquely. Do not identify a file as an independent asset just because it has a different timestamp.
2. Verify original measurement units, sample rate, number of samples per record and time spacing **from archive documentation**. Published literature often describes ~20 kHz recordings and ~1-second windows; this review has **not confirmed** whether each record has exactly 20,480 points or how sampling-rate conventions are specified by the donors. These parameters must never be silently assumed from MotorPulse AI's different 1024 Hz synthetic schema.
3. Inspect any end-of-run failure descriptions to distinguish *reported bearing-end failure* from **unknown per-window fault onset**. Do not label all preceding records as healthy, or invent exact onset times and remaining useful life.
4. Split entire **runs / bearings / linked channels** between training and evaluation to avoid adjacent-window leakage; group related measurements from a common test rig together. Do not naively random-split per-window samples or normalize using statistics fitted on the held-out test run.
5. Track record counts, missing channels, timestamp parse errors, duplicates and suspicious nested-archive paths. Map each accepted sample to its complete upstream source key.
6. Document collection date vs file-system packaging dates, archive version/URL, and archive SHA-256 **before** reporting a reproducible benchmark.
7. Make any downstream feature-export license and citation policy explicit. Never mix IMS-derived measurements with **synthetic** training labels without a declared data-source column.

**No real-data ingestion, waveform upload or ML evaluation was implemented in MP-027.** The next code milestone is MP-009 (read verified **user-provided local** files without bundling the dataset), followed by MP-028 (validation/preprocessing). If rights remain unclear, it is appropriate to keep redistribution blocked while allowing independent local research under the terms applicable to the user.

## How to validate this documentation offline

```bash
python -m unittest discover -s tests -p 'test_provenance.py' -v
python -m unittest discover -s tests -v
```

The documentation tests check the source card, exact upstream URLs, uncertainty and no-data-acquired sentinels, cross-references, and Git ignore safeguards **without opening a network connection or downloading source data**. Passing the tests does **not** mean the dataset is licensed or legally cleared for republication.
