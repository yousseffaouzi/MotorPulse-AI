from pathlib import Path

path = Path("README.md")
text = path.read_text(encoding="utf-8")
replacements = [
    (
        "> **Status:** pre-alpha simulated prototype. The current alerts are explainable rule-based baselines, **not** a trained predictive-maintenance AI model. All demo measurements are synthetic; no hardware is required.\n",
        "> **Status:** `v0.1.0` alpha **release candidate, not published**. MotorPulse AI remains a synthetic research lab: fixed rules and the healthy-trained anomaly baseline are not field-validated predictive-maintenance diagnoses, failure probabilities, or RUL estimates. No hardware is required.\n",
    ),
    (
        "Contributor references: [localhost API](docs/API.md), [CLI tutorial](docs/CLI.md), [troubleshooting](docs/TROUBLESHOOTING.md), [architecture](docs/ARCHITECTURE.md), [configuration](docs/CONFIG_FILE.md), [baseline model cards](docs/MODEL_CARDS.md), [local-first security](docs/SECURITY.md), and the [dated synthetic benchmark](docs/BENCHMARK.md).\n",
        "Contributor references: [localhost API](docs/API.md), [CLI tutorial](docs/CLI.md), [troubleshooting](docs/TROUBLESHOOTING.md), [architecture](docs/ARCHITECTURE.md), [configuration](docs/CONFIG_FILE.md), [baseline model cards](docs/MODEL_CARDS.md), [local-first security](docs/SECURITY.md), the [dated synthetic benchmark](docs/BENCHMARK.md), [CHANGELOG.md](CHANGELOG.md), and the [release procedure](docs/RELEASE.md).\n",
    ),
    (
        "MotorPulse AI is packaged as **motorpulse-ai 0.1.0.dev0** (development-only metadata; **not published to PyPI**). All runtime modules are standard-library-only; installing or building the wheel needs Python packaging tools. The single source of truth for the dashboard is now `motorpulse/web/index.html`, so it works after installing from a wheel even when launched from another working directory. See [docs/INSTALL.md](docs/INSTALL.md) for instructions and smoke checks.\n",
        "MotorPulse AI is packaged as **motorpulse-ai 0.1.0** for this alpha release candidate (**not published to PyPI and not yet tagged**). All runtime modules are standard-library-only; installing or building the wheel needs Python packaging tools. The single source of truth for the dashboard is `motorpulse/web/index.html`, so it works after installing from a wheel even when launched from another working directory. See [docs/INSTALL.md](docs/INSTALL.md) for instructions and smoke checks, and [docs/RELEASE.md](docs/RELEASE.md) for the integrated-`main` verification/tag boundary.\n",
    ),
]
for old, new in replacements:
    if text.count(old) != 1:
        raise SystemExit(f"README anchor mismatch: {old[:100]!r}")
    text = text.replace(old, new)
path.write_text(text, encoding="utf-8")
