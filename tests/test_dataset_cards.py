"""MP-032: public dataset-card templates and local source-bound run cards."""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest

from motorpulse.config_file import load_config_file
from motorpulse.dataset_cards import (
    CARD_VERSION, ims_run_card, synthetic_run_card, template_card, validate_card,
)
from motorpulse.export import export_dataset
from motorpulse.ims import inspect_ims_directory, write_local_manifest

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests/fixtures/ims_style_synthetic"


def ims_inspection():
    return inspect_ims_directory(
        FIXTURE, test_set="2", sample_rate_hz=8,
        expected_samples=4, expected_channels=4,
    )


class DatasetCardTemplateTests(unittest.TestCase):
    def test_two_versioned_templates_are_valid_and_packaged(self):
        for name, filename in (("synthetic", "synthetic-v1.json"),
                               ("ims", "ims-v1.json")):
            with self.subTest(name=name):
                path = ROOT / "motorpulse/cards" / filename
                template = json.loads(path.read_text(encoding="utf-8"))
                self.assertEqual(template, template_card(name))
                self.assertEqual(template["card_version"], CARD_VERSION)
                self.assertEqual(template["instance_kind"], "template")
                self.assertIsNone(template["run_provenance"])
                validate_card(template)
                self.assertGreaterEqual(len(template["known_limitations"]), 3)
                self.assertGreaterEqual(len(template["excluded_uses"]), 2)

    def test_static_synthetic_card_separates_truth_rules_and_license(self):
        card = template_card("synthetic")
        self.assertEqual(card["dataset_type"], "synthetic_motor_feature_events")
        self.assertEqual(card["collection"]["sample_rate_hz"], 1024)
        self.assertEqual(card["collection"]["sample_count"], 1024)
        self.assertIn("controlled synthetic scenario", card["labels"]["motor_fault"])
        self.assertIn("rule-based", card["labels"]["health"])
        self.assertIsNone(card["labels"]["failure_probability"])
        self.assertIsNone(card["labels"]["remaining_useful_life"])
        self.assertEqual(card["license"]["code_license"], "MIT")
        self.assertIsNone(card["license"]["dataset_specific_license"])
        self.assertEqual(card["publication_status"], "synthetic_demo")

    def test_ims_template_defers_license_rate_and_window_labels(self):
        card = template_card("ims")
        self.assertEqual(card["license"]["license_status"], "other-license-specified")
        self.assertIsNone(card["license"]["dataset_specific_license"])
        self.assertIsNone(card["collection"]["sample_rate_hz"])
        self.assertIsNone(card["collection"]["sample_count"])
        self.assertIsNone(card["labels"]["window_fault_onset"])
        self.assertEqual(card["rights_review"]["status"], "hold")
        self.assertFalse(card["rights_review"]["derived_publication_cleared"])
        self.assertEqual(card["publication_status"], "local_only_do_not_redistribute")
        self.assertIn("University of Cincinnati", card["creator_or_provider"])

    def test_reject_misleading_templates_and_labels(self):
        base = template_card("ims")
        trials = [
            lambda x: x["labels"].update({"remaining_useful_life":42}),
            lambda x: x["labels"].update({"motor_fault":"healthy"}),
            lambda x: x["rights_review"].update({"status":"cleared"}),
            lambda x: x["rights_review"].update({"derived_publication_cleared":True}),
            lambda x: x["collection"].update({"sample_rate_hz":20000}),
            lambda x: x["license"].update({"dataset_specific_license":"CC0"}),
            lambda x: x.update({"publication_status":"public"}),
            lambda x: x.update({"run_provenance":{"run_id":"ims-set-1"}}),
            lambda x: x.update({"unexpected":"field"}),
        ]
        for mutation in trials:
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                altered = deepcopy(base)
                mutation(altered)
                validate_card(altered)

    def test_synthetic_template_rejects_trained_claims_and_bad_types(self):
        base=template_card("synthetic")
        for key,value in (("failure_probability",.9),("remaining_useful_life",100)):
            with self.subTest(key=key),self.assertRaises(ValueError):
                card=deepcopy(base);card["labels"][key]=value;validate_card(card)
        card=deepcopy(base);card["instance_kind"]="run"
        with self.assertRaises(ValueError):
            validate_card(card)
        card=deepcopy(base);card["intended_uses"]=[]
        with self.assertRaises(ValueError):
            validate_card(card)


class SyntheticRunCardTests(unittest.TestCase):
    def test_card_provenance_matches_export_manifests(self):
        with TemporaryDirectory() as tmp:
            folder = Path(tmp)/"sim"
            manifest=export_dataset(folder,ticks=5,seed=71,file_format="both")
            card=synthetic_run_card(folder)
            self.assertEqual(card["instance_kind"],"run")
            self.assertEqual(card["run_provenance"]["export_id"],manifest["export_id"])
            self.assertEqual(card["run_provenance"]["model_source_sha256"],manifest["model_source_sha256"])
            self.assertEqual(card["run_provenance"]["config_sha256"],manifest["config_sha256"])
            self.assertEqual(card["run_provenance"]["events_jsonl_sha256"],
                             manifest["files"]["events.jsonl"]["sha256"])
            self.assertEqual(card["run_provenance"]["source_file_hashes"],
                             {k:v["sha256"] for k,v in manifest["files"].items()})
            self.assertEqual(card["run_provenance"]["seed"],71)
            self.assertEqual(card["run_provenance"]["events"],15)
            self.assertEqual(card["run_provenance"]["assets"],3)
            self.assertIsNone(card["run_provenance"]["generated_at_utc"])
            self.assertIn("sim-",card["card_id"])
            validate_card(card)

    def test_same_seed_and_config_yield_identical_card(self):
        with TemporaryDirectory() as tmp:
            export_dataset(Path(tmp)/"first",ticks=3,seed=9)
            export_dataset(Path(tmp)/"second",ticks=3,seed=9)
            a=synthetic_run_card(Path(tmp)/"first")
            b=synthetic_run_card(Path(tmp)/"second")
            self.assertEqual(a,b)
            self.assertEqual(json.dumps(a,sort_keys=True),json.dumps(b,sort_keys=True))

    def test_scenario_fault_and_sensor_quality_remain_distinct(self):
        with TemporaryDirectory() as tmp:
            assets=load_config_file(ROOT/"docs/examples/operations-v1.json")
            folder=Path(tmp)/"events"
            export_dataset(folder,ticks=6,assets=assets)
            card=synthetic_run_card(folder)
            self.assertIn("motor_fault",card["labels"])
            self.assertIn("sensor_quality",card["labels"])
            self.assertIsNone(card["labels"]["remaining_useful_life"])
            self.assertEqual(card["run_provenance"]["sample_rate_hz"],1024)

    def test_tampered_config_digest_rejected(self):
        with TemporaryDirectory() as tmp:
            folder=Path(tmp)/"sim"
            export_dataset(folder,ticks=2)
            path=folder/"manifest.json"
            data=json.loads(path.read_text(encoding="utf-8"))
            data["config_sha256"]="0"*64
            path.write_text(json.dumps(data),encoding="utf-8")
            with self.assertRaisesRegex(ValueError,"configuration SHA-256 mismatch"):
                synthetic_run_card(folder)

    def test_csv_only_or_corrupt_event_bytes_rejected(self):
        with TemporaryDirectory() as tmp:
            folder=Path(tmp)/"csv"
            export_dataset(folder,ticks=1,file_format="csv")
            with self.assertRaisesRegex(ValueError,"events.jsonl"):
                synthetic_run_card(folder)
            good=Path(tmp)/"both"
            export_dataset(good,ticks=1,file_format="both")
            with (good/"events.jsonl").open("ab") as fp:
                fp.write(b"corrupt")
            with self.assertRaisesRegex(ValueError,"integrity check"):
                synthetic_run_card(good)


class IMSRunCardTests(unittest.TestCase):
    def test_ims_metadata_is_local_only_without_derived_samples(self):
        with TemporaryDirectory() as tmp:
            path=Path(tmp)/"inspection.json"
            source=ims_inspection()
            write_local_manifest(path,source)
            card=ims_run_card(path)
            p=card["run_provenance"]
            self.assertEqual(card["publication_status"],"local_only_do_not_redistribute")
            self.assertEqual(p["source_card_id"],"nasa-pcoe-ims-bearings")
            self.assertEqual(p["run_id"],"ims-set-2")
            self.assertEqual(p["snapshot_count"],2)
            self.assertEqual(p["channel_record_count"],8)
            self.assertEqual(p["sample_rate_hz_declared_by_user"],8)
            self.assertEqual(p["value_unit_declared_by_user"],"unknown")
            self.assertEqual(p["timestamp_timezone"],"unknown")
            self.assertIsNone(p["window_fault_label"])
            self.assertIsNone(p["fault_onset_time"])
            self.assertIsNone(p["rul_seconds"])
            self.assertIsNone(p["original_archive_sha256_user_supplied"])
            self.assertFalse(p["file_hashes_rechecked"])
            self.assertFalse(p["source_archive_inspected_by_project"])
            self.assertIn("unit_unverified",p["quality_flag_counts"])
            serialized=json.dumps(card)
            self.assertNotIn(source["input_directory"],serialized)
            self.assertNotIn("rms_native",serialized)
            self.assertNotIn("2004.02.12.10.32.39",serialized)
            validate_card(card)

    def test_optional_actual_local_hash_reverification(self):
        with TemporaryDirectory() as tmp:
            path=Path(tmp)/"inspection.json"
            write_local_manifest(path,ims_inspection())
            noverify=ims_run_card(path,verify_files=False)
            verify=ims_run_card(path,verify_files=True)
            self.assertFalse(noverify["run_provenance"]["file_hashes_rechecked"])
            self.assertTrue(verify["run_provenance"]["file_hashes_rechecked"])
            self.assertEqual(noverify["run_provenance"]["inspection_report_sha256"],
                             verify["run_provenance"]["inspection_report_sha256"])

    def test_cannot_invent_ims_onset_or_publication_clearance(self):
        with TemporaryDirectory() as tmp:
            path=Path(tmp)/"report.json"
            data=ims_inspection()
            data["ground_truth"]["fault_onset_time"]="2004-02-12T10:32:39"
            write_local_manifest(path,data)
            with self.assertRaisesRegex(ValueError,"must not invent"):
                ims_run_card(path)
        card=template_card("ims")
        card["rights_review"]["derived_publication_cleared"]=True
        with self.assertRaises(ValueError):
            validate_card(card)


class CardCLIAndDocsTests(unittest.TestCase):
    def test_cli_synthetic_and_ims_write_once(self):
        with TemporaryDirectory() as tmp:
            root=Path(tmp)
            out=root/"export"
            export_dataset(out,ticks=2)
            report_path=root/"ims-report.json"
            write_local_manifest(report_path,ims_inspection())
            env=dict(os.environ);env["PYTHONPATH"]=str(ROOT)
            for source,input_path,filename in (
                ("synthetic",out,"synthetic-card.json"),
                ("ims",report_path,"ims-card.json"),
            ):
                with self.subTest(source=source):
                    args=[sys.executable,"-m","motorpulse.dataset_cards",
                          "--source",source,"--input",str(input_path),
                          "--out",str(root/filename)]
                    run=subprocess.run(args,cwd=root,env=env,
                                       text=True,capture_output=True,timeout=30)
                    self.assertEqual(run.returncode,0,run.stderr)
                    card=json.loads((root/filename).read_text(encoding="utf-8"))
                    validate_card(card)
                    again=subprocess.run(args,cwd=root,env=env,
                                         text=True,capture_output=True,timeout=30)
                    self.assertEqual(again.returncode,2)
                    self.assertIn("error:",again.stderr)

    def test_cli_no_ims_flags_on_synthetic_and_no_partial_file(self):
        with TemporaryDirectory() as tmp:
            root=Path(tmp)
            export_dataset(root/"export",ticks=1)
            result=subprocess.run([sys.executable,"-m","motorpulse.dataset_cards",
                                   "--source","synthetic","--input",str(root/"export"),
                                   "--verify-files","--out",str(root/"not-created.json")],
                                  cwd=root,env={**os.environ,"PYTHONPATH":str(ROOT)},
                                  text=True,capture_output=True,timeout=30)
            self.assertEqual(result.returncode,2)
            self.assertFalse((root/"not-created.json").exists())

    def test_dataset_docs_link_templates_and_prior_milestones(self):
        guide=(ROOT/"docs/DATASET_CARDS.md").read_text(encoding="utf-8")
        readme=(ROOT/"README.md").read_text(encoding="utf-8")
        todo=(ROOT/"TODO.md").read_text(encoding="utf-8")
        for name in ("synthetic-v1.json","ims-v1.json","MP-008","MP-027",
                     "MP-028","MP-029","MP-030","data leakage"):
            with self.subTest(name=name):
                self.assertIn(name.lower(),guide.lower())
        self.assertIn("docs/DATASET_CARDS.md",readme)
        self.assertIn("| MP-032 | DONE |",todo)
        self.assertIn("redistribution",guide.lower())


if __name__ == "__main__":
    unittest.main()
