"""MP-011: fully held-out synthetic detection evaluation and edge cases."""
from __future__ import annotations

from copy import deepcopy
import json
import math
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from motorpulse.anomaly import train_baseline
from motorpulse.evaluation import (
    _episodes, _truth, average_precision, confusion, evaluate, markdown,
)
from motorpulse.export import export_dataset
from motorpulse.scenarios import AssetScenario
from motorpulse.splits import group_split, _hash

ROOT = Path(__file__).resolve().parents[1]


def small_rows(truth, scores, alerts=None):
    if alerts is None:
        alerts = [score >= .5 for score in scores]
    return [dict(positive=bool(t), score=float(s), anomaly_alert=bool(a),
                 rule_alert=False)
            for t,s,a in zip(truth,scores,alerts)]


def runs(root, seeds=(11, 22, 33), ticks=16, *, assets=None, step=1.5):
    paths = []
    for seed in seeds:
        folder = root / f"run-{seed}"
        kwargs = dict(ticks=ticks,seed=seed,file_format="jsonl",step_seconds=step)
        if assets is not None:
            kwargs["assets"]=assets
        export_dataset(folder,**kwargs)
        paths.append(folder/"manifest.json")
    return group_split(paths,source_type="synthetic",seed=42),paths


def eval_model(root, *, assets=None, ticks=16, step=1.5):
    plan,paths=runs(root,assets=assets,ticks=ticks,step=step)
    model=train_baseline(plan,paths)
    return plan,paths,model


class ConfusionMetricTests(unittest.TestCase):
    def test_confusion_matrix_precision_recall_specificity_and_f1(self):
        rows=small_rows([1,1,0,0],[.9,.1,.8,.2])
        result=confusion(rows,decision="anomaly_alert",step_seconds=1.5,with_ap=True)
        self.assertEqual([result[k] for k in ("tp","fp","tn","fn")],[1,1,1,1])
        self.assertEqual(result["n"],4)
        self.assertEqual(result["precision"],.5)
        self.assertEqual(result["recall"],.5)
        self.assertEqual(result["false_positive_rate"],.5)
        self.assertEqual(result["specificity"],.5)
        self.assertEqual(result["f1"],.5)
        self.assertEqual(result["false_alarms_per_simulated_negative_hour"],1200)
        self.assertAlmostEqual(result["average_precision"],.75)

    def test_ap_uses_rank_order_and_groups_exact_ties(self):
        rows=small_rows([1,0,1,0],[.9,.9,.3,.1])
        self.assertAlmostEqual(average_precision(rows),(.5*.5)+(.5*2/3))
        self.assertAlmostEqual(average_precision(list(reversed(rows))),(.5*.5)+(.5*2/3))
        perfect=small_rows([1,1,0,0],[.9,.8,.2,.1])
        self.assertAlmostEqual(average_precision(perfect),1)
        inverted=small_rows([1,1,0,0],[.2,.1,.9,.8])
        self.assertAlmostEqual(average_precision(inverted),(.5/3)+(.5/2))

    def test_undefined_denominators_are_explicit_null(self):
        only_neg=small_rows([0,0],[.1,.9])
        neg=confusion(only_neg,decision="anomaly_alert",step_seconds=2,with_ap=True)
        self.assertIsNone(neg["recall"])
        self.assertIsNone(neg["average_precision"])
        self.assertIsNotNone(neg["false_positive_rate"])
        self.assertEqual(neg["f1"],0)  # an alert on a healthy window means FP
        only_pos=small_rows([1,1],[.1,.9])
        pos=confusion(only_pos,decision="anomaly_alert",step_seconds=2,with_ap=True)
        self.assertIsNone(pos["specificity"])
        self.assertIsNone(pos["false_positive_rate"])
        self.assertIsNone(pos["false_alarms_per_simulated_negative_hour"])
        self.assertIsNone(pos["average_precision"])
        empty=confusion([],decision="anomaly_alert",with_ap=True)
        for key in ("precision","recall","f1","average_precision","specificity"):
            self.assertIsNone(empty[key])

    def test_zero_false_alarm_and_zero_predicted_positive(self):
        neg=confusion(small_rows([0,0,0],[.1,.2,.3]),
                      decision="anomaly_alert",step_seconds=2)
        self.assertEqual(neg["fp"],0)
        self.assertEqual(neg["false_alarms_per_simulated_negative_hour"],0)
        self.assertIsNone(neg["precision"])
        self.assertIsNone(neg["f1"])
        self.assertEqual(neg["specificity"],1)

    def test_confusion_bad_types_or_step_refused(self):
        rows=small_rows([1],[.8])
        for val in (0,True,float("nan"),-3):
            with self.subTest(val=val),self.assertRaises(ValueError):
                confusion(rows,decision="anomaly_alert",step_seconds=val)
        with self.assertRaises(ValueError):
            confusion([{"positive":1,"anomaly_alert":True}],decision="anomaly_alert")
        with self.assertRaises(ValueError):
            confusion(rows,decision="bogus")

    def test_truth_uses_effective_not_future_fault(self):
        self.assertEqual(_truth({"scenario":"healthy","fault_phase":"scheduled"}),(False,"healthy"))
        self.assertEqual(_truth({"scenario":"healthy","fault_phase":"ramping"}),(False,"healthy"))
        self.assertEqual(_truth({"scenario":"bearing_wear","fault_phase":"ramping"}),(True,"bearing_wear"))
        self.assertEqual(_truth({"scenario":"healthy","fault_phase":"ended"}),(False,"healthy"))
        for event in ({"scenario":"unknown","fault_phase":"steady"},
                      {"scenario":"imbalance","fault_phase":"scheduled"},
                      {"scenario":"healthy","fault_phase":"unsupported"}):
            with self.subTest(event=event),self.assertRaises(ValueError):
                _truth(event)


def timeline(positives, alerts, qualities=None, *, fault="bearing_wear"):
    qualities=qualities or ["good"]*len(positives)
    return [dict(tick=i+1,asset_id="MTR-XY",
                 timestamp_utc=f"2026-01-01T00:00:{i:02d}+00:00",
                 scenario=fault if pos else "healthy",positive=bool(pos),
                 eligible=qualities[i]=="good",anomaly_alert=bool(alerts[i]),
                 rule_alert=False,score=float(alerts[i]) if qualities[i]=="good" else None)
            for i,pos in enumerate(positives)]


class EpisodeTests(unittest.TestCase):
    def test_episode_onset_first_positive_not_configured_future(self):
        rows=timeline([0,0,1,1,1,0,1,1,0],
                      [0,1,0,0,1,0,0,1,0])
        episode=_episodes(rows,1.5)
        self.assertEqual(episode["episodes"],2)
        self.assertEqual(episode["detected"],2)
        self.assertEqual(episode["missed"],0)
        self.assertEqual([x["onset_tick"] for x in episode["details"]],[3,7])
        self.assertEqual([x["first_alert_tick"] for x in episode["details"]],[5,8])
        self.assertEqual([x["delay_seconds"] for x in episode["details"]],[3,1.5])
        self.assertEqual(episode["mean_delay_seconds"],2.25)
        self.assertEqual(episode["median_delay_seconds"],2.25)

    def test_missed_and_all_abstained_episodes(self):
        rows=timeline([0,1,1,0,1,1,0],[0]*7,
                      ["good","missing","outlier","good","good","good","good"])
        report=_episodes(rows,2)
        self.assertEqual(report["episodes"],2)
        self.assertEqual(report["missed"],2)
        self.assertEqual(report["abstained_only"],1)
        self.assertIsNone(report["mean_delay_seconds"])
        self.assertIsNone(report["median_delay_seconds"])
        self.assertTrue(report["details"][0]["no_eligible_fault_windows"])
        self.assertIsNone(report["details"][0]["delay_seconds"])

    def test_abstention_does_not_shorten_positive_truth_episode(self):
        rows=timeline([0,1,1,1,0],[0,0,0,1,0],
                      ["good","missing","missing","good","good"])
        report=_episodes(rows,3)
        self.assertEqual(report["episodes"],1)
        self.assertEqual(report["details"][0]["onset_tick"],2)
        self.assertEqual(report["details"][0]["first_alert_tick"],4)
        self.assertEqual(report["details"][0]["abstentions"],2)
        self.assertEqual(report["details"][0]["delay_seconds"],6)


class HeldoutIntegrationTests(unittest.TestCase):
    def test_full_evaluation_provenance_and_frozen_training(self):
        with TemporaryDirectory() as tmp:
            plan,paths,model=eval_model(Path(tmp))
            before=json.dumps(model,sort_keys=True)
            report=evaluate(plan,paths,model,partition="test",max_events=3)
            self.assertEqual(json.dumps(model,sort_keys=True),before)
            self.assertEqual(report,evaluate(plan,list(reversed(paths)),model,
                                             partition="test",max_events=3))
            self.assertEqual(report["comparison_cohort"]["total_windows"],48)
            self.assertEqual(report["comparison_cohort"]["eligible_both_methods"],48)
            self.assertEqual(report["partition"],"test")
            self.assertEqual(report["trained_model_sha256"],model["model_sha256"])
            self.assertEqual(report["split_plan_sha256"],plan["plan_sha256"])
            self.assertEqual(report["training_groups"],model["training"]["groups"])
            self.assertEqual(report["evaluated_groups"],plan["partitions"]["test"]["group_ids"])
            self.assertEqual(len(report["source_provenance"]),1)
            self.assertEqual(report["overall"]["model"]["n"],48)
            self.assertEqual(report["overall"]["rules"]["n"],48)
            self.assertEqual(len(report["sample_events"]),3)
            self.assertEqual(report["evaluation_sha256"],
                             _hash({k:v for k,v in report.items() if k!="evaluation_sha256"}))
            self.assertIn("scripted",report["label_note"])

    def test_fair_rule_and_model_eligible_denominator(self):
        assets=(
            AssetScenario("MTR-AA","Healthy",scenario="healthy"),
            AssetScenario("MTR-BB","Transient",scenario="bearing_wear",severity=.7,
                          onset_tick=3, duration_ticks=7,
                          sensor_missing_onset_tick=4,sensor_missing_duration_ticks=2),
            AssetScenario("MTR-CC","Outlier",scenario="healthy",
                          sensor_outlier_onset_tick=5,sensor_outlier_duration_ticks=1,
                          sensor_outlier_g=1.2),
        )
        with TemporaryDirectory() as tmp:
            plan,paths,model=eval_model(Path(tmp),assets=assets,ticks=16)
            rep=evaluate(plan,paths,model)
            cohort=rep["comparison_cohort"]
            self.assertEqual(cohort["total_windows"],48)
            self.assertEqual(cohort["eligible_both_methods"],45)
            self.assertEqual(cohort["abstentions"],{"missing":2,"outlier":1})
            self.assertEqual(rep["overall"]["model"]["n"],45)
            self.assertEqual(rep["overall"]["rules"]["n"],45)
            self.assertEqual(rep["overall"]["model"]["positive_windows"],
                             rep["overall"]["rules"]["positive_windows"])
            self.assertEqual(rep["overall"]["model"]["negative_windows"],
                             rep["overall"]["rules"]["negative_windows"])
            self.assertEqual(rep["detection_episodes"]["total"],1)
            self.assertEqual(rep["detection_episodes"]["details"][0]["onset_tick"],3)
            self.assertIn("bearing_wear",rep["by_fault_type_positive_only"])

    def test_no_positives_metrics_undefined(self):
        assets=(AssetScenario("MTR-AA","Healthy",scenario="healthy"),)
        with TemporaryDirectory() as tmp:
            plan,paths,model=eval_model(Path(tmp),assets=assets,ticks=14)
            rep=evaluate(plan,paths,model)
            self.assertEqual(rep["overall"]["model"]["positive_windows"],0)
            self.assertIsNone(rep["overall"]["model"]["recall"])
            self.assertIsNone(rep["overall"]["model"]["average_precision"])
            self.assertEqual(rep["detection_episodes"]["total"],0)
            self.assertIsNone(rep["detection_episodes"]["mean_delay_seconds"])
            self.assertEqual(rep["by_fault_type_positive_only"],{})

    def test_no_negatives_metrics_undefined_on_test(self):
        # Training run keeps healthy rows, but test's programmed scenarios
        # remain positive for every event. This tests the reporting helper.
        rows=small_rows([1,1,1],[.1,.5,.9])
        metric=confusion(rows,decision="anomaly_alert",step_seconds=1.5,with_ap=True)
        self.assertIsNone(metric["false_positive_rate"])
        self.assertIsNone(metric["average_precision"])

    def test_no_refitting_from_heldout_events(self):
        import motorpulse.anomaly as anomaly
        with TemporaryDirectory() as tmp:
            plan,paths,model=eval_model(Path(tmp))
            with patch.object(anomaly, "train_baseline",side_effect=AssertionError("refit")):
                rep=evaluate(plan,paths,model)
            self.assertGreater(rep["overall"]["model"]["n"],0)

    def test_model_tampering_mismatched_plan_and_chrono_rejected(self):
        from motorpulse.splits import chronological_split
        with TemporaryDirectory() as tmp:
            plan,paths,model=eval_model(Path(tmp))
            fake=deepcopy(model);fake["center"][0]+=1
            with self.assertRaisesRegex(ValueError,"checksum"):
                evaluate(plan,paths,fake)
            fake=deepcopy(model)
            fake["training"]["groups"]=["fake"]
            fake["model_sha256"]=_hash({k:v for k,v in fake.items() if k!="model_sha256"})
            with self.assertRaisesRegex(ValueError,"partition"):
                evaluate(plan,paths,fake)
            chrono=chronological_split(paths[0])
            with self.assertRaisesRegex(ValueError,"whole-run synthetic"):
                evaluate(chrono,paths,model)

    def test_reject_train_partition_and_invalid_sample_limits(self):
        with TemporaryDirectory() as tmp:
            plan,paths,model=eval_model(Path(tmp))
            with self.assertRaisesRegex(ValueError,"validation or test"):
                evaluate(plan,paths,model,partition="train")
            for limit in (-1,101,True,1.3):
                with self.subTest(limit=limit),self.assertRaises(ValueError):
                    evaluate(plan,paths,model,max_events=limit)
            rep=evaluate(plan,paths,model,max_events=0)
            self.assertEqual(rep["sample_events"],[])
            self.assertEqual(rep["overall"]["model"]["n"],48)

    def test_operating_regime_breakdowns(self):
        assets=(
            AssetScenario("MTR-AA","Fixed",scenario="healthy"),
            AssetScenario("MTR-BB","Variable",scenario="healthy",
                          speed_variation_pct=.1,load_variation_pct=.2),
            AssetScenario("MTR-CC","Fault",scenario="imbalance",severity=.6),
        )
        with TemporaryDirectory() as tmp:
            plan,paths,model=eval_model(Path(tmp),assets=assets)
            report=evaluate(plan,paths,model)
            regimes=report["by_operating_regime"]
            self.assertIn("variable_speed_or_load",regimes)
            self.assertIn("nominal_speed_and_load",regimes)
            self.assertEqual(sum(x["model"]["n"] for x in regimes.values()),
                             report["overall"]["model"]["n"])
            self.assertEqual(len(report["by_motor"]),3)

    def test_markdown_includes_counts_caveats_and_undefined(self):
        with TemporaryDirectory() as tmp:
            assets=(AssetScenario("MTR-AA","Healthy",scenario="healthy"),)
            plan,paths,model=eval_model(Path(tmp),assets=assets,ticks=14)
            rep=evaluate(plan,paths,model)
            md=markdown(rep)
            self.assertIn("false",md.lower())
            self.assertIn("undefined",md)
            self.assertIn("Eligible windows",md)
            self.assertIn("F1",md)
            self.assertIn("No field diagnosis",md)


class EvaluateCLI(unittest.TestCase):
    def test_cli_json_markdown_write_once(self):
        with TemporaryDirectory() as tmp:
            root=Path(tmp)
            plan,paths,model=eval_model(root)
            split=root/"split.json"
            split.write_text(json.dumps(plan),encoding="utf-8")
            fitted=root/"trained.json"
            fitted.write_text(json.dumps({"model":model,"preview":{}}),encoding="utf-8")
            outfile=root/"metrics.json"
            md=root/"metrics.md"
            args=[sys.executable,"-m","motorpulse.evaluation",
                  "--split",str(split),"--model",str(fitted),
                  "--input",*(str(p) for p in paths),
                  "--out",str(outfile),"--markdown",str(md)]
            env={**os.environ,"PYTHONPATH":str(ROOT)}
            p=subprocess.run(args,cwd=root,env=env,capture_output=True,text=True,timeout=45)
            self.assertEqual(p.returncode,0,p.stderr)
            rep=json.loads(outfile.read_text(encoding="utf-8"))
            self.assertEqual(rep["partition"],"test")
            self.assertEqual(rep["overall"]["model"]["n"],48)
            self.assertIn("Held-out synthetic",md.read_text(encoding="utf-8"))
            before=outfile.read_bytes()
            rerun=subprocess.run(args,cwd=root,env=env,capture_output=True,text=True,timeout=45)
            self.assertEqual(rerun.returncode,2)
            self.assertEqual(before,outfile.read_bytes())

    def test_cli_rejects_same_output_path_and_missing_files(self):
        with TemporaryDirectory() as tmp:
            root=Path(tmp)
            plan,paths,model=eval_model(root)
            split=root/"plan.json"
            split.write_text(json.dumps(plan),encoding="utf-8")
            fitted=root/"trained.json"
            fitted.write_text(json.dumps({"model":model}),encoding="utf-8")
            outfile=root/"same.json"
            args=[sys.executable,"-m","motorpulse.evaluation",
                  "--split",str(split),"--model",str(fitted),
                  "--input",*(str(p) for p in paths),
                  "--out",str(outfile),"--markdown",str(outfile)]
            p=subprocess.run(args,cwd=root,env={**os.environ,"PYTHONPATH":str(ROOT)},
                             capture_output=True,text=True,timeout=45)
            self.assertEqual(p.returncode,2)
            self.assertFalse(outfile.exists())

    def test_documentation_and_packaging_present(self):
        guide=(ROOT/"docs/EVALUATION.md").read_text(encoding="utf-8")
        readme=(ROOT/"README.md").read_text(encoding="utf-8")
        todo=(ROOT/"TODO.md").read_text(encoding="utf-8")
        for phrase in ("MP-011","precision","recall","false-positive","average precision",
                       "null", "sensor", "training", "data leakage", "RUL"):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase.lower(),guide.lower())
        self.assertIn("docs/EVALUATION.md",readme)
        self.assertIn("| MP-011 | DONE |",todo)


if __name__ == "__main__":
    unittest.main()
