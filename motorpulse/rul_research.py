"""MP-039: a metadata-only RUL study evidence gate, NOT a prognostic model.

No failure time is ever inferred from MP-020 scripted fault onset,
MP-011 alert delay, or MP-010 anomaly score. A structurally valid protocol
still needs *independent* source, endpoint and rights review.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timedelta
import hashlib
from pathlib import Path
import platform
import re
import sys
from typing import Any

from .experiment import _write_markdown
from .ims import _read_strict_json, write_local_manifest
from .splits import _hash

PROTOCOL_VERSION = "1.0.0"
MAX_TRAJECTORIES = 1000
MAX_PROTOCOL_BYTES = 512 * 1024
SPLITS = ("train", "validation", "test")
CENSOR_REASONS = (
    "administrative_end",
    "lost_followup",
    "sensor_loss",
    "preventive_replacement",
    "competing_failure",
)
FAILURE_EVIDENCE_KINDS = (
    "instrumented_failure_log",
    "maintenance_failure_log",
    "inspection_confirmed_failure",
    "synthetic_method_fixture",
)
EVENT_STATES = ("failure_observed", "right_censored")
METRICS = (
    {
        "name": "censor_aware_concordance",
        "intent": "discrimination on comparable event-censor pairs; specify tie handling",
        "condition": "independent outcome/censor review; comparable pairs and held-out risk estimates",
        "not_a_point_rul_claim": True,
    },
    {
        "name": "ipcw_brier_at_preregistered_horizons",
        "intent": "probabilistic survival calibration and discrimination at each declared horizon",
        "condition": "train-only censor survival estimator, positive censor-support and held-out survival probabilities",
        "not_a_point_rul_claim": True,
    },
    {
        "name": "ipcw_integrated_brier",
        "intent": "average horizon-specific prediction error over prespecified supported horizon",
        "condition": "train-only censor model, fixed integration interval and nonzero supported at-risk cohort",
        "not_a_point_rul_claim": True,
    },
    {
        "name": "calibration_by_horizon",
        "intent": "compare predicted vs observed event risk with censor-aware estimators",
        "condition": "sufficient held-out events, prespecified probability bins/horizons and censor correction",
        "not_a_point_rul_claim": True,
    },
    {
        "name": "mae_on_uncensored_only_descriptive",
        "intent": "descriptive point-error conditional on observed failure only; selection-biased",
        "condition": "explicitly non-primary; cannot assign event time to censored trajectories",
        "not_a_point_rul_claim": True,
    },
)


def _keys(obj: Any, required: set[str], *, context: str) -> dict:
    if type(obj) is not dict or set(obj) != required:
        raise ValueError(f"{context} must have exactly {', '.join(sorted(required))}")
    return obj


def _label(value: Any, name: str, maximum: int = 160) -> str:
    if (
        type(value) is not str
        or not 1 <= len(value.strip()) <= maximum
        or (value != value.strip())
        or any(ord(ch) < 32 for ch in value)
    ):
        raise ValueError(f"{name} must be a nonempty bounded plain string")
    return value


def _enum(value: Any, values: tuple[str, ...], name: str) -> str:
    if value not in values or type(value) is not str:
        raise ValueError(f"{name} must be one of {values}")
    return value


def _utc(value: Any, name: str) -> datetime:
    if type(value) is not str or not re.fullmatch(
        r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|\+00:00)", value
    ):
        raise ValueError(f"{name}: require explicit RFC3339 UTC timestamp")
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"invalid {name}") from exc
    if result.utcoffset() != timedelta(0):
        raise ValueError(f"{name} must be UTC")
    return result


def _sha(value: Any, name: str) -> str:
    if type(value) is not str or not re.fullmatch(r"[0-9a-f]{64}", value):
        raise ValueError(f"{name} requires a lowercase SHA-256 hex digest")
    return value


def validate_protocol(document: Any) -> dict:
    """Validate structure and chronology without authenticating source claims.

    Returns a compact, derived cohort summary. No ML fit, RUL or prediction.
    """
    study = _keys(
        document,
        {
            "rul_study_version",
            "study_id",
            "data_class",
            "source",
            "endpoint",
            "split",
            "trajectories",
        },
        context="RUL study protocol",
    )
    if study["rul_study_version"] != PROTOCOL_VERSION:
        raise ValueError("unsupported RUL research protocol version")
    _label(study["study_id"], "study_id", 80)
    _enum(
        study["data_class"],
        ("synthetic_method_fixture", "observed_run_to_failure"),
        "data_class",
    )
    source = _keys(
        study["source"],
        {
            "dataset_id",
            "citation",
            "raw_data_sha256",
            "rights_review",
            "failure_annotations_review",
        },
        context="source",
    )
    _label(source["dataset_id"], "dataset_id", 80)
    _label(source["citation"], "citation", 500)
    _sha(source["raw_data_sha256"], "raw_data_sha256")
    _enum(
        source["rights_review"],
        ("unverified", "documented_for_external_review"),
        "source.rights_review",
    )
    _enum(
        source["failure_annotations_review"],
        ("unverified", "documented_for_external_review"),
        "source.failure_annotations_review",
    )
    endpoint = _keys(
        study["endpoint"],
        {
            "failure_event_definition",
            "failure_evidence_kind",
            "clock",
            "time_origin",
            "unit",
            "censoring_assumption",
        },
        context="endpoint",
    )
    _label(endpoint["failure_event_definition"], "failure_event_definition", 600)
    _enum(
        endpoint["failure_evidence_kind"],
        FAILURE_EVIDENCE_KINDS,
        "failure_evidence_kind",
    )
    if (
        endpoint["clock"] != "external_observed_utc"
        or endpoint["time_origin"] != "first_observation_utc"
        or endpoint["unit"] != "seconds"
    ):
        raise ValueError(
            "event clock must be externally observed UTC seconds since first observation"
        )
    _enum(
        endpoint["censoring_assumption"],
        ("unknown_requires_review", "conditionally_independent_requires_review"),
        "censoring_assumption",
    )
    split = _keys(study["split"], {"policy", "groups"}, context="split")
    if split["policy"] != "asset_disjoint_whole_trajectory":
        raise ValueError("RUL research requires asset-disjoint whole-trajectory groups")
    groups = _keys(split["groups"], set(SPLITS), context="split.groups")
    all_groups = []
    for partition in SPLITS:
        part = groups[partition]
        if (
            type(part) is not list
            or not part
            or any(type(item) is not str or not 1 <= len(item) <= 80 for item in part)
            or len(part) != len(set(part))
        ):
            raise ValueError(f"{partition}: unique nonempty group IDs required")
        all_groups.extend(part)
    if len(all_groups) != len(set(all_groups)):
        raise ValueError("train/validation/test group overlap is forbidden")
    rows = study["trajectories"]
    if type(rows) is not list or not 3 <= len(rows) <= MAX_TRAJECTORIES:
        raise ValueError(f"trajectories must contain 3-{MAX_TRAJECTORIES} records")
    seen_trajectories = set()
    asset_groups = {}
    asset_periods: dict[str, list[tuple[datetime, datetime]]] = defaultdict(list)
    status = Counter()
    reasons = Counter()
    groups_seen = Counter()
    durations = []
    source_ids = set(all_groups)
    for n, row in enumerate(rows):
        label = f"trajectory[{n}]"
        r = _keys(
            row,
            {
                "trajectory_id",
                "asset_id",
                "group_id",
                "first_observed_utc",
                "last_observed_utc",
                "status",
                "terminal_failure_utc",
                "failure_evidence_ref",
                "censoring_reason",
                "record_count",
            },
            context=label,
        )
        tid = _label(r["trajectory_id"], label + ".trajectory_id", 80)
        aid = _label(r["asset_id"], label + ".asset_id", 80)
        group = _label(r["group_id"], label + ".group_id", 80)
        if tid in seen_trajectories:
            raise ValueError("duplicate trajectory identity")
        seen_trajectories.add(tid)
        if group not in source_ids:
            raise ValueError("trajectory refers to unlisted split group")
        if aid in asset_groups and asset_groups[aid] != group:
            raise ValueError("physical asset crosses train/validation/test groups")
        asset_groups[aid] = group
        entry = _utc(r["first_observed_utc"], label + ".first_observed_utc")
        last = _utc(r["last_observed_utc"], label + ".last_observed_utc")
        if last <= entry:
            raise ValueError("trajectory requires positive observed duration")
        if (
            type(r["record_count"]) is not int
            or not 2 <= r["record_count"] <= 10_000_000
        ):
            raise ValueError("record_count must be 2-10,000,000")
        state = _enum(r["status"], EVENT_STATES, label + ".status")
        if state == "failure_observed":
            event = _utc(r["terminal_failure_utc"], label + ".terminal_failure_utc")
            if event < last:
                raise ValueError(
                    "terminal failure predates final observed sensor timestamp"
                )
            _label(r["failure_evidence_ref"], label + ".failure_evidence_ref", 300)
            if r["censoring_reason"] is not None:
                raise ValueError("observed failure cannot have a censoring reason")
            exit_time = event
        else:
            if (
                r["terminal_failure_utc"] is not None
                or r["failure_evidence_ref"] is not None
            ):
                raise ValueError(
                    "right-censored trajectory must not invent a failure time/evidence"
                )
            reason = _enum(
                r["censoring_reason"], CENSOR_REASONS, label + ".censoring_reason"
            )
            reasons[reason] += 1
            exit_time = last
        asset_periods[aid].append((entry, exit_time))
        duration = (exit_time - entry).total_seconds()
        if not 0 < duration <= 100 * 365.25 * 86400:
            raise ValueError(
                "trajectory elapsed observation time outside research bounds"
            )
        durations.append(duration)
        status[state] += 1
        groups_seen[group] += 1
    if set(groups_seen) != source_ids:
        raise ValueError("every split group requires an observed trajectory")
    # Two source runs from one machine cannot overlap in observed time.
    for periods in asset_periods.values():
        for previous, following in zip(sorted(periods), sorted(periods)[1:]):
            if previous[1] >= following[0]:
                raise ValueError("overlapping trajectories for the same physical asset")
    return {
        "trajectories": len(rows),
        "assets": len(asset_groups),
        "groups": len(source_ids),
        "per_split": {
            p: sum(groups_seen[group] for group in groups[p]) for p in SPLITS
        },
        "failure_events": status["failure_observed"],
        "right_censored": status["right_censored"],
        "censoring_reasons": dict(sorted(reasons.items())),
        "elapsed_source_seconds": sum(durations),
        "time_origin": endpoint["time_origin"],
        "time_unit": endpoint["unit"],
    }


def audit_protocol(document: Any) -> dict:
    """Audit metadata ONLY; even 'complete' metadata cannot certify field data."""
    cohort = validate_protocol(document)
    blockers = []
    cautions = []
    if document["data_class"] != "observed_run_to_failure":
        blockers.append("synthetic_fixture_is_not_observed_run_to_failure")
    if document["source"]["rights_review"] == "unverified":
        blockers.append("source_rights_unverified")
    if document["source"]["failure_annotations_review"] == "unverified":
        blockers.append("failure_annotations_unverified")
    if document["endpoint"]["failure_evidence_kind"] == "synthetic_method_fixture":
        blockers.append("scripted_synthetic_events_are_not_observed_failures")
    if cohort["failure_events"] == 0:
        blockers.append("no_externally_observed_terminal_failure_events")
    if cohort["right_censored"] == 0:
        cautions.append("no_right_censored_trajectories; inspect sampling/selection")
    for kind in (
        "lost_followup",
        "sensor_loss",
        "preventive_replacement",
        "competing_failure",
    ):
        if cohort["censoring_reasons"].get(kind):
            cautions.append(
                f"{kind}_may_be_informative_or_competing; model_assumptions_need_review"
            )
    if document["endpoint"]["censoring_assumption"] == "unknown_requires_review":
        cautions.append("censoring_independence_assumption_is_undocumented")
    cautions.extend(
        (
            "source_digest_is_self_reported_metadata_not_verified_against_raw_bytes",
            "rights_and_label_review_status_are_self_declared_not_independently_authenticated",
            "protocol_structure_does_not_validate_acquisition_or_physical_failure",
            "prevent_scenario_truth_model_scores_alerts_or_time_to_end_leakage_into_predictors",
        )
    )
    report = {
        "rul_audit_version": PROTOCOL_VERSION,
        "research_track_only": True,
        "provides_rul_estimates": False,
        "allows_rul_model_training": False,
        "data_class": document["data_class"],
        "study_id": document["study_id"],
        "protocol_sha256": _hash(document),
        "status": "blocked"
        if blockers
        else "metadata_complete_external_review_required",
        "blocking_reasons": blockers,
        "research_cautions": cautions,
        "cohort": cohort,
        "research_metrics_not_computed": list(METRICS),
        "leakage_control": (
            "Whole trajectories and every record from a physical asset remain in one "
            "partition. Event/censor timestamps and future interventions are targets "
            "or evaluation metadata, never allowed model input. Preprocessing and "
            "censor survival estimation fit to training groups only."
        ),
        "scientific_limit": (
            "No RUL prediction, simulated truth conversion, physical motor failure "
            "label certification, rights grant or prognostic performance metric. "
            "An external technical and licensing review is required even when "
            "all metadata fields are complete."
        ),
        "environment": {
            "python": ".".join(str(x) for x in sys.version_info[:3]),
            "implementation": platform.python_implementation(),
            "tool": "motorpulse.rul_research",
            "tool_source_sha256": hashlib.sha256(
                Path(__file__).read_bytes()
            ).hexdigest(),
            "runtime_dependencies": [],
        },
    }
    report["rul_audit_sha256"] = _hash(report)
    return report


def markdown(report: dict) -> str:
    if report.get("rul_audit_version") != PROTOCOL_VERSION:
        raise ValueError("unsupported RUL research audit")
    cohort = report["cohort"]
    lines = [
        "# MotorPulse AI — RUL research eligibility metadata audit (MP-039)",
        "",
        f"**Study:** {report['study_id']}",
        f"**Data class:** {report['data_class']}",
        f"**Audit status:** {report['status']}",
        "**RUL predictions:** NONE. **Model training authorized:** NO.",
        "",
        f"**Protocol SHA-256:** `{report['protocol_sha256']}`",
        "",
        f"**Trajectories:** {cohort['trajectories']}; "
        f"**observed failures:** {cohort['failure_events']}; "
        f"**right-censored:** {cohort['right_censored']}; "
        f"**total labelled follow-up:** {cohort['elapsed_source_seconds']} seconds",
        "",
        "## Blocking criteria",
        "",
    ]
    lines += [f"- {reason}" for reason in report["blocking_reasons"]] or [
        "- No metadata blockers, but independent external review remains required."
    ]
    lines += ["", "## Research cautions", ""]
    lines += [f"- {warning}" for warning in report["research_cautions"]]
    lines += [
        "",
        "## Prospective metrics (not computed)",
        "",
        "| Metric | Conditions and limitations |",
        "| --- | --- |",
    ]
    for metric in report["research_metrics_not_computed"]:
        lines.append(f"| {metric['name']} | {metric['condition']} |")
    lines += [
        "",
        "## Leakage prevention",
        "",
        report["leakage_control"],
        "",
        "## Scientific scope",
        "",
        report["scientific_limit"],
        "",
        "These timestamps are declared protocol metadata, not authenticated "
        "sensor records or evidence of real bearing/motor failure.",
        "",
    ]
    return "\n".join(lines)


def save_report(report: dict, json_path: str | Path, md_path: str | Path) -> None:
    if report.get("rul_audit_sha256") != _hash(
        {k: v for k, v in report.items() if k != "rul_audit_sha256"}
    ):
        raise ValueError("RUL audit checksum mismatch")
    jp, mp = Path(json_path), Path(md_path)
    if jp == mp or any(
        p.exists() or p.is_symlink() or not p.parent.is_dir() or p.parent.is_symlink()
        for p in (jp, mp)
    ):
        raise ValueError("RUL report needs two new paths with real existing parents")
    created = False
    try:
        write_local_manifest(jp, report)
        created = True
        _write_markdown(mp, markdown(report))
    except BaseException:
        if created:
            jp.unlink(missing_ok=True)
        raise


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Research-only metadata gate for terminal failures and censoring; no RUL estimates"
    )
    parser.add_argument(
        "--protocol",
        required=True,
        type=Path,
        help="local versioned RUL study metadata (no telemetry)",
    )
    parser.add_argument("--out-json", required=True, type=Path)
    parser.add_argument("--out-md", required=True, type=Path)
    args = parser.parse_args()
    try:
        doc = _read_strict_json(args.protocol, MAX_PROTOCOL_BYTES)
        report = audit_protocol(doc)
        save_report(report, args.out_json, args.out_md)
    except (OSError, ValueError, KeyError, TypeError, OverflowError) as exc:
        parser.error(str(exc))
    print(
        f"RUL metadata audit: {report['status']} "
        f"(no predictions; report={args.out_json})"
    )


if __name__ == "__main__":
    main()
