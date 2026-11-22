"""MP-072: local final-test scoring after exact MP-071 revalidation."""

from __future__ import annotations

import argparse
from contextlib import contextmanager
import hashlib
from math import isfinite
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Iterator, Sequence

from .physical_dataset import (
    MAX_CARDS,
    MAX_FEATURE_BYTES,
    PUBLICATION_STATUS,
    _read_features,
)
from .physical_final_test_approval_record import validate_final_test_approval_record
from .physical_final_test_approval_request import write_final_test_approval_request
from .physical_offline_trainer import _score, _vector
from .physical_training_approval_request import _require, _sha
from .physical_training_readiness import _read_json

RESULT_VERSION = "1.0.0"
PARTITION = "test"
# Bound temporary disk usage in addition to each existing feature-file limit.
MAX_SNAPSHOT_BYTES = 4 * MAX_FEATURE_BYTES


@contextmanager
def _snapshot_features(
    paths: Sequence[str | Path],
) -> Iterator[list[Path]]:
    """Capture the local inputs once; never expose snapshot paths in results."""
    _require(
        type(paths) in (list, tuple) and 3 <= len(paths) <= MAX_CARDS,
        "invalid number of physical feature files",
    )
    total = 0
    with TemporaryDirectory(prefix="motorpulse-final-test-") as directory:
        snapshots = []
        for index, path in enumerate(paths):
            source = Path(path)
            _require(
                source.is_file() and not source.is_symlink(),
                "feature source must be an existing non-symlink file",
            )
            target = Path(directory) / f"{index}.jsonl"
            size = 0
            with source.open("rb") as incoming, target.open("xb") as outgoing:
                while chunk := incoming.read(1024 * 1024):
                    size += len(chunk)
                    total += len(chunk)
                    _require(
                        size <= MAX_FEATURE_BYTES and total <= MAX_SNAPSHOT_BYTES,
                        "physical feature snapshot exceeds size limit",
                    )
                    outgoing.write(chunk)
            _require(size > 0, "physical feature snapshot is empty")
            snapshots.append(target)
        yield snapshots


def _build_result(
    record: dict[str, Any],
    request: dict[str, Any],
    model: dict[str, Any],
    bundle: dict[str, Any],
    split_plan: dict[str, Any],
    feature_paths: Sequence[Path],
) -> dict[str, Any]:
    _require(
        record["test_scoring_authorized"] is True,
        "MP-072 requires exact final-test scoring approval",
    )
    entries = {entry["features_sha256"]: entry for entry in bundle["source_files"]}
    test_ids = set(split_plan["partitions"][PARTITION]["card_ids"])
    _require(
        test_ids == {entry["card_id"] for entry in bundle["partitions"][PARTITION]},
        "test partition differs from approved bundle",
    )
    seen_cards: set[str] = set()
    seen_rows: set[tuple[str, int, str]] = set()
    rows: list[dict[str, Any]] = []
    centers = model["preprocessing"]["center"]
    scales = model["preprocessing"]["effective_scales"]
    threshold = float(model["calibration"]["threshold"])
    for path in feature_paths:
        feature_rows, digest = _read_features(path)
        _require(digest in entries, "feature snapshot is outside approved cohort")
        entry = entries[digest]
        card_id = entry["card_id"]
        _require(card_id not in seen_cards, "duplicate feature snapshot")
        seen_cards.add(card_id)
        # Verify raw bytes as well as parsed feature identity.
        with path.open("rb") as stream:
            raw_digest = hashlib.file_digest(stream, "sha256").hexdigest()
        _require(
            raw_digest == entry["feature_file_sha256"],
            "feature snapshot bytes differ from approved bundle",
        )
        if card_id not in test_ids:
            continue
        for row in feature_rows:
            identity = (card_id, row["sequence"], row["input_frame_sha256"])
            _require(identity not in seen_rows, "duplicate final-test row identity")
            seen_rows.add(identity)
            abstained = row["feature_status"] == "abstained"
            score = None if abstained else _score(_vector(row), centers, scales)
            _require(
                score is None or isfinite(score),
                "non-finite final-test score",
            )
            rows.append(
                {
                    "card_id": card_id,
                    "sequence": row["sequence"],
                    "input_frame_sha256": row["input_frame_sha256"],
                    "status": "abstained" if abstained else "scored",
                    "score": score,
                    "review_flag": None if abstained else score > threshold,
                }
            )
    _require(
        seen_cards == {entry["card_id"] for entry in entries.values()},
        "feature snapshots do not cover the approved cohort",
    )
    rows.sort(
        key=lambda row: (row["card_id"], row["sequence"], row["input_frame_sha256"])
    )
    scored = sum(row["status"] == "scored" for row in rows)
    abstained = len(rows) - scored
    test_entries = bundle["partitions"][PARTITION]
    _require(
        scored == sum(entry["extracted_records"] for entry in test_entries)
        and abstained == sum(entry["abstained_records"] for entry in test_entries),
        "final-test row counts differ from bundle",
    )
    core = {
        "physical_final_test_result_version": RESULT_VERSION,
        "result_kind": "review_only_anomaly_scores",
        "partition": PARTITION,
        "final_test_approval_record_id": record["final_test_approval_record_id"],
        "final_test_approval_record_sha256": _sha(record),
        "final_test_request_id": request["request_id"],
        "final_test_request_sha256": _sha(request),
        "validation_result_id": request["validation_result_id"],
        "validation_result_sha256": request["validation_result_sha256"],
        "model_id": model["model_id"],
        "model_sha256": _sha(model),
        "model_family": model["model_family"],
        "source_bundle_id": bundle["bundle_id"],
        "split_plan_sha256": split_plan["plan_sha256"],
        "score_direction": model["score_direction"],
        "score_is_failure_probability": False,
        "threshold": threshold,
        "threshold_source": "frozen_mp066_train_empirical_quantile",
        "threshold_comparison": "score > threshold",
        "rows": rows,
        "counts": {
            "test_rows_total": len(rows),
            "test_rows_scored": scored,
            "test_rows_abstained": abstained,
            "review_flags": sum(row["review_flag"] is True for row in rows),
        },
        "train_rows_consumed": 0,
        "validation_rows_consumed": 0,
        "test_rows_consumed": scored,
        "test_scoring_authorized": True,
        "test_scoring_completed": True,
        "model_refit_performed": False,
        "preprocessing_refit_performed": False,
        "threshold_recalibration_performed": False,
        "diagnosis_performed": False,
        "failure_probability_estimated": False,
        "rul_estimated": False,
        "publication_status": PUBLICATION_STATUS,
        "redistribution_cleared": False,
        "deployment_authorized": False,
    }
    return {"result_id": "physical-final-test-result:" + _sha(core)[:24], **core}


def score_physical_final_test(
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
    """Score test rows only after replay of the exact approved chain."""
    with _snapshot_features(feature_paths) as snapshots:
        validate_final_test_approval_record(
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
            snapshots,
            protocol,
        )
        return _build_result(record, request, model, bundle, split_plan, snapshots)


def validate_physical_final_test_result(
    result: Any,
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
    """Reproduce the result; no changed scope or JSON types are accepted."""
    _require(type(result) is dict, "final-test result must be an object")
    expected = score_physical_final_test(
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
        result == expected and _sha(result) == _sha(expected),
        "final-test result does not match exact approved model and sources",
    )


def score_files(
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
    return score_physical_final_test(
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


def write_physical_final_test_result(path: str | Path, result: dict[str, Any]) -> None:
    write_final_test_approval_request(path, result)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Score only the explicitly approved final-test partition with "
            "the frozen model; no new fit or threshold selection"
        )
    )
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
    parser.add_argument(
        "--out", required=True, help="write-once final-test result JSON"
    )
    args = parser.parse_args(argv)
    result = score_files(
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
    write_physical_final_test_result(args.out, result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
