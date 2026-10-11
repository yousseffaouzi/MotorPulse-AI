# Install MotorPulse AI locally — MP-022

MotorPulse AI is a **software-only synthetic motor simulation**, not industrial safety equipment. Python **3.11+** is required. The application needs **no external runtime packages**, sensors, cloud account, database, or Docker. Python packaging tools are needed **at build/install time**, as specified in `pyproject.toml`.

## Fresh-clone setup

```bash
git clone https://github.com/yousseffaouzi/MotorPulse-AI.git
cd MotorPulse-AI
python -m venv .venv
```

Activate the environment:

- macOS/Linux: `source .venv/bin/activate`
- Windows PowerShell: `.venv\Scripts\Activate.ps1`

Install in **editable development** mode:

```bash
python -m pip install -e .
python -m unittest discover -s tests -v
python -m motorpulse --help
motorpulse-ai --help
```

Run `python -m motorpulse` or `motorpulse-ai`, then open `http://127.0.0.1:8765`. Use Ctrl+C to stop. The HTTP server remains bound to **127.0.0.1**, not `0.0.0.0`. **Do not port-forward the app or connect real equipment.**

Without installing, you may still run `python -m motorpulse` from the repository root; this is the supported zero-install development path.

## Wheel smoke test (independent of the checkout directory)

From the repository root, with an environment where `pip`, `setuptools`, and `wheel` are available:

```bash
python -m pip wheel --no-deps . --wheel-dir dist/
python -m pip install --no-deps --force-reinstall dist/motorpulse_ai-0.1.0.dev0-py3-none-any.whl
cd ..
python -m motorpulse --help
motorpulse-ai --help
python -c "from importlib.resources import files; print(files('motorpulse').joinpath('web', 'index.html').is_file())"
```

A motor scenario file can be supplied from any working directory: `motorpulse-ai --config /absolute/path/to/config.json --paused`. See [CONFIG_FILE.md](CONFIG_FILE.md) for file format and error conditions.

Both command-line help commands should succeed; the final command should print `True`. Starting the server from outside the repo should serve the bundled dashboard at `/`, while `GET /api/health` returns simulation status.

The installed `motorpulse-export` CLI can produce offline CSV/JSONL data with `motorpulse-export --out-dir NEW_DIRECTORY --ticks 10`; see [DATASET.md](DATASET.md). The installed `motorpulse-ims` CLI inspects **user-provided local** timestamp-named bearing ASCII records (never downloads); see [IMS_INGESTION.md](IMS_INGESTION.md).

The `pip wheel` command may fetch the **build-time** backend if your environment does not have a suitable version. In restricted/offline environments with build tools preinstalled, use `python -m pip wheel --no-deps --no-build-isolation . --wheel-dir dist/` instead.

## Packaging design

- `pyproject.toml` defines `motorpulse-ai` distribution version `0.1.0.dev0`, setuptools as build backend, the supported Python floor, and a `motorpulse-ai` console script.
- Python modules remain in the existing `motorpulse/` **flat layout**. No risky module reorganization was necessary.
- The single source of truth for the static dashboard is now `motorpulse/web/index.html`, included in **both** wheels and source archives by `[tool.setuptools.package-data]` and `MANIFEST.in`. The server resolves this file relative to its installed package location rather than the current working directory.
- Source and installed entry points behave consistently: `python -m motorpulse` is retained, with `motorpulse-ai` added as a convenience.
- No PyPI publication, executable installer, release tag, or deployment is implied by this prerelease package metadata; those are separate milestones.

## Regression checks and troubleshooting

```bash
python -m unittest discover -s tests -v
python -m unittest discover -s tests -p 'test_packaging.py' -v
```

The packaging checks read build metadata, verify that the dashboard exists as a Python package resource, retrieve the dashboard through a real loopback HTTP server, and confirm CLI help works from another working directory. A complete **installed wheel** smoke check requires the separate build/install commands above.

If installation fails due to unavailable build dependencies, provision setuptools and wheel in the virtual environment first (or use the zero-install source path). If port 8765 is occupied, stop the other local process using it. Tests themselves use ephemeral local ports.

See [Python Packaging User Guide](https://packaging.python.org/en/latest/tutorials/packaging-projects/), [setuptools package data](https://setuptools.pypa.io/en/stable/userguide/datafiles.html), and [wheel/project metadata](https://packaging.python.org/en/latest/specifications/pyproject-toml/) for the conventions used.
