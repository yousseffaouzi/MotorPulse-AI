"""Strict, bounded loading of local synthetic-motor scenario configurations.

The JSON file contains the same {"assets": [...]} object accepted by PUT
/api/config. No YAML, remote URLs, code execution or implicit filesystem writes.
"""

from __future__ import annotations

import json
from pathlib import Path

from .scenarios import AssetScenario, parse_configuration

MAX_CONFIG_BYTES = 64 * 1024


def _reject_nonfinite(value: str) -> None:
    raise ValueError(f"non-standard JSON number {value} is not allowed")


def _reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for name, value in pairs:
        if name in result:
            raise ValueError(f"duplicate JSON key: {name!r}")
        result[name] = value
    return result


def _path_contains_symlink(path: Path) -> bool:
    candidate = path if path.is_absolute() else Path.cwd() / path
    current = Path(candidate.anchor)
    for part in candidate.parts[1:]:
        if part in ("", "."):
            continue
        if part == "..":
            current = current.parent
            continue
        current = current / part
        if current.is_symlink():
            return True
    return False


def load_config_file(path: str | Path) -> tuple[AssetScenario, ...]:
    """Load one validated UTF-8 JSON config of at most MAX_CONFIG_BYTES.

    Relative paths resolve against the current working directory. Symlinked
    files or parent path components are rejected before reading. The file is
    read with an explicit size limit before parsing. All scenario validation
    remains centralized in parse_configuration.
    """
    filepath = Path(path)
    try:
        if _path_contains_symlink(filepath):
            raise ValueError(f"configuration path may not use symlinks: {filepath}")
        if not filepath.is_file():
            raise ValueError(
                "configuration file does not exist or is not a regular file: "
                f"{filepath}"
            )
        with filepath.open("rb") as handle:
            payload = handle.read(MAX_CONFIG_BYTES + 1)
    except OSError as exc:
        raise ValueError(
            f"cannot read configuration file {filepath}: {exc.strerror or exc}"
        ) from exc

    if len(payload) > MAX_CONFIG_BYTES:
        raise ValueError(
            f"configuration file exceeds {MAX_CONFIG_BYTES} bytes: {filepath}"
        )
    if not payload:
        raise ValueError(f"configuration file is empty: {filepath}")
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError(f"configuration file must be UTF-8: {filepath}") from exc
    try:
        raw = json.loads(
            text,
            parse_constant=_reject_nonfinite,
            object_pairs_hook=_reject_duplicate_keys,
        )
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"invalid JSON in {filepath} (line {exc.lineno}, column {exc.colno}): "
            f"{exc.msg}"
        ) from exc

    try:
        return parse_configuration(raw)
    except (ValueError, TypeError) as exc:
        raise ValueError(f"invalid configuration in {filepath}: {exc}") from exc
