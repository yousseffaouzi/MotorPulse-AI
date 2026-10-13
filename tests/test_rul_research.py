"""MP-039 RUL research protocol: labels/censoring are declared, NEVER inferred."""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest

from motorpulse.rul_research import (
    PROTOCOL_VERSION, METRICS, audit_protocol, markdown, save_report,
    validate_protocol,
)
from motorpulse.splits import _hash

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "docs" / "examples" / "rul-protocol-v1.json"


def original():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def observational():
    sample = original()
    sample["data_class"] = "observed_run_to_failure"
    sample["source"]["rights_review"] = "documented_for_external_review"
    sample["source"]["failure_annotations_review"] = "documented_for_external_review"
    sample["endpoint"]["failure_evidence_kind"] = "maintenance_failure_log"
    return sample


class ResearchProtocolTests(unittest.TestCase):
    def test_fixture_is_blocked_and_never_estimates_rul(self):
        report = audit_protocol(original())
        self.assertEqual(report["rul_audit_version"], PROTOCOL_VERSION)
        self.assertEqual(report["status"], "blocked")
        self.assertFalse(report["provides_rul_estimates"])
        self.assertFalse(report["allows_rul_model_training"])
        self.assertIn("synthetic_fixture_is_not_observed_run_to_failure",
                      report["blocking_reasons"])
        self.assertIn("scripted_synthetic_events_are_not_observed_failures",
                      report["blocking_reasons"])
        self.assertEqual(report["cohort"]["failure_events"], 1)
        self.assertEqual(report["cohort"]["right_censored"], 2)
        self.assertEqual(report["cohort"]["per_split"],
                         {"train": 1, "validation": 1, "test": 1})
        self.assertEqual(report["cohort"]["elapsed_source_seconds"], 22500)
        self.assertTrue(any("sensor_loss" in text for text in report["research_cautions"]))
        self.assertEqual(report["rul_audit_sha256"],
                         _hash({k:v for k,v in report.items() if k!="rul_audit_sha256"}))

    def test_documented_observational_metadata_still_requires_external_review(self):
        report = audit_protocol(observational())
        self.assertEqual(report["status"], "metadata_complete_external_review_required")
        self.assertEqual(report["blocking_reasons"], [])
        self.assertFalse(report["allows_rul_model_training"])
        self.assertFalse(report["provides_rul_estimates"])
        self.assertIn("not independently authenticated"," ".join(report["research_cautions"]))
        self.assertIn("not computed",markdown(report).lower())

    def test_rights_and_labels_are_independently_gated(self):
        sample = observational()
        sample["source"]["rights_review"] = "unverified"
        self.assertIn("source_rights_unverified",audit_protocol(sample)["blocking_reasons"])
        sample = observational()
        sample["source"]["failure_annotations_review"] = "unverified"
        self.assertIn("failure_annotations_unverified",audit_protocol(sample)["blocking_reasons"])

    def test_no_observed_failures_blocks_inference(self):
        sample = observational()
        row = sample["trajectories"][0]
        row["status"] = "right_censored"
        row["terminal_failure_utc"] = None
        row["failure_evidence_ref"] = None
        row["censoring_reason"] = "administrative_end"
        report=audit_protocol(sample)
        self.assertIn("no_externally_observed_terminal_failure_events",
                      report["blocking_reasons"])
        self.assertEqual(report["cohort"]["right_censored"],3)

    def test_failure_time_and_evidence_required_but_not_fabricated(self):
        for changes in (
            {"terminal_failure_utc": None},
            {"failure_evidence_ref": None},
            {"terminal_failure_utc": "2025-12-31T23:59:59Z"},
            {"terminal_failure_utc": "2026-01-01T00:30:00Z"},
            {"censoring_reason": "administrative_end"},
        ):
            sample=original()
            sample["trajectories"][0].update(changes)
            with self.subTest(changes=changes),self.assertRaises(ValueError):
                validate_protocol(sample)

    def test_censored_trajectory_never_invents_event_evidence(self):
        for changes in (
            {"terminal_failure_utc": "2026-01-02T03:00:00Z"},
            {"failure_evidence_ref": "fictional-evidence"},
            {"censoring_reason": None},
            {"censoring_reason": "unknown"},
        ):
            sample=original()
            sample["trajectories"][1].update(changes)
            with self.subTest(changes=changes),self.assertRaises(ValueError):
                validate_protocol(sample)

    def test_strict_utc_and_positive_elapsed_duration(self):
        for changes in (
            {"first_observed_utc": "2026-01-02T00:00:00+01:00"},
            {"first_observed_utc": "2026-01-02T00:00:00"},
            {"last_observed_utc": "2026-01-02T00:00:00Z"},
            {"last_observed_utc": "no date"},
            {"first_observed_utc": "2026-13-02T00:00:00Z"},
        ):
            sample=original()
            sample["trajectories"][1].update(changes)
            with self.subTest(changes=changes),self.assertRaises(ValueError):
                validate_protocol(sample)

    def test_identical_trajectory_ids_rejected(self):
        sample=original()
        sample["trajectories"][1]["trajectory_id"]=sample["trajectories"][0]["trajectory_id"]
        with self.assertRaisesRegex(ValueError,"duplicate trajectory"):
            validate_protocol(sample)

    def test_cross_partition_physical_asset_leakage_rejected(self):
        sample=original()
        sample["trajectories"][1]["asset_id"]=sample["trajectories"][0]["asset_id"]
        with self.assertRaisesRegex(ValueError,"physical asset crosses"):
            validate_protocol(sample)

    def test_overlapping_trajectories_same_asset_rejected(self):
        sample=original()
        overlap=deepcopy(sample["trajectories"][0])
        overlap["trajectory_id"]="fixture-overlap"
        overlap["status"]="right_censored"
        overlap["terminal_failure_utc"]=None
        overlap["failure_evidence_ref"]=None
        overlap["censoring_reason"]="administrative_end"
        sample["trajectories"].append(overlap)
        with self.assertRaisesRegex(ValueError,"overlapping trajectories"):
            validate_protocol(sample)

    def test_partition_overlap_and_missing_source_group_rejected(self):
        sample=original()
        sample["split"]["groups"]["test"]=["fixture-run-A"]
        with self.assertRaisesRegex(ValueError,"overlap"):
            validate_protocol(sample)
        sample=original()
        sample["split"]["groups"]["test"]=["fixture-run-D"]
        with self.assertRaisesRegex(ValueError,"unlisted split group"):
            validate_protocol(sample)

    def test_unknown_version_and_extra_features_are_rejected(self):
        for mutate in (
            lambda s: s.update(rul_study_version="2.0.0"),
            lambda s: s.update(predicted_rul_seconds=5),
            lambda s: s["endpoint"].update(clock="simulated_ticks"),
            lambda s: s["split"].update(policy="window_random"),
            lambda s: s["trajectories"][0].update(remaining_useful_life=300),
            lambda s: s["source"].update(raw_data_sha256="unverified"),
        ):
            sample=original()
            mutate(sample)
            with self.subTest(mutate=mutate),self.assertRaises(ValueError):
                validate_protocol(sample)

    def test_bounded_record_count_and_trajectory_length(self):
        for count in (1,True,0,10000001):
            sample=original()
            sample["trajectories"][0]["record_count"]=count
            with self.subTest(count=count),self.assertRaises(ValueError):
                validate_protocol(sample)
        sample=original()
        sample["trajectories"]=sample["trajectories"][:2]
        with self.assertRaises(ValueError):
            validate_protocol(sample)

    def test_informative_censoring_and_metric_preregistration_flags(self):
        sample=observational()
        sample["trajectories"][1]["censoring_reason"]="competing_failure"
        sample["trajectories"][2]["censoring_reason"]="preventive_replacement"
        report=audit_protocol(sample)
        warnings=" ".join(report["research_cautions"])
        self.assertIn("competing_failure",warnings)
        self.assertIn("preventive_replacement",warnings)
        self.assertTrue(all(m["not_a_point_rul_claim"] for m in METRICS))
        self.assertTrue(any(m["name"]=="ipcw_integrated_brier" for m in METRICS))
        self.assertEqual(report["status"],"metadata_complete_external_review_required")

    def test_deterministic_markdown_and_metadata_only_output(self):
        first=audit_protocol(original())
        self.assertEqual(first,audit_protocol(original()))
        rendered=markdown(first)
        self.assertIn("model training authorized",rendered.lower())
        self.assertIn("censor",rendered.lower())
        self.assertIn("no predictions",rendered.lower())
        self.assertNotIn("predicted_rul_seconds",json.dumps(first))


class ResearchProtocolCLITests(unittest.TestCase):
    def test_json_markdown_output_write_once(self):
        with TemporaryDirectory() as temporary:
            root=Path(temporary)
            report=audit_protocol(original())
            save_report(report,root/"audit.json",root/"audit.md")
            self.assertEqual(json.loads((root/"audit.json").read_text()),report)
            with self.assertRaisesRegex(ValueError,"new paths"):
                save_report(report,root/"audit.json",root/"other.md")
            self.assertFalse((root/"other.md").exists())

    def test_checksum_guard_does_not_write_on_tampered_report(self):
        with TemporaryDirectory() as temporary:
            root=Path(temporary)
            report=audit_protocol(original())
            report["cohort"]["failure_events"]=999
            with self.assertRaisesRegex(ValueError,"checksum"):
                save_report(report,root/"bad.json",root/"bad.md")
            self.assertFalse((root/"bad.json").exists())

    def test_cli_run_and_no_overwrite(self):
        with TemporaryDirectory() as temporary:
            root=Path(temporary)
            command=[
                sys.executable,"-m","motorpulse.rul_research",
                "--protocol",str(FIXTURE),"--out-json",str(root/"audit.json"),
                "--out-md",str(root/"audit.md"),
            ]
            first=subprocess.run(command,cwd=ROOT,capture_output=True,text=True)
            self.assertEqual(first.returncode,0,first.stderr)
            self.assertIn("blocked",first.stdout)
            saved=json.loads((root/"audit.json").read_text())
            self.assertEqual(saved["status"],"blocked")
            self.assertFalse(saved["provides_rul_estimates"])
            second=subprocess.run(command,cwd=ROOT,capture_output=True,text=True)
            self.assertNotEqual(second.returncode,0)
            self.assertIn("new paths",second.stderr)


if __name__ == "__main__":
    unittest.main()
