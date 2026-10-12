"""MP-035: portable, non-executable, source-verified synthetic model artifacts.

JSON only. A checksum is integrity evidence, not a signature or a license.
Loading for scoring requires the original whole-run split and local manifests.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import json
from math import isfinite
from pathlib import Path
import platform
import re
import sys
from typing import Any, Sequence

from .anomaly import FEATURES, FEATURE_UNITS, MODEL_VERSION, _validated_sources
from .dataset_cards import synthetic_run_card
from .evaluation import _validate_model
from .feature_pipeline import EXCLUDED, VERSION as PIPELINE_VERSION
from .ims import _read_strict_json
from .splits import _hash

ARTIFACT_VERSION = "1.0.0"
KIND = "motorpulse_synthetic_healthy_anomaly"
MAX_ARTIFACT_BYTES = 512 * 1024
_SHA = re.compile(r"^[0-9a-f]{64}$")
TOP_KEYS = frozenset((
    "artifact_version", "kind", "algorithm", "model_version",
    "model", "model_sha256", "processor_sha256", "split_plan_sha256",
    "feature_contract", "training_groups", "source_runs", "runtime",
    "claimed_failure_probability", "remaining_useful_life",
    "limitations", "artifact_sha256",
))
SOURCE_KEYS = frozenset((
    "group_id", "source_id", "source_data_sha256", "model_source_sha256",
    "config_sha256", "dataset_card_id", "partition",
))


def _digest(value: Any, name: str) -> None:
    if type(value) is not str or not _SHA.fullmatch(value):
        raise ValueError(f"invalid {name} SHA-256")


def _source_rows(plan: dict, sources: dict) -> list[dict]:
    """Canonical, path-free source-run and card references."""
    memberships = {}
    for partition in ("train", "validation", "test"):
        for group in plan["partitions"][partition]["group_ids"]:
            if group in memberships:
                raise ValueError("duplicate source-group partition membership")
            memberships[group] = partition
    if set(memberships) != set(sources):
        raise ValueError("model artifact missing source-run group")
    rows = []
    for group in sorted(sources):
        source = sources[group]
        card = synthetic_run_card(source["path"].parent)
        if (card["run_provenance"]["export_id"] != source["source_id"] or
                card["run_provenance"]["events_jsonl_sha256"] != source["source_data_sha256"] or
                card["run_provenance"]["config_sha256"] != source["config_sha256"] or
                card["run_provenance"]["model_source_sha256"] != source["model_source_sha256"]):
            raise ValueError("source data and dataset card disagree")
        rows.append({
            "group_id": group, "source_id": source["source_id"],
            "source_data_sha256": source["source_data_sha256"],
            "config_sha256": source["config_sha256"],
            "model_source_sha256": source["model_source_sha256"],
            "dataset_card_id": card["card_id"],
            "partition": memberships[group],
        })
    return rows


def validate_model_artifact(artifact: Any) -> None:
    """Validate the complete *offline* JSON contract before trusting it.

    This is structural + self-consistency validation; source matching requires
    verify_model_artifact with actual local source data and a split manifest.
    """
    if type(artifact) is not dict or set(artifact) != TOP_KEYS:
        raise ValueError("model artifact has missing or unexpected top-level keys")
    if artifact["artifact_version"] != ARTIFACT_VERSION:
        raise ValueError("unsupported model artifact version")
    if artifact["kind"] != KIND or artifact["algorithm"] != "healthy_training_zscore_euclidean":
        raise ValueError("unsupported model artifact algorithm")
    if artifact["model_version"] != MODEL_VERSION:
        raise ValueError("unsupported trained model version")
    if artifact["claimed_failure_probability"] is not False or artifact["remaining_useful_life"] is not None:
        raise ValueError("synthetic artifact must not claim calibrated prognostics")
    if type(artifact["limitations"]) is not str or not artifact["limitations"]:
        raise ValueError("model artifact must state scientific limitations")
    for key in ("artifact_sha256", "model_sha256", "processor_sha256", "split_plan_sha256"):
        _digest(artifact[key], key)
    model = artifact["model"]
    if type(model) is not dict or model.get("model_version") != MODEL_VERSION or (
        model.get("method") != artifact["algorithm"] or
        model.get("score_direction") != "higher_is_more_unusual" or
        model.get("score_is_failure_probability") is not False or
        model.get("remaining_useful_life") is not None
    ):
        raise ValueError("invalid embedded trained model")
    if model.get("model_sha256") != artifact["model_sha256"] or (
        _hash({k:v for k,v in model.items() if k != "model_sha256"}) != model["model_sha256"]
    ):
        raise ValueError("embedded model checksum mismatch")
    contract = model.get("feature_contract")
    if type(contract) is not dict or contract.get("names") != list(FEATURES) or (
        contract.get("units") != list(FEATURE_UNITS) or
        contract.get("sample_rate_hz") != 1024 or
        contract.get("sample_count") != 1024 or
        artifact["feature_contract"] != contract
    ):
        raise ValueError("artifact feature names, order, units or sampling incompatible")
    params = model.get("feature_processing")
    if type(params) is not dict or params.get("pipeline_version") != PIPELINE_VERSION or (
        params.get("fit_partition") != "train" or
        params.get("feature_names") != list(FEATURES) or
        params.get("feature_units") != list(FEATURE_UNITS) or
        params.get("excluded_inputs") != list(EXCLUDED)
    ):
        raise ValueError("unsupported or changed train-only preprocessing contract")
    if params.get("pipeline_sha256") != artifact["processor_sha256"] or (
        _hash({k:v for k,v in params.items() if k != "pipeline_sha256"}) != artifact["processor_sha256"]
    ):
        raise ValueError("preprocessing checksum mismatch")
    sampling = params.get("sampling")
    if sampling != {"sample_rate_hz": 1024, "sample_count": 1024,
                    "waveform_window_seconds": 1.0, "rolling_lookback_ticks": 5}:
        raise ValueError("unsupported model sampling/rolling contract")
    for name in ("center", "population_std", "effective_scales"):
        a = model.get(name)
        b = params.get(name)
        if (type(a) is not list or type(b) is not list or len(a) != len(FEATURES) or
                a != b or any(type(v) not in (int,float) or not isfinite(v) or
                             (name == "effective_scales" and v <= 0) or
                             (name == "population_std" and v < 0) for v in a)):
            raise ValueError(f"incompatible fitted parameters: {name}")
    train = model.get("training")
    if type(train) is not dict or train.get("fit_partitions") != ["train"] or (
        train.get("split_plan_sha256") != artifact["split_plan_sha256"] or
        params.get("split_plan_sha256") != artifact["split_plan_sha256"] or
        params.get("training_windows") != train.get("healthy_good_sensor_events") or
        type(params.get("training_windows")) is not int or
        params["training_windows"] < 8
    ):
        raise ValueError("artifact preprocessing/training provenance mismatch")
    groups = artifact["training_groups"]
    if (type(groups) is not list or not groups or
            any(type(g) is not str or not g for g in groups) or
            len(groups) != len(set(groups)) or groups != sorted(groups) or
            groups != train.get("groups") or groups != params.get("train_groups")):
        raise ValueError("model artifact training group mismatch")
    cal = model.get("calibration")
    if type(cal) is not dict or cal.get("partition") != "train" or (
        cal.get("quantile") != .99 or cal.get("comparison") != "score > threshold" or
        type(cal.get("threshold")) not in (int,float) or
        not isfinite(cal["threshold"]) or cal["threshold"] < 0
    ):
        raise ValueError("invalid frozen training-calibrated threshold")
    rows = artifact["source_runs"]
    if type(rows) is not list or not 3 <= len(rows) <= 100:
        raise ValueError("model artifact needs 3-100 source runs")
    source_groups = set()
    partitions = {"train": set(), "validation":set(), "test":set()}
    for row in rows:
        if type(row) is not dict or set(row) != SOURCE_KEYS:
            raise ValueError("malformed source-run provenance")
        for key in ("source_data_sha256","model_source_sha256","config_sha256"):
            _digest(row[key], key)
        for key in ("group_id","source_id","dataset_card_id"):
            if type(row[key]) is not str or not row[key]:
                raise ValueError(f"missing source-run {key}")
        if row["group_id"] in source_groups or row["partition"] not in partitions:
            raise ValueError("duplicate source groups or invalid partitions")
        source_groups.add(row["group_id"])
        partitions[row["partition"]].add(row["group_id"])
    if rows != sorted(rows,key=lambda r:r["group_id"]) or (
        any(not members for members in partitions.values()) or
        partitions["train"] != set(groups) or
        params.get("train_source_sha256") != {
            r["group_id"]:r["source_data_sha256"] for r in rows if r["partition"] == "train"
        }
    ):
        raise ValueError("source-run partition or train-data digests incompatible")
    cards = train.get("dataset_cards")
    by_group = {r["group_id"]:r for r in rows}
    if type(cards) is not list or len(cards) != len(groups):
        raise ValueError("trained dataset cards missing")
    for group,card in zip(groups,cards):
        src = by_group[group]
        if type(card) is not dict or (
            card.get("card_id") != src["dataset_card_id"] or
            card.get("export_id") != src["source_id"] or
            card.get("config_sha256") != src["config_sha256"] or
            card.get("model_source_sha256") != src["model_source_sha256"]
        ):
            raise ValueError("training dataset-card provenance mismatch")
    runtime = artifact["runtime"]
    if type(runtime) is not dict or set(runtime) != {
        "python_version", "implementation", "producer", "producer_sha256",
        "runtime_dependencies", "portability_note"
    } or runtime["producer"] != "motorpulse.model_artifact" or (
        runtime["runtime_dependencies"] != [] or
        any(type(runtime[k]) is not str or not runtime[k] for k in
            ("python_version", "implementation", "portability_note"))
    ):
        raise ValueError("invalid artifact runtime provenance")
    _digest(runtime["producer_sha256"], "artifact producer code")
    if _hash({k:v for k,v in artifact.items() if k != "artifact_sha256"}) != artifact["artifact_sha256"]:
        raise ValueError("model artifact checksum mismatch")


def build_model_artifact(plan: dict, manifests: Sequence[str | Path], model: dict) -> dict:
    """Build only from fully verified local sources and a frozen trained model."""
    sources = _validated_sources(plan, manifests)
    _validate_model(model, plan, sources)
    if model.get("model_version") != MODEL_VERSION:
        raise ValueError("unknown model version")
    artifact = {
        "artifact_version": ARTIFACT_VERSION, "kind": KIND,
        "algorithm": "healthy_training_zscore_euclidean",
        "model_version": MODEL_VERSION,
        "model": deepcopy(model),
        "model_sha256": model["model_sha256"],
        "processor_sha256": model["feature_processing"]["pipeline_sha256"],
        "split_plan_sha256": plan["plan_sha256"],
        "feature_contract": deepcopy(model["feature_contract"]),
        "training_groups": sorted(plan["partitions"]["train"]["group_ids"]),
        "source_runs": _source_rows(plan,sources),
        "runtime": {
            "python_version": platform.python_version(),
            "implementation": platform.python_implementation(),
            "producer": "motorpulse.model_artifact",
            "producer_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "runtime_dependencies": [],
            "portability_note": "Same code and Python runtime are needed for bit-stable results; file SHA-256 is not a signature.",
        },
        "claimed_failure_probability": False, "remaining_useful_life": None,
        "limitations": "Synthetic-only model; not a validated field fault diagnosis, failure probability, physical lead time or RUL.",
    }
    artifact["artifact_sha256"] = _hash(artifact)
    validate_model_artifact(artifact)
    return artifact


def verify_model_artifact(artifact: dict, plan: dict,
                          manifests: Sequence[str | Path]) -> dict:
    """Revalidate model + hashes + original complete source-run membership.

    Fails closed on any changed or missing local data. Never retrains.
    """
    validate_model_artifact(artifact)
    sources = _validated_sources(plan, manifests)
    _validate_model(artifact["model"], plan, sources)
    if (artifact["split_plan_sha256"] != plan["plan_sha256"] or
            artifact["training_groups"] != sorted(plan["partitions"]["train"]["group_ids"]) or
            artifact["source_runs"] != _source_rows(plan,sources)):
        raise ValueError("model artifact does not match original split/source/dataset cards")
    return deepcopy(artifact["model"])


def save_model_artifact(path: str | Path, artifact: dict) -> None:
    """Exclusive-create JSON with rollback of *our own* partial new output."""
    validate_model_artifact(artifact)
    p = Path(path)
    if p.is_symlink():
        raise ValueError("model artifact output may not be a symlink")
    data = (json.dumps(artifact, indent=2, ensure_ascii=False,
                                    sort_keys=True, allow_nan=False) + "\n")
    if len(data.encode("utf-8")) > MAX_ARTIFACT_BYTES:
        raise ValueError("model artifact exceeds 512 KiB")
    created = False
    try:
        with p.open("x", encoding="utf-8", newline="\n") as stream:
            created = True
            stream.write(data)
    except BaseException:
        if created:
            p.unlink(missing_ok=True)
        raise


def load_model_artifact(path: str | Path, *, plan: dict,
                        manifests: Sequence[str | Path]) -> dict:
    """Read safely as strict size-bounded JSON, verify sources, return frozen model."""
    p = Path(path)
    if p.is_symlink() or not p.is_file():
        raise ValueError("model artifact must be an existing regular non-symlink JSON file")
    data = _read_strict_json(p, MAX_ARTIFACT_BYTES)
    return verify_model_artifact(data, plan, manifests)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Create or verify safe versioned JSON synthetic-model artifacts")
    sub = parser.add_subparsers(dest="command", required=True)
    create = sub.add_parser("save", help="package a trained MP-010 model from local sources")
    verify = sub.add_parser("verify", help="revalidate an artifact against original local sources")
    for command in (create,verify):
        command.add_argument("--split", type=Path, required=True,
                             help="MP-030 whole-run split-plan.json")
        command.add_argument("--input", type=Path, nargs="+", required=True,
                             help="ALL original source manifest.json paths in the split")
    create.add_argument("--model", type=Path, required=True,
                        help="MP-010 trained-model.json with model key")
    create.add_argument("--out", type=Path, required=True,
                        help="new versioned JSON artifact; never overwrite")
    verify.add_argument("--artifact", type=Path, required=True)
    args = parser.parse_args()
    try:
        plan = _read_strict_json(args.split, 256 * 1024)
        if args.command == "save":
            package = _read_strict_json(args.model, 256 * 1024)
            if type(package) is not dict or type(package.get("model")) is not dict:
                raise ValueError("--model must be MP-010 JSON containing model")
            artifact = build_model_artifact(plan, args.input, package["model"])
            save_model_artifact(args.out, artifact)
            print(f"Saved model artifact: {args.out} ({artifact['artifact_sha256'][:16]})")
        else:
            model = load_model_artifact(args.artifact, plan=plan, manifests=args.input)
            print(f"Verified model artifact: {args.artifact} ({model['model_sha256'][:16]})")
    except (OSError, ValueError, KeyError, TypeError, OverflowError) as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    main()
