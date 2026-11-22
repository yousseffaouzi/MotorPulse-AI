"""MP-073: descriptive local reporting of a verified physical experiment."""

from __future__ import annotations

import argparse
from pathlib import Path
from statistics import median
from typing import Any, Sequence

from .physical_dataset import PUBLICATION_STATUS
from .physical_final_test_approval_request import write_final_test_approval_request
from .physical_final_test_scorer import validate_physical_final_test_result
from .physical_training_approval_request import _require, _sha
from .physical_training_readiness import _read_json

REPORT_VERSION = "1.0.0"
LIMITATIONS = (
    "Review flags are not verified faults or false alarms.",
    "No label-dependent accuracy, precision, recall, or failure probability.",
    "Window counts do not establish independent sample size or field performance.",
    "No test-driven tuning, diagnosis, RUL, publication, or deployment.",
    "Local integrity replay is not authenticated consent or a sealed holdout.",
)


def _rate(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def _summary(
    result: dict[str, Any], entries: Sequence[dict[str, Any]]
) -> dict[str, Any]:
    rows = result["rows"]
    scores = [row["score"] for row in rows if row["status"] == "scored"]
    flagged = sum(row["review_flag"] is True for row in rows)
    return {
        "assets": len({entry["asset_id"] for entry in entries}),
        "sessions": len(entries),
        "windows_total": len(rows),
        "windows_scored": len(scores),
        "windows_abstained": len(rows) - len(scores),
        "review_flags": flagged,
        "scored_fraction_of_total": _rate(len(scores), len(rows)),
        "abstained_fraction_of_total": _rate(len(rows) - len(scores), len(rows)),
        "review_flag_fraction_of_scored": _rate(flagged, len(scores)),
        "score_min": min(scores) if scores else None,
        "score_median": median(scores) if scores else None,
        "score_max": max(scores) if scores else None,
    }


def create_experiment_report(
    result: dict[str, Any],
    record: dict[str, Any],
    request: dict[str, Any],
    decision: dict[str, Any],
    validation_result: dict[str, Any],
    evaluation_approval_record: dict[str, Any],
    evaluation_request: dict[str, Any],
    evaluation_decision: dict[str, Any],
    model: dict[str, Any],
    training_approval_record: dict[str, Any],
    training_request: dict[str, Any],
    training_decision: dict[str, Any],
    preregistration: dict[str, Any],
    bundle: dict[str, Any],
    readiness: dict[str, Any],
    split_plan: dict[str, Any],
    run_cards: Sequence[dict[str, Any]],
    review_manifests: Sequence[dict[str, Any]],
    feature_paths: Sequence[str | Path],
    protocol: dict[str, Any],
) -> dict[str, Any]:
    """Replay and verify the complete chain before summarizing existing results."""
    validate_physical_final_test_result(
        result,
        record,
        request,
        decision,
        validation_result,
        evaluation_approval_record,
        evaluation_request,
        evaluation_decision,
        model,
        training_approval_record,
        training_request,
        training_decision,
        preregistration,
        bundle,
        readiness,
        split_plan,
        run_cards,
        review_manifests,
        feature_paths,
        protocol,
    )
    # MP-071 explicitly binds the exact validation-result hash.
    _require(
        result["validation_result_sha256"] == _sha(validation_result),
        "validation result binding changed",
    )
    train = bundle["partitions"]["train"]
    core = {
        "physical_experiment_report_version": REPORT_VERSION,
        "report_kind": "descriptive_review_only",
        "model_id": model["model_id"],
        "model_sha256": _sha(model),
        "model_family": model["model_family"],
        "source_bundle_id": bundle["bundle_id"],
        "source_bundle_sha256": _sha(bundle),
        "split_plan_sha256": split_plan["plan_sha256"],
        "validation_result_id": validation_result["result_id"],
        "validation_result_sha256": _sha(validation_result),
        "final_test_result_id": result["result_id"],
        "final_test_result_sha256": _sha(result),
        "final_test_approval_record_sha256": _sha(record),
        "threshold": result["threshold"],
        "threshold_comparison": "score > threshold",
        "threshold_source": result["threshold_source"],
        "train_coverage": {
            "assets": len({entry["asset_id"] for entry in train}),
            "sessions": len(train),
            "windows_total": sum(entry["records"] for entry in train),
            "windows_extracted": sum(entry["extracted_records"] for entry in train),
            "windows_abstained": sum(entry["abstained_records"] for entry in train),
        },
        "validation": _summary(validation_result, bundle["partitions"]["validation"]),
        "test": _summary(result, bundle["partitions"]["test"]),
        "label_dependent_metrics": None,
        "field_performance_validated": False,
        "score_is_failure_probability": False,
        "publication_status": PUBLICATION_STATUS,
        "redistribution_cleared": False,
        "deployment_authorized": False,
        "limitations": list(LIMITATIONS),
    }
    return {"report_id": "physical-experiment-report:" + _sha(core)[:24], **core}


def validate_experiment_report(
    report: Any,
    result: dict[str, Any],
    record: dict[str, Any],
    request: dict[str, Any],
    decision: dict[str, Any],
    validation_result: dict[str, Any],
    evaluation_approval_record: dict[str, Any],
    evaluation_request: dict[str, Any],
    evaluation_decision: dict[str, Any],
    model: dict[str, Any],
    training_approval_record: dict[str, Any],
    training_request: dict[str, Any],
    training_decision: dict[str, Any],
    preregistration: dict[str, Any],
    bundle: dict[str, Any],
    readiness: dict[str, Any],
    split_plan: dict[str, Any],
    run_cards: Sequence[dict[str, Any]],
    review_manifests: Sequence[dict[str, Any]],
    feature_paths: Sequence[str | Path],
    protocol: dict[str, Any],
) -> None:
    expected = create_experiment_report(
        result,
        record,
        request,
        decision,
        validation_result,
        evaluation_approval_record,
        evaluation_request,
        evaluation_decision,
        model,
        training_approval_record,
        training_request,
        training_decision,
        preregistration,
        bundle,
        readiness,
        split_plan,
        run_cards,
        review_manifests,
        feature_paths,
        protocol,
    )
    _require(
        type(report) is dict
        and report == expected
        and _sha(report) == _sha(expected),
        "physical experiment report does not match exact verified results",
    )


def render_markdown(report: dict[str, Any]) -> str:
    """Render a report returned by create_experiment_report; no data access."""
    lines = [
        "# Physical experiment report — local review only",
        "",
        f"Report: `{report['report_id']}`",
        f"Model: `{report['model_id']}`",
        f"Bundle: `{report['source_bundle_id']}`",
        f"Frozen threshold: {report['threshold']:.8g} (score > threshold)",
        "",
        "| Quantity | Validation | Final test |",
        "|---|---:|---:|",
    ]
    for key, label in (
        ("assets", "Assets"),
        ("sessions", "Sessions"),
        ("windows_total", "Total windows"),
        ("windows_scored", "Scored windows"),
        ("windows_abstained", "Abstained windows"),
        ("review_flags", "Review flags"),
        ("review_flag_fraction_of_scored", "Flagged / scored"),
        ("abstained_fraction_of_total", "Abstained / total"),
        ("score_min", "Minimum score"),
        ("score_median", "Median score"),
        ("score_max", "Maximum score"),
    ):
        cells = []
        for partition in ("validation", "test"):
            value = report[partition][key]
            cells.append("Undefined" if value is None else format(value, ".8g"))
        lines.append(f"| {label} | {cells[0]} | {cells[1]} |")
    lines.extend(["", "## Training coverage", ""])
    for key, value in report["train_coverage"].items():
        lines.append(f"- {key.replace('_', ' ')}: {value}")
    lines.extend(["", "## Source fingerprints", ""])
    for key in (
        "model_sha256",
        "source_bundle_sha256",
        "split_plan_sha256",
        "validation_result_sha256",
        "final_test_result_sha256",
        "final_test_approval_record_sha256",
    ):
        lines.append(f"- {key}: `{report[key]}`")
    lines.extend(["", "## Limitations", ""])
    lines.extend(f"- {item}" for item in report["limitations"])
    lines.extend(["", f"Publication status: `{report['publication_status']}`.", ""])
    return "\n".join(lines)


def write_experiment_report(
    path: str | Path, report: dict[str, Any], *, output_format: str = "json"
) -> None:
    _require(output_format in ("json", "markdown"), "unsupported report format")
    if output_format == "json":
        write_final_test_approval_request(path, report)
        return
    content = render_markdown(report)
    destination = Path(path)
    _require(
        not destination.exists() and not destination.is_symlink(),
        "physical experiment report already exists; refusing to overwrite",
    )
    _require(
        destination.parent.is_dir() and not destination.parent.is_symlink(),
        "report output parent must exist and not be a symlink",
    )
    with destination.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(content)


def report_files(
    final_test_result_path: str | Path,
    final_test_approval_record_path: str | Path,
    final_test_request_path: str | Path,
    final_test_decision_path: str | Path,
    validation_result_path: str | Path,
    evaluation_approval_record_path: str | Path,
    evaluation_request_path: str | Path,
    evaluation_decision_path: str | Path,
    model_path: str | Path,
    training_approval_record_path: str | Path,
    training_request_path: str | Path,
    training_decision_path: str | Path,
    preregistration_path: str | Path,
    bundle_path: str | Path,
    readiness_path: str | Path,
    split_path: str | Path,
    card_paths: Sequence[str | Path],
    review_paths: Sequence[str | Path],
    feature_paths: Sequence[str | Path],
    protocol_path: str | Path,
) -> dict[str, Any]:
    result = _read_json(final_test_result_path, "final-test result")
    record = _read_json(final_test_approval_record_path, "final-test approval record")
    request = _read_json(final_test_request_path, "final-test request")
    decision = _read_json(final_test_decision_path, "final-test decision")
    validation_result = _read_json(validation_result_path, "validation result")
    evaluation_approval_record = _read_json(
        evaluation_approval_record_path, "evaluation approval record"
    )
    evaluation_request = _read_json(evaluation_request_path, "evaluation request")
    evaluation_decision = _read_json(evaluation_decision_path, "evaluation decision")
    model = _read_json(model_path, "physical model")
    training_approval_record = _read_json(
        training_approval_record_path, "training approval"
    )
    training_request = _read_json(training_request_path, "training request")
    training_decision = _read_json(training_decision_path, "training decision")
    preregistration = _read_json(preregistration_path, "preregistration")
    bundle = _read_json(bundle_path, "physical bundle")
    readiness = _read_json(readiness_path, "physical readiness")
    split_plan = _read_json(split_path, "physical split")
    run_cards = [_read_json(path, "physical run card") for path in card_paths]
    review_manifests = [
        _read_json(path, "physical evidence review") for path in review_paths
    ]
    protocol = _read_json(protocol_path, "physical protocol")
    return create_experiment_report(
        result,
        record,
        request,
        decision,
        validation_result,
        evaluation_approval_record,
        evaluation_request,
        evaluation_decision,
        model,
        training_approval_record,
        training_request,
        training_decision,
        preregistration,
        bundle,
        readiness,
        split_plan,
        run_cards,
        review_manifests,
        feature_paths,
        protocol,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Summarize the exact completed physical experiment for local review"
        )
    )
    parser.add_argument("--final-test-result", required=True)
    parser.add_argument("--final-test-approval-record", required=True)
    parser.add_argument("--final-test-request", required=True)
    parser.add_argument("--final-test-decision", required=True)
    parser.add_argument("--validation-result", required=True)
    parser.add_argument("--evaluation-approval-record", required=True)
    parser.add_argument("--evaluation-request", required=True)
    parser.add_argument("--evaluation-decision", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--training-approval-record", required=True)
    parser.add_argument("--training-request", required=True)
    parser.add_argument("--training-decision", required=True)
    parser.add_argument("--preregistration", required=True)
    parser.add_argument("--bundle", required=True)
    parser.add_argument("--readiness", required=True)
    parser.add_argument("--split", required=True)
    parser.add_argument("--card", action="append", required=True, dest="cards")
    parser.add_argument("--review", action="append", required=True, dest="reviews")
    parser.add_argument("--feature", action="append", required=True, dest="features")
    parser.add_argument("--protocol", required=True)
    parser.add_argument("--format", choices=("json", "markdown"), default="json")
    parser.add_argument("--out", required=True, help="write-once report")
    args = parser.parse_args(argv)
    report = report_files(
        args.final_test_result,
        args.final_test_approval_record,
        args.final_test_request,
        args.final_test_decision,
        args.validation_result,
        args.evaluation_approval_record,
        args.evaluation_request,
        args.evaluation_decision,
        args.model,
        args.training_approval_record,
        args.training_request,
        args.training_decision,
        args.preregistration,
        args.bundle,
        args.readiness,
        args.split,
        args.cards,
        args.reviews,
        args.features,
        args.protocol,
    )
    write_experiment_report(args.out, report, output_format=args.format)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
