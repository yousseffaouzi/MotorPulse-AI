"""MP-010 healthy-trained anomaly baseline: run/label leakage protections."""
from __future__ import annotations

from copy import deepcopy
import json
from math import isfinite
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from motorpulse.anomaly import (
    FEATURES, _score, _vector, score_partition, train_baseline,
)
from motorpulse.export import export_dataset
from motorpulse.scenarios import AssetScenario
from motorpulse.splits import group_split, _hash

ROOT = Path(__file__).resolve().parents[1]


def runs(root, seeds=(11, 22, 33), ticks=12, *, assets=None):
    paths = []
    for seed in seeds:
        folder = root / f"run-{seed}"
        kwargs = {"ticks":ticks, "seed":seed, "file_format":"jsonl"}
        if assets is not None:
            kwargs["assets"] = assets
        export_dataset(folder, **kwargs)
        paths.append(folder / "manifest.json")
    plan = group_split(paths, source_type="synthetic", seed=42)
    return plan, paths


class TrainBaselineTests(unittest.TestCase):
    def test_train_only_healthy_good_sensor_and_provenance(self):
        with TemporaryDirectory() as tmp:
            plan, paths = runs(Path(tmp))
            model = train_baseline(plan, paths)
            self.assertEqual(model["model_version"], "1.0.0")
            self.assertEqual(model["method"], "healthy_training_zscore_euclidean")
            self.assertFalse(model["score_is_failure_probability"])
            self.assertIsNone(model["remaining_useful_life"])
            self.assertEqual(model["training"]["fit_partitions"], ["train"])
            self.assertEqual(model["training"]["groups"],
                             sorted(plan["partitions"]["train"]["group_ids"]))
            self.assertEqual(model["training"]["healthy_good_sensor_events"], 12)
            self.assertEqual(model["training"]["excluded_training_events"]
                             ["nonhealthy_synthetic_truth"], 24)
            self.assertEqual(model["feature_contract"]["names"], list(FEATURES))
            self.assertEqual(len(model["center"]), 5)
            self.assertTrue(all(v > 0 for v in model["effective_scales"]))
            self.assertTrue(all(isfinite(v) for v in model["center"]))
            self.assertEqual(model["calibration"]["partition"], "train")
            self.assertEqual(model["calibration"]["quantile"], .99)
            self.assertEqual(model["training"]["split_plan_sha256"],
                             plan["plan_sha256"])
            self.assertEqual(len(model["training"]["dataset_cards"]), 1)
            self.assertEqual(model["model_sha256"],
                             _hash({k:v for k,v in model.items() if k != "model_sha256"}))

    def test_replay_and_source_input_order_do_not_change_model(self):
        with TemporaryDirectory() as tmp:
            plan, paths = runs(Path(tmp), seeds=(11,22,33,44,55))
            a = train_baseline(plan, paths)
            b = train_baseline(plan, list(reversed(paths)))
            self.assertEqual(a,b)
            self.assertEqual(a["model_sha256"],b["model_sha256"])

    def test_only_training_events_consumed_for_fit(self):
        from motorpulse import anomaly
        with TemporaryDirectory() as tmp:
            plan, paths = runs(Path(tmp))
            touched = []
            original = anomaly._events
            def audited(source):
                touched.append(source["group_id"])
                return original(source)
            with patch("motorpulse.anomaly._events", side_effect=audited):
                train_baseline(plan, paths)
            self.assertEqual(touched, sorted(plan["partitions"]["train"]["group_ids"]))
            self.assertNotIn(plan["partitions"]["test"]["group_ids"][0],touched)
            self.assertNotIn(plan["partitions"]["validation"]["group_ids"][0],touched)

    def test_input_features_exclude_label_rule_and_identity(self):
        values = dict(rms_g=.25, crest_factor=2.5, band_80_400_rms_g=.1,
                      temperature_c=55, rpm=1500)
        first = {**values, "scenario":"healthy", "health":"normal",
                 "severity":0, "asset_id":"MTR-01", "sensor_quality":"good"}
        adversarial = {**first, "scenario":"bearing_wear","severity":1,
                       "health":"critical","asset_id":"ANY","sensor_quality":"outlier",
                       "timestamp_utc":"2030-01-01","fault_phase":"critical"}
        self.assertEqual(_vector(first),_vector(adversarial))
        for bad in (None, "not numeric", float("nan"),float("inf"),-1,True):
            with self.subTest(value=bad), self.assertRaises(ValueError):
                _vector({**first,"rms_g":bad})

    def test_no_healthy_training_samples_refused(self):
        with TemporaryDirectory() as tmp:
            assets=(AssetScenario("MTR-XX","Only fault",scenario="imbalance",severity=.8),)
            plan,paths=runs(Path(tmp),assets=assets)
            with self.assertRaisesRegex(ValueError,"at least 8 healthy"):
                train_baseline(plan,paths)

    def test_insufficient_good_samples_refused(self):
        with TemporaryDirectory() as tmp:
            assets=(AssetScenario("MTR-XX","Mostly absent",scenario="healthy",
                    sensor_missing_onset_tick=1,sensor_missing_duration_ticks=9),)
            plan,paths=runs(Path(tmp),ticks=12,assets=assets)
            with self.assertRaisesRegex(ValueError,"at least 8 healthy"):
                train_baseline(plan,paths)

    def test_bad_plan_checksum_rejected(self):
        with TemporaryDirectory() as tmp:
            plan,paths=runs(Path(tmp))
            malicious=deepcopy(plan)
            malicious["partitions"]["train"]["group_ids"] = malicious["partitions"]["test"]["group_ids"]
            with self.assertRaisesRegex(ValueError,"checksum"):
                train_baseline(malicious,paths)

    def test_forged_checksum_but_partition_overlap_rejected(self):
        with TemporaryDirectory() as tmp:
            plan,paths=runs(Path(tmp))
            tampered=deepcopy(plan)
            tampered["partitions"]["test"]["group_ids"]=tampered["partitions"]["train"]["group_ids"]
            tampered["plan_sha256"]=_hash({k:v for k,v in tampered.items() if k!="plan_sha256"})
            with self.assertRaisesRegex(ValueError,"overlapping"):
                train_baseline(tampered,paths)

    def test_missing_or_duplicate_manifests_rejected(self):
        with TemporaryDirectory() as tmp:
            plan,paths=runs(Path(tmp))
            with self.assertRaisesRegex(ValueError,"3-100"):
                train_baseline(plan,paths[:2])
            with self.assertRaisesRegex(ValueError,"supplied source identity"):
                train_baseline(plan,[paths[0],paths[0],paths[2]])

    def test_dataset_changed_after_split_is_rejected(self):
        with TemporaryDirectory() as tmp:
            plan,paths=runs(Path(tmp))
            p=paths[0].parent/"events.jsonl"
            p.write_bytes(p.read_bytes()+b"corrupt")
            with self.assertRaisesRegex(ValueError,"integrity check"):
                train_baseline(plan,paths)

    def test_chronological_and_ims_plans_rejected_for_training(self):
        from motorpulse.splits import chronological_split
        with TemporaryDirectory() as tmp:
            plan,paths=runs(Path(tmp))
            chrono=chronological_split(paths[0])
            with self.assertRaisesRegex(ValueError,"whole-run synthetic"):
                train_baseline(chrono,paths)
            invalid=deepcopy(plan)
            invalid["source_type"]="user_supplied_local_ims_style"
            with self.assertRaisesRegex(ValueError,"whole-run synthetic"):
                train_baseline(invalid,paths)


class ScoreBaselineTests(unittest.TestCase):
    def test_validation_test_scoring_preserves_training_model(self):
        with TemporaryDirectory() as tmp:
            plan,paths=runs(Path(tmp))
            model=train_baseline(plan,paths)
            before=json.dumps(model,sort_keys=True)
            val=score_partition(plan,paths,model,partition="validation")
            test=score_partition(plan,paths,model,partition="test")
            self.assertEqual(json.dumps(model,sort_keys=True),before)
            for report,kind in ((val,"validation"),(test,"test")):
                self.assertEqual(report["partition"],kind)
                self.assertEqual(report["total_events"],36)
                self.assertEqual(report["model_sha256"],model["model_sha256"])
                self.assertEqual(report["displayed_events"],30)
                self.assertTrue(all(event["anomaly_score"] is None or
                                    event["anomaly_score"] >= 0 for event in report["events_sample"]))
                self.assertNotIn("scenario",json.dumps(report))
                self.assertIn("rule_based_health",report["events_sample"][0])
                self.assertIn("not failure probability",report["events_sample"][0]["note"])

    def test_quality_missing_and_outlier_are_unscorable(self):
        with TemporaryDirectory() as tmp:
            assets=(
                AssetScenario("MTR-AA","Healthy",scenario="healthy"),
                AssetScenario("MTR-BB","Missing",scenario="healthy",
                    sensor_missing_onset_tick=3,sensor_missing_duration_ticks=4),
                AssetScenario("MTR-CC","Outlier",scenario="healthy",
                    sensor_outlier_onset_tick=4,sensor_outlier_duration_ticks=2,
                    sensor_outlier_g=.8),
            )
            plan,paths=runs(Path(tmp),ticks=15,assets=assets)
            model=train_baseline(plan,paths)
            scored=score_partition(plan,paths,model,partition="test",max_events=45)
            self.assertEqual(scored["counts_unscorable"]["missing_sensor"],4)
            self.assertEqual(scored["counts_unscorable"]["sensor_outlier"],2)
            unscorable=[ev for ev in scored["events_sample"] if ev["decision"]=="unscorable"]
            self.assertEqual(len(unscorable),6)
            self.assertTrue(all(x["anomaly_score"] is None for x in unscorable))

    def test_threshold_strictly_greater(self):
        features=(1.,2.,3.,4.,5.)
        self.assertAlmostEqual(_score(features,list(features),[1.]*5),0)
        self.assertAlmostEqual(_score((2.,2.,3.,4.,5.),list(features),[1.]*5),
                               (1/5)**.5)

    def test_invalid_partition_model_checksum_and_limits(self):
        with TemporaryDirectory() as tmp:
            plan,paths=runs(Path(tmp))
            model=train_baseline(plan,paths)
            with self.assertRaises(ValueError):
                score_partition(plan,paths,model,partition="bogus")
            for limit in (0,-1,True,12001):
                with self.subTest(limit=limit),self.assertRaises(ValueError):
                    score_partition(plan,paths,model,partition="test",max_events=limit)
            changed=deepcopy(model)
            changed["center"][0]+=1
            with self.assertRaisesRegex(ValueError,"checksum"):
                score_partition(plan,paths,changed,partition="test")

    def test_preview_limit_and_order_reproducible(self):
        with TemporaryDirectory() as tmp:
            plan,paths=runs(Path(tmp))
            model=train_baseline(plan,paths)
            a=score_partition(plan,paths,model,partition="test",max_events=2)
            b=score_partition(plan,list(reversed(paths)),model,
                              partition="test",max_events=2)
            self.assertEqual(a,b)
            self.assertEqual(a["displayed_events"],2)
            self.assertEqual(a["total_events"],36)


class BaselineCLIAndDocsTests(unittest.TestCase):
    def test_cli_write_once_and_reproducible_json(self):
        with TemporaryDirectory() as tmp:
            root=Path(tmp)
            plan,paths=runs(root)
            split=root/"plan.json"
            split.write_text(json.dumps(plan),encoding="utf-8")
            dest=root/"baseline.json"
            args=[sys.executable,"-m","motorpulse.anomaly",
                  "--split",str(split),"--input",*(str(p) for p in paths),
                  "--out",str(dest),"--preview","test"]
            env={**os.environ,"PYTHONPATH":str(ROOT)}
            proc=subprocess.run(args,cwd=root,env=env,text=True,capture_output=True,timeout=45)
            self.assertEqual(proc.returncode,0,proc.stderr)
            result=json.loads(dest.read_text(encoding="utf-8"))
            self.assertEqual(result["preview"]["partition"],"test")
            self.assertEqual(result["model"]["training"]["healthy_good_sensor_events"],12)
            proc2=subprocess.run(args,cwd=root,env=env,text=True,capture_output=True,timeout=45)
            self.assertEqual(proc2.returncode,2)
            self.assertIn("error:",proc2.stderr)

    def test_cli_rejects_missing_paths_without_outputs(self):
        with TemporaryDirectory() as tmp:
            root=Path(tmp)
            output=root/"should-not-exist.json"
            proc=subprocess.run([sys.executable,"-m","motorpulse.anomaly",
                "--split",str(root/"missing.json"),"--input",str(root/"missing-manifest"),
                "--out",str(output)],cwd=root,env={**os.environ,"PYTHONPATH":str(ROOT)},
                text=True,capture_output=True,timeout=20)
            self.assertEqual(proc.returncode,2)
            self.assertFalse(output.exists())

    def test_docs_and_package_command(self):
        guide=(ROOT/"docs/ANOMALY_BASELINE.md").read_text(encoding="utf-8")
        todo=(ROOT/"TODO.md").read_text(encoding="utf-8")
        readme=(ROOT/"README.md").read_text(encoding="utf-8")
        for word in ("MP-030","MP-032","healthy", "99th", "training",
                     "null", "failure probability","data leakage"):
            with self.subTest(word=word):
                self.assertIn(word.lower(),guide.lower())
        self.assertIn("| MP-010 | DONE |",todo)
        self.assertIn("docs/ANOMALY_BASELINE.md",readme)


if __name__ == "__main__":
    unittest.main()
