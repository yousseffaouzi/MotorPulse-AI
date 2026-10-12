"""MP-033: deterministic, fully offline synthetic experiment orchestration.

Only this module owns its newly created output directory. Source export
manifests retain actual creation timestamps, but experiment identity and
downstream model/evaluation results exclude that nondeterministic field.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import platform
import shutil
import sys
from typing import Any

from .anomaly import train_baseline
from .dataset_cards import synthetic_run_card
from .evaluation import evaluate, markdown as evaluation_markdown
from .export import export_dataset
from .ims import _read_strict_json, write_local_manifest
from .scenarios import configuration_dict, parse_configuration
from .sim import MotorSimulator, parse_start_time_utc
from .splits import _hash, _ratios, group_split

EXPERIMENT_VERSION = "1.0.0"
MAX_CONFIG_BYTES = 65536
MAX_RUNS = 12
REQUIRED = frozenset({
    "experiment_version", "seeds", "ticks", "assets", "virtual_start_utc",
    "step_seconds", "split_seed", "split_ratios",
})


def validate_experiment_config(raw: Any) -> dict:
    """Validate a strict, path-free, completely specified local experiment."""
    if type(raw) is not dict or set(raw) != REQUIRED:
        raise ValueError("experiment config must contain exactly the v1 required fields")
    if raw["experiment_version"] != EXPERIMENT_VERSION:
        raise ValueError("unsupported experiment version")
    seeds = raw["seeds"]
    if (type(seeds) is not list or not 3 <= len(seeds) <= MAX_RUNS or
            any(type(s) is not int or not 0 <= s <= 2**32 - 1 for s in seeds) or
            len(set(seeds)) != len(seeds)):
        raise ValueError("3-12 distinct integer generator seeds in [0, 2^32-1] are required")
    ticks = raw["ticks"]
    if type(ticks) is not int or not 8 <= ticks <= 1000:
        raise ValueError("ticks must be an integer between 8 and 1000")
    assets = parse_configuration(raw["assets"])
    start = parse_start_time_utc(raw["virtual_start_utc"])
    step = raw["step_seconds"]
    # Central simulation contract checks UTC offset, clock precision, bounds.
    simulation = MotorSimulator(seed=seeds[0], assets=assets,
                                start_time_utc=start, step_seconds=step)
    simulation.timestamp_for_tick(ticks)
    split_seed = raw["split_seed"]
    if type(split_seed) is not int or not 0 <= split_seed <= 2**32 - 1:
        raise ValueError("split_seed must be an integer in [0, 2^32-1]")
    ratios = _ratios(raw["split_ratios"])
    # Normalized config is stable regardless of JSON whitespace/key ordering.
    return {
        "experiment_version": EXPERIMENT_VERSION,
        "seeds": sorted(seeds), "ticks": ticks,
        "assets": configuration_dict(assets),
        "virtual_start_utc": start.isoformat(),
        "step_seconds": simulation.step_seconds,
        "split_seed": split_seed, "split_ratios": list(ratios),
    }


def load_experiment_config(path: str | Path) -> dict:
    p = Path(path)
    if p.is_symlink() or not p.is_file():
        raise ValueError("experiment configuration must be a local, regular non-symlink JSON file")
    return validate_experiment_config(_read_strict_json(p, MAX_CONFIG_BYTES))


def _sha_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as inp:
        for block in iter(lambda: inp.read(65536), b""):
            h.update(block)
    return h.hexdigest()


def _write_markdown(path: Path, contents: str) -> None:
    created = False
    try:
        with path.open("x", encoding="utf-8", newline="\n") as out:
            created = True
            out.write(contents)
    except BaseException:
        if created:
            path.unlink(missing_ok=True)
        raise


def _summary(config: dict, model: dict, reports: dict[str, dict]) -> str:
    lines = [
        "# MotorPulse AI — Reproducible synthetic experiment", "",
        "## Experiment parameters", "",
        f"- Seeds: {config['seeds']}",
        f"- Ticks/run: {config['ticks']}",
        f"- Virtual start UTC: {config['virtual_start_utc']}",
        f"- Split ratios by full source run: {config['split_ratios']}",
        f"- Healthy sensor-good training windows: {model['training']['healthy_good_sensor_events']}",
        f"- Frozen training anomaly threshold: {model['calibration']['threshold']}",
        f"- Training-only preprocessing SHA-256: {model['feature_processing']['pipeline_sha256']}", "",
    ]
    for name in ("validation", "test"):
        lines += ["## " + name.title(), "", evaluation_markdown(reports[name]), ""]
    lines += [
        "## Interpretation", "",
        "This is a synthetic-only demonstration. Split membership is by complete",
        "generator run, and the same fitted parameters and threshold are used",
        "for validation and test. Data-leakage checks are performed by the",
        "underlying split, model and evaluator modules.", "",
        "Fault labels and onset/delay are scripted simulation truth; results",
        "are NOT industrial predictive-maintenance accuracy, a physical",
        "failure probability, real maintenance lead time, or RUL.", "",
        "Actual per-export manifest creation timestamps are intentionally",
        "excluded from deterministic experiment fingerprints.", "",
    ]
    return "\n".join(lines)


def run_experiment(config: dict, output_dir: str | Path) -> dict:
    """Write one exclusively owned experiment directory; clean only on failure.

    All relative paths are fixed code-defined names derived from validated
    integer seeds. No path, shell command or filename is loaded from config.
    """
    cfg = validate_experiment_config(config)
    root = Path(output_dir)
    if not root.parent.is_dir() or root.parent.is_symlink():
        raise ValueError("output parent must exist and must not be a symlink")
    # Atomic ownership claim: existing folders are never touched or deleted.
    root.mkdir(exist_ok=False)
    try:
        start = parse_start_time_utc(cfg["virtual_start_utc"])
        assets = parse_configuration(cfg["assets"])
        run_root = root / "runs"
        run_root.mkdir()
        manifests = []
        cards = {}
        source_semantic_hashes = {}
        stable_paths = ["experiment-config.json"]
        write_local_manifest(root / "experiment-config.json", cfg)
        for seed in cfg["seeds"]:
            run_name = f"seed-{seed:010d}"
            dest = run_root / run_name
            info = export_dataset(dest, ticks=cfg["ticks"], seed=seed,
                                  assets=assets, start_time_utc=start,
                                  step_seconds=cfg["step_seconds"], file_format="jsonl")
            manifest_path = dest / "manifest.json"
            manifests.append(manifest_path)
            source_semantic_hashes[run_name] = _hash({
                k: v for k, v in info.items() if k != "created_at_utc"
            })
            card = synthetic_run_card(dest)
            write_local_manifest(dest / "dataset-card.json", card)
            cards[run_name] = {"card_id": card["card_id"],
                               "export_id": info["export_id"],
                               "source_data_sha256": info["files"]["events.jsonl"]["sha256"],
                               "dataset_card_sha256": _sha_file(dest / "dataset-card.json")}
            stable_paths.extend([f"runs/{run_name}/events.jsonl",
                                 f"runs/{run_name}/dataset-card.json"])
        plan = group_split(manifests, source_type="synthetic",
                           seed=cfg["split_seed"], ratios=cfg["split_ratios"])
        write_local_manifest(root / "split-plan.json", plan)
        stable_paths.append("split-plan.json")
        model = train_baseline(plan, manifests)
        write_local_manifest(root / "trained-model.json", {"model": model})
        stable_paths.append("trained-model.json")
        reports = {}
        for partition in ("validation", "test"):
            report = evaluate(plan, manifests, model, partition=partition,
                              max_events=0)
            reports[partition] = report
            filename = f"{partition}-metrics.json"
            write_local_manifest(root / filename, report)
            stable_paths.append(filename)
        _write_markdown(root / "SUMMARY.md", _summary(cfg, model, reports))
        stable_paths.append("SUMMARY.md")
        # SHA values below are over exact bytes of stable artifacts. The
        # exporter manifest created_at_utc is recorded separately by a
        # normalized semantic hash, not misrepresented as a raw file SHA.
        stable_hashes = {path: _sha_file(root / path) for path in sorted(stable_paths)}
        index = {
            "experiment_version": EXPERIMENT_VERSION,
            "source": "synthetic_only",
            "config_sha256": _hash(cfg),
            "environment": {
                "python": ".".join(map(str, sys.version_info[:3])),
                "implementation": platform.python_implementation(),
                "runtime_dependencies": [],
                "tool": "motorpulse.experiment",
                "tool_source_sha256": _sha_file(Path(__file__)),
                "portability_note": "Same source/runtime yields stable results; cross-version floating-point equality not guaranteed.",
            },
            "runs": cards,
            "source_manifest_semantic_sha256": source_semantic_hashes,
            "export_manifest_note": "Raw generator manifest contains wall-clock created_at_utc and its exact bytes differ across reruns; the semantic digest omits only that field.",
            "stable_artifact_sha256": stable_hashes,
            "split_plan_sha256": plan["plan_sha256"],
            "model_sha256": model["model_sha256"],
            "feature_pipeline_sha256": model["feature_processing"]["pipeline_sha256"],
            "feature_pipeline_version": model["feature_processing"]["pipeline_version"],
            "evaluation_sha256": {p: reports[p]["evaluation_sha256"]
                                  for p in ("validation", "test")},
            "training_groups": plan["partitions"]["train"]["group_ids"],
            "heldout_groups": {p: plan["partitions"][p]["group_ids"]
                               for p in ("validation", "test")},
            "no_real_data": True,
            "claimed_failure_probability": False,
            "remaining_useful_life": None,
            "limitations": "Synthetic run-seeded evaluation only. No industrial machine reliability, physical failure probability or RUL.",
        }
        index["experiment_sha256"] = _hash(index)
        write_local_manifest(root / "experiment-index.json", index)
        return index
    except BaseException:
        # Only this call created root, so no unrelated user files are removed.
        shutil.rmtree(root)
        raise


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run a reproducible, offline synthetic ML experiment (MP-033)")
    parser.add_argument("--config", required=True, type=Path,
                        help="strict local experiment JSON (no external paths)")
    parser.add_argument("--out-dir", required=True, type=Path,
                        help="new output directory, never overwrite")
    args = parser.parse_args()
    try:
        cfg = load_experiment_config(args.config)
        result = run_experiment(cfg, args.out_dir)
    except (OSError, ValueError, TypeError, KeyError, OverflowError) as exc:
        parser.error(str(exc))
    print("Synthetic experiment complete: " + str(args.out_dir) +
          " (sha256=" + result["experiment_sha256"][:16] +
          ", train groups=" + str(len(result["training_groups"])) + ")")


if __name__ == "__main__":
    main()
