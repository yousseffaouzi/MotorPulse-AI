"""Execute exactly one approved offline physical workflow stage from a manifest.

This operator convenience layer does not create approvals, chain stages,
connect hardware, access the network, or weaken upstream source validation.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from .physical_experiment_report import report_files, write_experiment_report
from .physical_final_test_scorer import score_files as final_test_files
from .physical_final_test_scorer import write_physical_final_test_result
from .physical_offline_trainer import train_files, write_physical_model
from .physical_training_approval_request import _require
from .physical_training_readiness import _read_json
from .physical_validation_scorer import score_files as validation_files
from .physical_validation_scorer import write_physical_validation_result

WORKFLOW_VERSION = "1.0.0"
_SHARED = (
    "preregistration",
    "bundle",
    "readiness",
    "split",
    "cards",
    "reviews",
    "features",
    "protocol",
)
_TRAIN = (
    "training_approval_record",
    "training_request",
    "training_decision",
    *_SHARED,
)
_VALIDATION = (
    "evaluation_approval_record",
    "evaluation_request",
    "evaluation_decision",
    "model",
    *_TRAIN,
)
_TEST = (
    "final_test_approval_record",
    "final_test_request",
    "final_test_decision",
    "validation_result",
    *_VALIDATION,
)
_STAGE_FIELDS = {
    "train": _TRAIN,
    "validation": _VALIDATION,
    "test": _TEST,
    "report": ("final_test_result", *_TEST),
}
_ALLOWED = frozenset(field for fields in _STAGE_FIELDS.values() for field in fields)
_LIST_FIELDS = frozenset(("cards", "reviews", "features"))


def _local_path(value: Any, parent: Path, label: str) -> Path:
    _require(
        type(value) is str
        and value == value.strip()
        and 1 <= len(value) <= 4096
        and all(ord(char) >= 32 and ord(char) != 127 for char in value)
        and "://" not in value,
        f"{label} must be an explicit local file path",
    )
    path = Path(value)
    return path if path.is_absolute() else parent / path


def load_workflow_manifest(path: str | Path) -> tuple[dict[str, Any], Path]:
    """Strictly validate the manifest schema without granting any capability."""
    manifest = _read_json(path, "physical workflow manifest")
    _require(
        type(manifest) is dict
        and set(manifest) == {"workflow_manifest_version", "artifacts"},
        "invalid physical workflow manifest fields",
    )
    _require(
        manifest["workflow_manifest_version"] == WORKFLOW_VERSION,
        "unsupported physical workflow manifest version",
    )
    artifacts = manifest["artifacts"]
    _require(
        type(artifacts) is dict
        and bool(artifacts)
        and set(artifacts).issubset(_ALLOWED),
        "physical workflow contains unsupported artifact names",
    )
    base = Path(path).parent
    for name, value in artifacts.items():
        if name in _LIST_FIELDS:
            _require(
                type(value) is list and 3 <= len(value) <= 1000,
                f"{name} must contain between 3 and 1000 local paths",
            )
            paths = [_local_path(item, base, name) for item in value]
            _require(
                len({str(item) for item in paths}) == len(paths),
                f"{name} must not repeat file paths",
            )
        else:
            _local_path(value, base, name)
    return artifacts, base


def stage_paths(
    manifest_path: str | Path, stage: str
) -> tuple[Path | list[Path], ...]:
    """Resolve the single selected stage's explicit inputs."""
    _require(stage in _STAGE_FIELDS, "unsupported physical workflow stage")
    artifacts, parent = load_workflow_manifest(manifest_path)
    required = _STAGE_FIELDS[stage]
    missing = sorted(set(required) - set(artifacts))
    _require(not missing, "missing stage artifacts: " + ", ".join(missing))
    inputs: list[Path | list[Path]] = []
    for name in required:
        value = artifacts[name]
        if name in _LIST_FIELDS:
            inputs.append([_local_path(item, parent, name) for item in value])
        else:
            inputs.append(_local_path(value, parent, name))
    return tuple(inputs)


def run_workflow_stage(
    manifest_path: str | Path,
    stage: str,
    output_path: str | Path,
    *,
    output_format: str = "json",
) -> dict[str, Any]:
    """Execute exactly one stage, delegating all approvals to its original API."""
    _require(stage in _STAGE_FIELDS, "unsupported physical workflow stage")
    _require(
        output_format == "json"
        or (stage == "report" and output_format == "markdown"),
        "Markdown output is supported only for report stage",
    )
    destination = Path(output_path)
    _require(
        not destination.exists() and not destination.is_symlink(),
        "physical workflow output already exists; refusing to overwrite",
    )
    inputs = stage_paths(manifest_path, stage)
    if stage == "train":
        result = train_files(*inputs)
        write_physical_model(destination, result)
    elif stage == "validation":
        result = validation_files(*inputs)
        write_physical_validation_result(destination, result)
    elif stage == "test":
        result = final_test_files(*inputs)
        write_physical_final_test_result(destination, result)
    else:
        result = report_files(*inputs)
        write_experiment_report(destination, result, output_format=output_format)
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Run one explicitly selected local physical experiment stage using "
            "existing exact source and human-decision validation"
        )
    )
    parser.add_argument("--manifest", required=True, help="local workflow JSON")
    parser.add_argument("--stage", choices=tuple(_STAGE_FIELDS), required=True)
    parser.add_argument("--out", required=True, help="new write-once output")
    parser.add_argument("--format", choices=("json", "markdown"), default="json")
    args = parser.parse_args(argv)
    run_workflow_stage(
        args.manifest, args.stage, args.out, output_format=args.format
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
