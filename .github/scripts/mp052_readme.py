from pathlib import Path

path = Path("README.md")
text = path.read_text(encoding="utf-8")
old = "See [docs/INSTALL.md](docs/INSTALL.md) for wheel builds, offline options, cross-directory verification, and troubleshooting.\n"
new = old + "\nAn **optional container** quick start is documented in [docs/CONTAINER.md](docs/CONTAINER.md). The **native Python** workflow above remains the primary supported path, and **No Docker** installation is required to run or develop MotorPulse AI.\n"
if text.count(old) != 1:
    raise SystemExit("README install-guide anchor mismatch")
path.write_text(text.replace(old, new), encoding="utf-8")
