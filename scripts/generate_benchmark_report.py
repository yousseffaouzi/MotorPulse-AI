#!/usr/bin/env python3
"""Generate the dated MP-015 synthetic benchmark Markdown and SVG demo card.

The generator runs the existing MP-033 experiment CLI with a fixed local config,
then summarizes its deterministic validation/test JSON. It uses only the Python
standard library and creates new outputs exclusively; it never downloads data.
"""

from __future__ import annotations

import argparse
from datetime import date
from html import escape
import json
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / "docs" / "examples" / "experiment-v1.json"


def _read_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        value = json.load(handle)
    if type(value) is not dict:
        raise ValueError(f"expected JSON object: {path}")
    return value


def _validated_date(value: str) -> str:
    parsed = date.fromisoformat(value)
    if parsed.isoformat() != value:
        raise ValueError("--date must be canonical YYYY-MM-DD")
    return value


def _ensure_new_output(path: Path) -> None:
    if not path.parent.is_dir() or path.parent.is_symlink():
        raise ValueError(f"output parent must exist and not be a symlink: {path.parent}")
    if path.exists() or path.is_symlink():
        raise ValueError(f"output already exists: {path}")


def _run_experiment(config: Path) -> tuple[dict, dict, dict, dict]:
    if not config.is_file() or config.is_symlink():
        raise ValueError("benchmark config must be a local regular non-symlink file")
    with TemporaryDirectory(prefix="motorpulse-mp015-") as temp:
        root = Path(temp)
        experiment = root / "experiment"
        env = dict(os.environ)
        previous = env.get("PYTHONPATH")
        env["PYTHONPATH"] = str(ROOT) if not previous else str(ROOT) + os.pathsep + previous
        command = [
            sys.executable,
            "-m",
            "motorpulse.experiment",
            "--config",
            str(config),
            "--out-dir",
            str(experiment),
        ]
        result = subprocess.run(
            command,
            cwd=ROOT,
            env=env,
            text=True,
            capture_output=True,
            timeout=120,
            check=False,
        )
        if result.returncode != 0:
            raise RuntimeError(
                "benchmark experiment failed\n"
                f"stdout:\n{result.stdout}\n"
                f"stderr:\n{result.stderr}"
            )
        normalized_config = _read_json(experiment / "experiment-config.json")
        index = _read_json(experiment / "experiment-index.json")
        validation = _read_json(experiment / "validation-metrics.json")
        test = _read_json(experiment / "test-metrics.json")
    return normalized_config, index, validation, test


def _format(value: object) -> str:
    if value is None:
        return "undefined"
    if type(value) is float:
        rendered = f"{value:.6f}".rstrip("0").rstrip(".")
        return rendered or "0"
    return str(value)


def _metric_table(report: dict) -> list[str]:
    overall = report["overall"]
    lines = [
        "| Metric | Model | Rules |",
        "| --- | ---: | ---: |",
    ]
    for label, key in (
        ("Eligible windows", "n"),
        ("TP", "tp"),
        ("FP", "fp"),
        ("TN", "tn"),
        ("FN", "fn"),
        ("Precision", "precision"),
        ("Recall", "recall"),
        ("F1", "f1"),
        ("FPR", "false_positive_rate"),
        ("PR average precision", "average_precision"),
        (
            "False alarms / simulated negative hour",
            "false_alarms_per_simulated_negative_hour",
        ),
    ):
        lines.append(
            f"| {label} | {_format(overall['model'][key])} | "
            f"{_format(overall['rules'][key])} |"
        )
    return lines


def _partition_section(title: str, report: dict) -> list[str]:
    cohort = report["comparison_cohort"]
    episodes = report["detection_episodes"]
    return [
        f"## {title} held-out",
        "",
        f"- Whole-run evaluated groups: `{', '.join(report['evaluated_groups'])}`",
        f"- Eligible good-sensor windows: {cohort['eligible_both_methods']} / {cohort['total_windows']}",
        f"- Sensor abstentions: `{json.dumps(cohort['abstentions'], sort_keys=True)}`",
        f"- Synthetic fault episodes: {episodes['total']} total; model detected "
        f"{episodes['detected']}, missed {episodes['missed']}; mean delay "
        f"{_format(episodes['mean_delay_seconds'])} simulated seconds",
        "",
        *_metric_table(report),
        "",
        f"Evaluation SHA-256: `{report['evaluation_sha256']}`",
        "",
    ]


def _markdown(
    benchmark_date: str,
    config_path: Path,
    config: dict,
    index: dict,
    validation: dict,
    test: dict,
) -> str:
    relative_config = config_path.relative_to(ROOT).as_posix()
    lines = [
        "# MotorPulse AI — Dated synthetic benchmark (MP-015)",
        "",
        f"**Benchmark date:** {benchmark_date}",
        "",
        "This is a **synthetic-only** reproducibility snapshot. It compares the frozen",
        "healthy-trained anomaly baseline with the existing illustrative rules on",
        "disjoint **whole-run** held-out generator runs. These numbers are **not field performance**.",
        "They are not calibrated failure probability, physical maintenance lead time,",
        "industrial reliability, or Remaining Useful Life (**RUL**) evidence.",
        "",
        "![Synthetic benchmark demo card](demo/benchmark-summary.svg)",
        "",
        "## Reproduce",
        "",
        "Run the underlying experiment into a new directory:",
        "",
        "```bash",
        "python -m motorpulse.experiment \\",
        f"  --config {relative_config} \\",
        "  --out-dir /tmp/motorpulse-mp015-experiment",
        "```",
        "",
        "Regenerate this report and its repo-local SVG media on Python 3.13:",
        "",
        "```bash",
        "python scripts/generate_benchmark_report.py \\",
        f"  --date {benchmark_date} \\",
        f"  --config {relative_config} \\",
        "  --markdown docs/BENCHMARK.md \\",
        "  --svg docs/demo/benchmark-summary.svg",
        "```",
        "",
        "The generator creates outputs exclusively and refuses to overwrite existing files.",
        "For a byte-for-byte check, generate into new temporary paths; the Python 3.13",
        "regression test does exactly that. Cross-Python floating-point byte identity is",
        "not claimed by the project.",
        "",
        "## Fixed benchmark setup",
        "",
        f"- Config: `{relative_config}`",
        f"- Generator seeds: `{config['seeds']}`",
        f"- Ticks per run: {config['ticks']}",
        f"- Virtual step: {config['step_seconds']} seconds",
        f"- Whole-run split ratios: `{config['split_ratios']}`",
        f"- Training groups: `{', '.join(index['training_groups'])}`",
        f"- Validation groups: `{', '.join(index['heldout_groups']['validation'])}`",
        f"- Test groups: `{', '.join(index['heldout_groups']['test'])}`",
        "- Model fitting: healthy + sensor-good training windows only; preprocessing and",
        "  the original anomaly threshold stay frozen for validation/test.",
        "- Both model and rules use the same good-sensor held-out denominator; missing",
        "  and injected-outlier windows are abstentions.",
        "",
        *_partition_section("Validation", validation),
        *_partition_section("Test", test),
        "## Provenance",
        "",
        f"- Experiment config SHA-256: `{index['config_sha256']}`",
        f"- Split plan SHA-256: `{index['split_plan_sha256']}`",
        f"- Trained model SHA-256: `{index['model_sha256']}`",
        f"- Portable artifact SHA-256: `{index['model_artifact_sha256']}`",
        f"- Feature pipeline SHA-256: `{index['feature_pipeline_sha256']}`",
        "- Runtime dependencies recorded by the experiment: none.",
        "- Source data: locally generated MotorPulse synthetic feature events only; no",
        "  IMS archive or third-party derived records are used.",
        "",
        "## Interpretation limits",
        "",
        "The benchmark is a software/reproducibility demonstration against scripted",
        "simulator truth. Distinct seeds still share the same generator equations and do",
        "not establish independent machine populations. A higher synthetic metric does",
        "not validate diagnosis, alert calibration, domain transfer, maintenance value,",
        "failure probability, or RUL. The SVG is generated from the same test report and",
        "is demo media, not a screenshot of physical equipment or measured telemetry.",
        "",
    ]
    return "\n".join(lines)


def _svg(benchmark_date: str, test: dict) -> str:
    model = test["overall"]["model"]
    rules = test["overall"]["rules"]
    cohort = test["comparison_cohort"]
    rows = [
        ("Precision", _format(model["precision"]), _format(rules["precision"])),
        ("Recall", _format(model["recall"]), _format(rules["recall"])),
        ("F1", _format(model["f1"]), _format(rules["f1"])),
        ("FPR", _format(model["false_positive_rate"]), _format(rules["false_positive_rate"])),
    ]
    text_rows = []
    y = 220
    for label, model_value, rule_value in rows:
        text_rows.extend(
            [
                f'<text x="70" y="{y}" font-size="20">{escape(label)}</text>',
                f'<text x="360" y="{y}" font-size="20" text-anchor="middle">{escape(model_value)}</text>',
                f'<text x="590" y="{y}" font-size="20" text-anchor="middle">{escape(rule_value)}</text>',
            ]
        )
        y += 48
    return "\n".join(
        [
            '<svg xmlns="http://www.w3.org/2000/svg" width="760" height="500" viewBox="0 0 760 500" role="img" aria-labelledby="title desc">',
            '<title id="title">MotorPulse AI synthetic benchmark summary</title>',
            '<desc id="desc">Held-out test metrics for the synthetic anomaly model and illustrative rules. Not field performance.</desc>',
            '<rect width="760" height="500" fill="#ffffff"/>',
            '<rect x="28" y="28" width="704" height="444" rx="16" fill="#f6f7f9" stroke="#20242a"/>',
            '<text x="70" y="82" font-size="30" font-weight="700">MotorPulse AI</text>',
            f'<text x="70" y="116" font-size="20">Synthetic benchmark · {escape(benchmark_date)}</text>',
            '<text x="70" y="154" font-size="18" font-weight="700">Held-out test</text>',
            f'<text x="70" y="180" font-size="16">Eligible windows: {cohort["eligible_both_methods"]} / {cohort["total_windows"]}</text>',
            '<text x="360" y="180" font-size="18" font-weight="700" text-anchor="middle">Model</text>',
            '<text x="590" y="180" font-size="18" font-weight="700" text-anchor="middle">Rules</text>',
            *text_rows,
            '<line x1="70" y1="420" x2="690" y2="420" stroke="#20242a"/>',
            '<text x="70" y="452" font-size="16" font-weight="700">Not field performance · synthetic-only · no failure probability or RUL</text>',
            '</svg>',
            "",
        ]
    )


def _write_new(path: Path, content: str) -> None:
    _ensure_new_output(path)
    with path.open("x", encoding="utf-8", newline="\n") as handle:
        handle.write(content)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate MP-015 synthetic benchmark Markdown and SVG demo media"
    )
    parser.add_argument("--date", required=True, help="benchmark date as YYYY-MM-DD")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--markdown", type=Path, required=True)
    parser.add_argument("--svg", type=Path, required=True)
    args = parser.parse_args()
    try:
        benchmark_date = _validated_date(args.date)
        config_path = args.config if args.config.is_absolute() else ROOT / args.config
        config_path = config_path.absolute()
        if args.markdown.absolute() == args.svg.absolute():
            raise ValueError("Markdown and SVG outputs must differ")
        _ensure_new_output(args.markdown)
        _ensure_new_output(args.svg)
        config, index, validation, test = _run_experiment(config_path)
        markdown = _markdown(
            benchmark_date, config_path, config, index, validation, test
        )
        svg = _svg(benchmark_date, test)
        _write_new(args.markdown, markdown)
        try:
            _write_new(args.svg, svg)
        except BaseException:
            args.markdown.unlink(missing_ok=True)
            raise
    except (OSError, ValueError, RuntimeError, KeyError, TypeError) as exc:
        parser.error(str(exc))
    print(
        "Generated synthetic-only MP-015 benchmark: "
        f"{args.markdown} and {args.svg}"
    )


if __name__ == "__main__":
    main()
