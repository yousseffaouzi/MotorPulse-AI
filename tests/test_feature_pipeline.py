"""MP-034: train-only preprocessing and temporal leakage regression tests."""
from __future__ import annotations

from copy import deepcopy
import json
from math import sqrt
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from motorpulse.anomaly import score_partition, train_baseline
from motorpulse.evaluation import evaluate
from motorpulse.experiment import run_experiment
from motorpulse.export import export_dataset
from motorpulse.feature_pipeline import (
    EXCLUDED, FEATURES, UNITS, fit_preprocessing, numeric_features,
    validate_chronological_boundaries, validate_window_contract,
    verify_fitted_preprocessing,
)
from motorpulse.scenarios import AssetScenario
from motorpulse.splits import _hash, chronological_split, group_split


def event(tick=1, *, asset="MTR-AA", scenario="healthy", quality="good", value=1.0):
    return {
        "asset_id": asset, "tick": tick,
        "scenario": scenario, "sensor_quality": quality,
        "sample_rate_hz": 1024, "sample_count": 1024,
        "window_duration_s": 1.0, "rolling_window_ticks": 5,
        "rolling_observations": min(5, tick),
        "rolling_valid_observations": min(5, tick),
        "rms_g": value, "crest_factor": value + 1,
        "band_80_400_rms_g": value / 2,
        "temperature_c": value + 40, "rpm": value + 1450,
    }


def fit_rows(rows=None, *, group="train-run", source_hash="a"*64):
    if rows is None:
        rows = [(group, event(tick=i, value=float(i))) for i in range(1, 9)]
    return fit_preprocessing(
        rows, train_groups=[group], split_plan_sha256="b"*64,
        source_hashes={group: source_hash},
    )


def runs(root, seeds=(11,22,33), *, ticks=12, assets=None, step=1.5):
    paths = []
    for seed in seeds:
        folder=root/f"run-{seed}"
        opts=dict(ticks=ticks,seed=seed,file_format="jsonl",step_seconds=step)
        if assets is not None:
            opts["assets"]=assets
        export_dataset(folder,**opts)
        paths.append(folder/"manifest.json")
    return group_split(paths,source_type="synthetic"),paths


class FeatureContractTests(unittest.TestCase):
    def test_feature_allowlist_excludes_truth_rules_identity_and_quality(self):
        self.assertEqual(len(FEATURES),5)
        self.assertEqual(len(FEATURES),len(UNITS))
        for forbidden in ("scenario","health","sensor_quality","asset_id",
                          "timestamp_utc","export_id","fault_phase",
                          "operating_config","tick","severity"):
            self.assertIn(forbidden,EXCLUDED)
            self.assertNotIn(forbidden,FEATURES)
        x=event()
        copy={**x,"scenario":"bearing_wear","health":"critical",
              "severity":1,"timestamp_utc":"2100-01-01",
              "sensor_quality":"outlier","asset_id":"DIFFERENT"}
        self.assertEqual(numeric_features(x),numeric_features(copy))

    def test_nonfinite_missing_negative_and_boolean_are_rejected(self):
        for value in (None,True,False,"12",float("nan"),
                      float("inf"),-0.001):
            with self.subTest(value=value),self.assertRaises(ValueError):
                numeric_features({**event(), "rms_g":value})
        with self.assertRaises(ValueError):
            numeric_features({"rms_g":1})
        self.assertEqual(numeric_features(event(value=1)),(1,2,.5,41,1451))

    def test_sampling_rate_sample_count_and_duration_must_match(self):
        for key,bad in (("sample_rate_hz",8000),("sample_count",512),
                        ("window_duration_s",2),("rolling_window_ticks",4),
                        ("rolling_observations",0),("rolling_observations",6),
                        ("rolling_valid_observations",-1),
                        ("rolling_valid_observations",7),
                        ("tick",0),("asset_id","")):
            with self.subTest(key=key),self.assertRaises(ValueError):
                validate_window_contract({**event(tick=6),key:bad})
        validate_window_contract(event(tick=1))
        validate_window_contract(event(tick=12))

    def test_known_missing_sensor_history_valid_with_zero_valid_rms(self):
        candidate=event(tick=3,quality="missing")
        candidate["rms_g"]=None
        candidate["rolling_valid_observations"]=0
        validate_window_contract(candidate)
        with self.assertRaises(ValueError):
            numeric_features(candidate)


class PreprocessingFitTests(unittest.TestCase):
    def test_fitted_means_population_stds_and_training_scale_floors(self):
        fitted=fit_rows()
        self.assertEqual(fitted["train_groups"],["train-run"])
        self.assertEqual(fitted["fit_partition"],"train")
        self.assertEqual(fitted["training_windows"],8)
        self.assertEqual(fitted["center"][0],4.5)
        self.assertAlmostEqual(fitted["population_std"][0],sqrt(5.25))
        self.assertAlmostEqual(fitted["effective_scales"][0],sqrt(5.25))
        self.assertEqual(fitted["feature_names"],list(FEATURES))
        self.assertEqual(fitted["pipeline_sha256"],
                         _hash({k:v for k,v in fitted.items() if k!="pipeline_sha256"}))

    def test_constant_feature_floor_no_division_by_zero(self):
        rows=[("train-run",event(tick=i,value=0.0)) for i in range(1,9)]
        fitted=fit_rows(rows)
        self.assertEqual(fitted["population_std"],[0]*5)
        self.assertEqual(fitted["effective_scales"][0],1e-6)
        self.assertEqual(fitted["effective_scales"][3],.4)
        self.assertEqual(fitted["effective_scales"][4],14.5)

    def test_reordered_training_rows_deterministic(self):
        rows=[("train-run",event(tick=i,value=float(i))) for i in range(1,9)]
        self.assertEqual(fit_rows(rows),fit_rows(list(reversed(rows))))

    def test_reject_validation_or_test_rows_even_when_healthy(self):
        rows=[("train-run",event(tick=i)) for i in range(1,9)]
        rows[3]=("heldout-run",event(tick=4))
        with self.assertRaisesRegex(ValueError,"held-out"):
            fit_rows(rows)

    def test_reject_nonhealthy_and_bad_sensor_in_fitted_set(self):
        rows=[("train-run",event(tick=i)) for i in range(1,9)]
        for field,value in (("scenario","imbalance"),("sensor_quality","outlier"),
                            ("sensor_quality","missing")):
            with self.subTest(field=field,value=value),self.assertRaisesRegex(ValueError,"healthy good-sensor"):
                samples=deepcopy(rows)
                samples[0][1][field]=value
                fit_rows(samples)

    def test_duplicate_asset_tick_run_identity_rejected(self):
        rows=[("train-run",event(tick=i)) for i in range(1,9)]
        rows[7]=("train-run",event(tick=1))
        with self.assertRaisesRegex(ValueError,"repeated training window"):
            fit_rows(rows)

    def test_insufficient_training_windows_and_invalid_provenance(self):
        with self.assertRaisesRegex(ValueError,"at least 8"):
            fit_rows([("train-run",event(tick=i)) for i in range(1,7)])
        with self.assertRaises(ValueError):
            fit_preprocessing([],train_groups=["train-run","train-run"],
                              split_plan_sha256="b"*64,source_hashes={"train-run":"a"*64})
        with self.assertRaises(ValueError):
            fit_preprocessing([],train_groups=["train-run"],
                              split_plan_sha256="broken",source_hashes={"train-run":"a"*64})
        with self.assertRaises(ValueError):
            fit_preprocessing([],train_groups=["train-run"],
                              split_plan_sha256="b"*64,source_hashes={"train-run":"bad"})


class TemporalBoundaryTests(unittest.TestCase):
    def test_normal_and_fast_virtual_clocks_enforce_distinct_gaps(self):
        with TemporaryDirectory() as tmp:
            root=Path(tmp)
            export_dataset(root/"normal",ticks=30,step_seconds=1.5,file_format="jsonl")
            normal=chronological_split(root/"normal"/"manifest.json")
            self.assertEqual(validate_chronological_boundaries(
                normal,window_duration_s=1,step_seconds=1.5),4)
            export_dataset(root/"fast",ticks=45,step_seconds=.1,file_format="jsonl")
            fast=chronological_split(root/"fast"/"manifest.json",purge_ticks=10)
            self.assertEqual(validate_chronological_boundaries(
                fast,window_duration_s=1,step_seconds=.1),10)

    def test_reject_shortened_gap_and_forged_purge_metadata(self):
        with TemporaryDirectory() as tmp:
            root=Path(tmp)
            export_dataset(root/"source",ticks=40,file_format="jsonl")
            original=chronological_split(root/"source"/"manifest.json")
            plan=deepcopy(original)
            plan["partitions"]["validation"]["tick_start"]=plan["partitions"]["train"]["tick_end"]+2
            plan["partitions"]["validation"]["ticks"]=(
                plan["partitions"]["validation"]["tick_end"]-plan["partitions"]["validation"]["tick_start"]+1)
            with self.assertRaisesRegex(ValueError,"data leakage"):
                validate_chronological_boundaries(plan,window_duration_s=1,step_seconds=1.5)
            plan=deepcopy(original);plan["purged_ranges"]=[]
            with self.assertRaisesRegex(ValueError,"purge metadata"):
                validate_chronological_boundaries(plan,window_duration_s=1,step_seconds=1.5)
            plan=deepcopy(original);plan["minimum_purge_ticks"]=1
            with self.assertRaisesRegex(ValueError,"minimum purge"):
                validate_chronological_boundaries(plan,window_duration_s=1,step_seconds=1.5)

    def test_always_reject_chronological_train_fitting_even_with_gap(self):
        with TemporaryDirectory() as tmp:
            root=Path(tmp)
            export_dataset(root/"source",ticks=40,file_format="jsonl")
            plan=chronological_split(root/"source"/"manifest.json")
            with self.assertRaisesRegex(ValueError,"whole-run synthetic"):
                train_baseline(plan,[root/"source"/"manifest.json"]*3)


class IntegratedTrainingTests(unittest.TestCase):
    def test_train_record_and_frozen_validation_test_preprocessing(self):
        with TemporaryDirectory() as tmp:
            plan,paths=runs(Path(tmp))
            model=train_baseline(plan,paths)
            proc=model["feature_processing"]
            self.assertEqual(proc["training_windows"],model["training"]["healthy_good_sensor_events"])
            self.assertEqual(proc["train_groups"],model["training"]["groups"])
            self.assertEqual(proc["center"],model["center"])
            self.assertEqual(proc["effective_scales"],model["effective_scales"])
            sources={s["group_id"]:s for s in plan["sources"]}
            verify_fitted_preprocessing(proc,model=model,plan=plan,sources=sources)
            original=json.dumps(model,sort_keys=True)
            scored=score_partition(plan,paths,model,partition="test",max_events=2)
            evaluated=evaluate(plan,paths,model,partition="validation",max_events=0)
            self.assertEqual(scored["model_sha256"],model["model_sha256"])
            self.assertEqual(evaluated["feature_pipeline_sha256"],proc["pipeline_sha256"])
            self.assertEqual(json.dumps(model,sort_keys=True),original)

    def test_recomputed_model_checksum_does_not_hide_modified_preprocessing(self):
        with TemporaryDirectory() as tmp:
            plan,paths=runs(Path(tmp))
            model=train_baseline(plan,paths)
            wrong=deepcopy(model)
            # Fitted arrays are initially aliased to the model for consistency.
            # Rebind only the model array to simulate a changed scoring scaler.
            wrong["center"]=list(wrong["center"])
            wrong["center"][0]+=123
            wrong["model_sha256"]=_hash({k:v for k,v in wrong.items() if k!="model_sha256"})
            with self.assertRaisesRegex(ValueError,"model/preprocessing"):
                score_partition(plan,paths,wrong,partition="test")
            with self.assertRaisesRegex(ValueError,"model/preprocessing"):
                evaluate(plan,paths,wrong)

    def test_wrong_train_source_digest_rejected_even_if_hashes_recomputed(self):
        with TemporaryDirectory() as tmp:
            plan,paths=runs(Path(tmp))
            model=train_baseline(plan,paths)
            wrong=deepcopy(model)
            g=wrong["feature_processing"]["train_groups"][0]
            wrong["feature_processing"]["train_source_sha256"][g]="f"*64
            wrong["feature_processing"]["pipeline_sha256"]=_hash({
                k:v for k,v in wrong["feature_processing"].items() if k!="pipeline_sha256"})
            wrong["model_sha256"]=_hash({k:v for k,v in wrong.items() if k!="model_sha256"})
            with self.assertRaisesRegex(ValueError,"source/sampling"):
                evaluate(plan,paths,wrong)

    def test_experiment_index_includes_fit_only_pipeline(self):
        from motorpulse.experiment import validate_experiment_config
        with TemporaryDirectory() as tmp:
            cfg={
                "experiment_version":"1.0.0", "seeds":[11,22,33], "ticks":9,
                "assets":{"assets":[
                    {"asset_id":"MTR-AA","name":"Healthy","scenario":"healthy"},
                    {"asset_id":"MTR-BB","name":"Fault","scenario":"imbalance",
                     "severity":0.6,"onset_tick":3}]},
                "virtual_start_utc":"2026-01-01T00:00:00+00:00",
                "step_seconds":1.5,"split_seed":42,"split_ratios":[.6,.2,.2]}
            folder=Path(tmp)/"experiment"
            index=run_experiment(cfg,folder)
            model=json.loads((folder/"trained-model.json").read_text())["model"]
            self.assertEqual(index["feature_pipeline_sha256"],
                             model["feature_processing"]["pipeline_sha256"])
            self.assertEqual(index["feature_pipeline_version"],"1.0.0")
            self.assertTrue(index["feature_pipeline_sha256"])


class DocumentationTests(unittest.TestCase):
    def test_published_feature_documentation_and_roadmap(self):
        root=Path(__file__).resolve().parents[1]
        readme=(root/"README.md").read_text(encoding="utf-8")
        guide=(root/"docs/FEATURE_PIPELINE.md").read_text(encoding="utf-8")
        todo=(root/"TODO.md").read_text(encoding="utf-8")
        for phrase in ("MP-034","MP-030","training only","overlapping","purge",
                       "sensor_quality","data leakage","RUL"):
            self.assertIn(phrase.lower(),guide.lower())
        self.assertIn("docs/FEATURE_PIPELINE.md",readme)
        self.assertIn("| MP-034 | DONE |",todo)


if __name__=="__main__":
    unittest.main()
