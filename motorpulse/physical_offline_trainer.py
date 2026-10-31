"""Fail-closed offline physical model fitting behind MP-065 approval (MP-066).

MP-066 fits only the preregistered train-partition standardized-distance baseline.
It revalidates the complete physical approval/source chain before fitting and does
not score held-out data, diagnose machinery, estimate failure probability or RUL,
publish data, deploy models, or connect to hardware/network/control interfaces.
"""

from __future__ import annotations

import argparse
import json
from math import isfinite, sqrt
from pathlib import Path
from statistics import fmean
from typing import Any, Sequence

from .feature_pipeline import FEATURES, UNITS as FEATURE_UNITS
from .physical_dataset import PUBLICATION_STATUS, _read_features
from .physical_experiment_preregistration import MODEL_FAMILY
from .physical_training_approval_record import validate_approval_record
from .physical_training_approval_request import _require, _sha
from .physical_training_readiness import _read_json

PHYSICAL_MODEL_VERSION = "1.0.0"
TRAINING_METHOD = "train_only_standardized_distance"
SCORE_DIRECTION = "higher_is_more_unusual"
SCALE_FLOOR_ABSOLUTE = 1e-9
SCALE_FLOOR_RELATIVE = 1e-9
_REQUIRED_OPERATIONS = [
    "fit_preprocessing_on_train",
    "fit_model_on_train",
    "derive_threshold_on_train",
]
_MODEL_KEYS = frozenset(
    {
        "physical_model_version",
        "model_id",
        "model_family",
        "training_method",
        "score_direction",
        "score_is_failure_probability",
        "remaining_useful_life",
        "approval_record_id",
        "approval_record_sha256",
        "request_id",
        "preregistration_id",
        "source_bundle_id",
        "split_plan_sha256",
        "target_mode",
        "feature_contract",
        "preprocessing",
        "calibration",
        "training",
        "heldout_partitions",
        "publication_status",
        "redistribution_cleared",
        "training_authorized",
        "training_completed",
        "model_scoring_authorized",
        "diagnosis_authorized",
        "failure_probability_authorized",
        "rul_authorized",
        "deployment_authorized",
    }
)


def _percentile(values: list[float], quantile: float) -> float:
    _require(bool(values), "physical training score distribution must not be empty")
    ordered = sorted(values)
    index = (len(ordered) - 1) * quantile
    low = int(index)
    high = min(low + 1, len(ordered) - 1)
    return ordered[low] + (ordered[high] - ordered[low]) * (index - low)


def _vector(row: dict[str, Any]) -> tuple[float, ...]:
    _require(
        row["feature_status"] == "extracted",
        "only extracted physical feature rows can be used for fitting",
    )
    _require(
        row["sample_rate_hz"] == 1024 and row["sample_count"] == 1024,
        "physical training requires the preregistered 1024 Hz / 1024 sample contract",
    )
    quality = row["quality"]
    _require(
        type(quality) is dict
        and quality.get("vibration") == "good"
        and quality.get("temperature") == "good"
        and quality.get("rpm") == "good",
        "physical training requires good vibration, temperature, and rpm quality",
    )
    values: list[float] = []
    for name in FEATURES:
        value = row.get(name)
        _require(
            type(value) in (int, float) and isfinite(value) and value >= 0,
            f"physical training feature {name} must be finite and nonnegative",
        )
        values.append(float(value))
    return tuple(values)


def _score(
    values: tuple[float, ...], centers: list[float], scales: list[float]
) -> float:
    return sqrt(
        sum(
            ((value - center) / scale) ** 2
            for value, center, scale in zip(values, centers, scales)
        )
        / len(FEATURES)
    )


def _training_rows(
    bundle: dict[str, Any],
    split_plan: dict[str, Any],
    run_cards: Sequence[dict[str, Any]],
    feature_paths: Sequence[str | Path],
) -> tuple[list[tuple[str, dict[str, Any]]], list[str], list[str], int]:
    cards_by_digest = {card["features_sha256"]: card for card in run_cards}
    _require(
        len(cards_by_digest) == len(run_cards),
        "physical training run cards contain duplicate feature content",
    )
    rows_by_card: dict[str, list[dict[str, Any]]] = {}
    digests_by_card: dict[str, str] = {}
    for path in feature_paths:
        rows, digest = _read_features(path)
        _require(
            digest in cards_by_digest,
            "physical training feature file is outside the approved cohort",
        )
        card = cards_by_digest[digest]
        card_id = card["card_id"]
        _require(
            card_id not in rows_by_card,
            "duplicate physical training feature file for run card",
        )
        rows_by_card[card_id] = rows
        digests_by_card[card_id] = digest

    _require(
        set(rows_by_card) == {card["card_id"] for card in run_cards},
        "physical training feature files do not cover the approved cohort",
    )
    train_card_ids = sorted(split_plan["partitions"]["train"]["card_ids"])
    expected_train_ids = sorted(
        entry["card_id"] for entry in bundle["partitions"]["train"]
    )
    _require(
        train_card_ids == expected_train_ids,
        "physical training train partition differs from approved bundle",
    )

    training_rows: list[tuple[str, dict[str, Any]]] = []
    abstained = 0
    seen: set[tuple[str, int, str]] = set()
    for card_id in train_card_ids:
        _require(card_id in rows_by_card, "approved train feature file is missing")
        for row in rows_by_card[card_id]:
            identity = (card_id, row["sequence"], row["input_frame_sha256"])
            _require(identity not in seen, "duplicate physical training row identity")
            seen.add(identity)
            if row["feature_status"] == "abstained":
                abstained += 1
                continue
            _vector(row)
            training_rows.append((card_id, row))

    expected_extracted = sum(
        entry["extracted_records"] for entry in bundle["partitions"]["train"]
    )
    expected_abstained = sum(
        entry["abstained_records"] for entry in bundle["partitions"]["train"]
    )
    _require(
        len(training_rows) == expected_extracted and abstained == expected_abstained,
        "physical training row counts differ from approved train partition",
    )
    return (
        training_rows,
        train_card_ids,
        sorted(digests_by_card[card_id] for card_id in train_card_ids),
        abstained,
    )


def _fit_parameters(
    rows: Sequence[tuple[str, dict[str, Any]]], quantile: float
) -> tuple[list[float], list[float], list[float], list[float], float]:
    _require(bool(rows), "physical training requires at least one extracted train row")
    vectors = [_vector(row) for _, row in rows]
    columns = list(zip(*vectors))
    centers = [fmean(column) for column in columns]
    population_std = [
        sqrt(fmean((value - center) ** 2 for value in column))
        for column, center in zip(columns, centers)
    ]
    effective_scales = [
        max(
            deviation,
            SCALE_FLOOR_ABSOLUTE,
            abs(center) * SCALE_FLOOR_RELATIVE,
        )
        for center, deviation in zip(centers, population_std)
    ]
    scores = [_score(vector, centers, effective_scales) for vector in vectors]
    threshold = _percentile(scores, quantile)
    _require(
        all(
            isfinite(value)
            for value in centers
            + population_std
            + effective_scales
            + scores
            + [threshold]
        ),
        "physical training produced non-finite statistics",
    )
    return centers, population_std, effective_scales, scores, threshold


def _build_model(
    approval_record: dict[str, Any],
    request: dict[str, Any],
    preregistration: dict[str, Any],
    bundle: dict[str, Any],
    split_plan: dict[str, Any],
    run_cards: Sequence[dict[str, Any]],
    feature_paths: Sequence[str | Path],
    protocol: dict[str, Any],
) -> dict[str, Any]:
    _require(
        approval_record["training_authorized"] is True,
        "MP-066 requires explicit MP-065 training authorization",
    )
    _require(
        approval_record["approved_operations"] == _REQUIRED_OPERATIONS,
        "MP-066 approval does not match exact preregistered training operations",
    )
    design = preregistration["experiment_design"]
    _require(
        design["model_family"] == MODEL_FAMILY
        and request["model_family"] == MODEL_FAMILY
        and protocol["model_family"] == MODEL_FAMILY,
        "MP-066 model family differs from preregistration",
    )
    _require(
        design["input_features"] == list(FEATURES),
        "MP-066 feature allowlist differs from preregistration",
    )
    _require(
        design["fit_partition"] == "train"
        and design["preprocessing_fit_partition"] == "train"
        and design["threshold_partition"] == "train",
        "MP-066 may fit preprocessing, model, and threshold only on train",
    )
    _require(
        design["validation_role"] == "review_only_no_fit"
        and design["test_role"] == "final_only_no_fit",
        "MP-066 held-out partition roles changed",
    )
    quantile = float(design["threshold_quantile"])
    _require(
        quantile == float(protocol["threshold_quantile"]),
        "MP-066 threshold quantile differs from protocol",
    )

    rows, train_card_ids, train_feature_hashes, abstained = _training_rows(
        bundle, split_plan, run_cards, feature_paths
    )
    _require(
        len(rows) >= design["minimum_extracted_records"]["train"],
        "physical training has fewer extracted train rows than preregistered minimum",
    )
    centers, deviations, scales, scores, threshold = _fit_parameters(rows, quantile)

    core = {
        "physical_model_version": PHYSICAL_MODEL_VERSION,
        "model_family": MODEL_FAMILY,
        "training_method": TRAINING_METHOD,
        "score_direction": SCORE_DIRECTION,
        "score_is_failure_probability": False,
        "remaining_useful_life": None,
        "approval_record_id": approval_record["approval_record_id"],
        "approval_record_sha256": _sha(approval_record),
        "request_id": request["request_id"],
        "preregistration_id": preregistration["preregistration_id"],
        "source_bundle_id": bundle["bundle_id"],
        "split_plan_sha256": split_plan["plan_sha256"],
        "target_mode": preregistration["target_mode"],
        "feature_contract": {
            "names": list(FEATURES),
            "units": list(FEATURE_UNITS),
            "source": "local user-supplied physical feature rows",
            "sample_rate_hz": 1024,
            "sample_count": 1024,
            "required_quality": "good",
            "abstained_rows": "excluded_from_fit",
            "labels_used": False,
        },
        "preprocessing": {
            "fit_partition": "train",
            "center": centers,
            "population_std": deviations,
            "effective_scales": scales,
            "scale_floor_absolute": SCALE_FLOOR_ABSOLUTE,
            "scale_floor_relative_to_abs_center": SCALE_FLOOR_RELATIVE,
        },
        "calibration": {
            "partition": "train",
            "quantile": quantile,
            "threshold": threshold,
            "comparison": "score > threshold",
            "training_score_max": max(scores),
            "method_note": (
                "in-sample train empirical quantile; not a calibrated failure "
                "probability or guaranteed false-alarm rate"
            ),
        },
        "training": {
            "partition": "train",
            "train_card_ids": train_card_ids,
            "train_feature_sha256": train_feature_hashes,
            "extracted_rows_consumed": len(rows),
            "abstained_rows_excluded": abstained,
            "heldout_rows_consumed": 0,
            "seed": design["seed"],
        },
        "heldout_partitions": {
            "validation": "untouched_no_fit_no_score",
            "test": "untouched_no_fit_no_score",
        },
        "publication_status": PUBLICATION_STATUS,
        "redistribution_cleared": False,
        "training_authorized": True,
        "training_completed": True,
        "model_scoring_authorized": False,
        "diagnosis_authorized": False,
        "failure_probability_authorized": False,
        "rul_authorized": False,
        "deployment_authorized": False,
    }
    return {"model_id": "physical-model:" + _sha(core)[:24], **core}


def train_physical_model(
    approval_record: dict[str, Any],
    request: dict[str, Any],
    decision: dict[str, Any],
    preregistration: dict[str, Any],
    bundle: dict[str, Any],
    readiness: dict[str, Any],
    split_plan: dict[str, Any],
    run_cards: Sequence[dict[str, Any]],
    review_manifests: Sequence[dict[str, Any]],
    feature_paths: Sequence[str | Path],
    protocol: dict[str, Any],
) -> dict[str, Any]:
    """Fit the exact approved train-only physical baseline and nothing else."""
    validate_approval_record(
        approval_record,
        request,
        decision,
        preregistration,
        bundle,
        readiness,
        split_plan,
        run_cards,
        review_manifests,
        feature_paths,
        protocol,
    )
    model = _build_model(
        approval_record,
        request,
        preregistration,
        bundle,
        split_plan,
        run_cards,
        feature_paths,
        protocol,
    )
    validate_physical_model(
        model,
        approval_record,
        request,
        decision,
        preregistration,
        bundle,
        readiness,
        split_plan,
        run_cards,
        review_manifests,
        feature_paths,
        protocol,
    )
    return model


def validate_physical_model(
    model: Any,
    approval_record: dict[str, Any],
    request: dict[str, Any],
    decision: dict[str, Any],
    preregistration: dict[str, Any],
    bundle: dict[str, Any],
    readiness: dict[str, Any],
    split_plan: dict[str, Any],
    run_cards: Sequence[dict[str, Any]],
    review_manifests: Sequence[dict[str, Any]],
    feature_paths: Sequence[str | Path],
    protocol: dict[str, Any],
) -> None:
    """Recompute the exact artifact and reject stale, broadened, or rescoped models."""
    _require(
        type(model) is dict and set(model) == _MODEL_KEYS,
        "physical model artifact fields differ from v1 contract",
    )
    _require(
        model["physical_model_version"] == PHYSICAL_MODEL_VERSION,
        "unsupported physical model artifact version",
    )
    _require(
        model["training_authorized"] is True,
        "physical model lost training authorization",
    )
    _require(
        model["training_completed"] is True,
        "physical model training completion changed",
    )
    for field in (
        "redistribution_cleared",
        "model_scoring_authorized",
        "diagnosis_authorized",
        "failure_probability_authorized",
        "rul_authorized",
        "deployment_authorized",
    ):
        _require(model[field] is False, f"MP-066 must keep {field}=false")
    validate_approval_record(
        approval_record,
        request,
        decision,
        preregistration,
        bundle,
        readiness,
        split_plan,
        run_cards,
        review_manifests,
        feature_paths,
        protocol,
    )
    expected = _build_model(
        approval_record,
        request,
        preregistration,
        bundle,
        split_plan,
        run_cards,
        feature_paths,
        protocol,
    )
    _require(
        model == expected,
        "physical model artifact does not match exact approved sources and protocol",
    )


def train_files(
    approval_record_path: str | Path,
    request_path: str | Path,
    decision_path: str | Path,
    preregistration_path: str | Path,
    bundle_path: str | Path,
    readiness_path: str | Path,
    split_path: str | Path,
    card_paths: Sequence[str | Path],
    review_paths: Sequence[str | Path],
    feature_paths: Sequence[str | Path],
    protocol_path: str | Path,
) -> dict[str, Any]:
    approval_record = _read_json(
        approval_record_path, "physical training approval record"
    )
    request = _read_json(request_path, "physical training approval request")
    decision = _read_json(decision_path, "physical training human decision")
    preregistration = _read_json(
        preregistration_path, "physical experiment preregistration"
    )
    bundle = _read_json(bundle_path, "physical experiment bundle")
    readiness = _read_json(readiness_path, "physical readiness assessment")
    split_plan = _read_json(split_path, "physical split plan")
    cards = [_read_json(path, "physical run card") for path in card_paths]
    reviews = [_read_json(path, "physical evidence review") for path in review_paths]
    protocol = _read_json(protocol_path, "physical experiment protocol")
    return train_physical_model(
        approval_record,
        request,
        decision,
        preregistration,
        bundle,
        readiness,
        split_plan,
        cards,
        reviews,
        feature_paths,
        protocol,
    )


def write_physical_model(path: str | Path, model: dict[str, Any]) -> None:
    destination = Path(path)
    _require(
        not destination.exists() and not destination.is_symlink(),
        "physical model output already exists; refusing to overwrite",
    )
    _require(
        destination.parent.is_dir() and not destination.parent.is_symlink(),
        "physical model output parent must exist and not be a symlink",
    )
    with destination.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(
            model,
            stream,
            sort_keys=True,
            ensure_ascii=False,
            allow_nan=False,
            indent=2,
        )
        stream.write("\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Fit the exact approved train-only physical anomaly baseline without "
            "scoring, diagnosis, RUL, publication, or deployment"
        )
    )
    parser.add_argument(
        "--approval-record", required=True, help="MP-065 approval JSON"
    )
    parser.add_argument(
        "--request", required=True, help="MP-064 approval request JSON"
    )
    parser.add_argument(
        "--decision", required=True, help="exact separate human decision JSON"
    )
    parser.add_argument("--preregistration", required=True, help="MP-063 JSON")
    parser.add_argument("--bundle", required=True, help="MP-062 bundle JSON")
    parser.add_argument("--readiness", required=True, help="MP-061 readiness JSON")
    parser.add_argument("--split", required=True, help="MP-059 split plan JSON")
    parser.add_argument("--card", action="append", required=True, dest="cards")
    parser.add_argument("--review", action="append", required=True, dest="reviews")
    parser.add_argument("--feature", action="append", required=True, dest="features")
    parser.add_argument("--protocol", required=True, help="MP-063 protocol JSON")
    parser.add_argument("--out", required=True, help="write-once physical model JSON")
    args = parser.parse_args(argv)
    model = train_files(
        args.approval_record,
        args.request,
        args.decision,
        args.preregistration,
        args.bundle,
        args.readiness,
        args.split,
        args.cards,
        args.reviews,
        args.features,
        args.protocol,
    )
    write_physical_model(args.out, model)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
