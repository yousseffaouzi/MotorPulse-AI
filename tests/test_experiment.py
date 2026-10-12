"""MP-033: offline experiment reproducibility, provenance, no-overwrite tests."""
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
from unittest.mock import patch

from motorpulse.experiment import (
    _sha_file, load_experiment_config, run_experiment,
    validate_experiment_config,
)
from motorpulse.ims import _read_strict_json

ROOT = Path(__file__).resolve().parents[1]


def demo_config():
    return {
        "experiment_version":"1.0.0",
        "seeds":[11,22,33],
        "ticks":8,
        "assets":{"assets":[
            {"asset_id":"MTR-AA","name":"Healthy", "scenario":"healthy"},
            {"asset_id":"MTR-BB","name":"Simulated bearing fault",
             "scenario":"bearing_wear","severity":0.7,
             "onset_tick":3},
        ]},
        "virtual_start_utc":"2026-01-01T00:00:00+00:00",
        "step_seconds":1.5,
        "split_seed":42,
        "split_ratios":[0.6,0.2,0.2],
    }


class ConfigValidationTests(unittest.TestCase):
    def test_accepts_and_normalizes_strict_config(self):
        config=demo_config()
        normalized=validate_experiment_config(config)
        self.assertEqual(normalized["seeds"],[11,22,33])
        self.assertEqual(normalized["ticks"],8)
        self.assertEqual(normalized["virtual_start_utc"],"2026-01-01T00:00:00+00:00")
        self.assertEqual(normalized["split_ratios"],[.6,.2,.2])
        self.assertEqual(len(normalized["assets"]["assets"]),2)
        self.assertEqual(validate_experiment_config(normalized),normalized)
        self.assertIn("sensor_noise_g",normalized["assets"]["assets"][0])

    def test_rejects_duplicate_invalid_and_too_few_seeds(self):
        for seeds in ([],[1,2],[1,1,2],[True,2,3],[1,2,2**32],
                      [1,2,"3"],list(range(13))):
            config=demo_config();config["seeds"]=seeds
            with self.subTest(seeds=seeds),self.assertRaises(ValueError):
                validate_experiment_config(config)

    def test_rejects_invalid_ratios_clock_and_ticks(self):
        for key,choices in (
            ("ticks",[0,7,1001,True,8.5]),
            ("step_seconds",[0,-1,float("inf"),.0000001,True]),
            ("virtual_start_utc",["2026-01-01T00:00:00","not-a-time"]),
            ("split_seed",[-1,True,2**32]),
            ("split_ratios",[[.2,.2,.2],[0,.5,.5],[".6",.2,.2]])
        ):
            for choice in choices:
                config=demo_config();config[key]=choice
                with self.subTest(key=key,value=choice),self.assertRaises((ValueError,TypeError)):
                    validate_experiment_config(config)

    def test_rejects_config_paths_extra_unknown_fields_and_wrong_assets(self):
        for bad in (
            {"path":"../secrets","mode":"synthetic"},
            {"download_url":"https://example.com/data"},
        ):
            config=demo_config();config.update(bad)
            with self.assertRaises(ValueError):
                validate_experiment_config(config)
        wrong=demo_config()
        wrong["assets"]={"assets":[{"asset_id":"bad path/../","name":"X","scenario":"healthy"}]}
        with self.assertRaises(ValueError):
            validate_experiment_config(wrong)

    def test_loader_rejects_duplicate_keys_nans_and_symlink(self):
        with TemporaryDirectory() as tmp:
            root=Path(tmp);path=root/"experiment.json"
            path.write_text('{"experiment_version":"1.0.0","experiment_version":"other"}',encoding="utf-8")
            with self.assertRaises(ValueError):
                load_experiment_config(path)
            path.write_text('{"a":NaN}',encoding="utf-8")
            with self.assertRaises(ValueError):
                load_experiment_config(path)
            path.write_text(json.dumps(demo_config()),encoding="utf-8")
            self.assertEqual(load_experiment_config(path)["ticks"],8)
            alias=root/"alias.json"
            try:
                alias.symlink_to(path)
            except (OSError,NotImplementedError):
                return
            with self.assertRaisesRegex(ValueError,"non-symlink"):
                load_experiment_config(alias)

    def test_source_fixture_documented_example_valid(self):
        path=ROOT/"docs/examples/experiment-v1.json"
        config=load_experiment_config(path)
        self.assertEqual(config["experiment_version"],"1.0.0")
        self.assertEqual(len(config["seeds"]),5)
        self.assertEqual(config["ticks"],24)


class ExperimentIntegrationTests(unittest.TestCase):
    def test_pipeline_artifacts_split_model_cards_evaluations(self):
        with TemporaryDirectory() as tmp:
            root=Path(tmp)/"experiment"
            result=run_experiment(demo_config(),root)
            self.assertTrue((root/"experiment-index.json").exists())
            self.assertEqual(json.loads((root/"experiment-index.json").read_text()),result)
            self.assertEqual(result["source"],"synthetic_only")
            self.assertEqual(len(result["runs"]),3)
            self.assertTrue(result["no_real_data"])
            self.assertIsNone(result["remaining_useful_life"])
            split=json.loads((root/"split-plan.json").read_text())
            self.assertEqual(split["policy"],"whole_run_grouped")
            train=set(result["training_groups"])
            valid=set(result["heldout_groups"]["validation"])
            test=set(result["heldout_groups"]["test"])
            self.assertFalse(train & test or train & valid or valid & test)
            self.assertEqual(len(train | test | valid),3)
            model=json.loads((root/"trained-model.json").read_text())["model"]
            self.assertEqual(model["training"]["fit_partitions"],["train"])
            self.assertEqual(model["model_sha256"],result["model_sha256"])
            for group in ("validation","test"):
                metrics=json.loads((root/(group+"-metrics.json")).read_text())
                self.assertEqual(metrics["partition"],group)
                self.assertEqual(metrics["trained_model_sha256"],model["model_sha256"])
                self.assertEqual(metrics["overall"]["model"]["n"],
                                 metrics["overall"]["rules"]["n"])
                self.assertEqual(metrics["evaluation_sha256"],
                                 result["evaluation_sha256"][group])
                self.assertEqual(metrics["sample_events"],[])
            for seed in (11,22,33):
                path=root/"runs"/f"seed-{seed:010d}"
                self.assertTrue((path/"events.jsonl").is_file())
                card=json.loads((path/"dataset-card.json").read_text())
                self.assertEqual(card["instance_kind"],"run")
            self.assertIn("NOT industrial", (root/"SUMMARY.md").read_text())

    def test_repeated_runs_have_identical_stable_hashes(self):
        with TemporaryDirectory() as tmp:
            root=Path(tmp)
            a=run_experiment(demo_config(),root/"a")
            reordered=demo_config()
            reordered["seeds"]=[33,11,22]
            b=run_experiment(reordered,root/"b")
            self.assertEqual(a["experiment_sha256"],b["experiment_sha256"])
            self.assertEqual(a["stable_artifact_sha256"],b["stable_artifact_sha256"])
            self.assertEqual(a["model_sha256"],b["model_sha256"])
            self.assertEqual(a["evaluation_sha256"],b["evaluation_sha256"])
            self.assertEqual(a["source_manifest_semantic_sha256"],
                             b["source_manifest_semantic_sha256"])
            self.assertEqual((root/"a"/"SUMMARY.md").read_bytes(),
                             (root/"b"/"SUMMARY.md").read_bytes())
            self.assertEqual(a["stable_artifact_sha256"]["experiment-config.json"],
                             _sha_file(root/"a"/"experiment-config.json"))
            self.assertEqual(len(a["stable_artifact_sha256"]),3*2+6)

    def test_index_hashes_match_exact_stable_files_and_semantic_manifests(self):
        from motorpulse.splits import _hash
        with TemporaryDirectory() as tmp:
            root=Path(tmp)/"experiment"
            index=run_experiment(demo_config(),root)
            for rel,digest in index["stable_artifact_sha256"].items():
                self.assertEqual(_sha_file(root/rel),digest)
            for run_name,semhash in index["source_manifest_semantic_sha256"].items():
                doc=json.loads((root/"runs"/run_name/"manifest.json").read_text())
                self.assertEqual(semhash,_hash({k:v for k,v in doc.items()
                                                if k!="created_at_utc"}))
            self.assertNotIn("runs/seed-0000000011/manifest.json",
                             index["stable_artifact_sha256"])
            self.assertEqual(index["experiment_sha256"],
                             _hash({k:v for k,v in index.items() if k!="experiment_sha256"}))

    def test_no_overwrite_and_existing_user_content_preserved(self):
        with TemporaryDirectory() as tmp:
            root=Path(tmp)/"experiment"
            root.mkdir();marker=root/"user.txt";marker.write_text("keep",encoding="utf-8")
            with self.assertRaises(FileExistsError):
                run_experiment(demo_config(),root)
            self.assertEqual(marker.read_text(),"keep")
            self.assertEqual(sorted(p.name for p in root.iterdir()),["user.txt"])

    def test_cleanup_only_newly_created_partial_output_on_failure(self):
        with TemporaryDirectory() as tmp:
            root=Path(tmp);target=root/"experiment"
            sibling=root/"keep.txt";sibling.write_text("untouched",encoding="utf-8")
            with patch("motorpulse.experiment.evaluate",side_effect=RuntimeError("deliberate midrun failure")):
                with self.assertRaisesRegex(RuntimeError,"midrun failure"):
                    run_experiment(demo_config(),target)
            self.assertFalse(target.exists())
            self.assertEqual(sibling.read_text(),"untouched")

    def test_insufficient_healthy_training_fails_without_output(self):
        cfg=demo_config()
        cfg["assets"]={"assets":[{"asset_id":"MTR-FF","name":"All fault",
                                   "scenario":"bearing_wear","severity":1.0,
                                   "onset_tick":1}]}
        with TemporaryDirectory() as tmp:
            target=Path(tmp)/"failure"
            with self.assertRaisesRegex(ValueError,"at least 8 healthy"):
                run_experiment(cfg,target)
            self.assertFalse(target.exists())

    def test_cannot_use_symlink_parent_for_output(self):
        with TemporaryDirectory() as tmp:
            root=Path(tmp)
            link=root/"link"; actual=root/"actual";actual.mkdir()
            try:
                link.symlink_to(actual,target_is_directory=True)
            except (OSError,NotImplementedError):
                return
            with self.assertRaisesRegex(ValueError,"parent"):
                run_experiment(demo_config(),link/"escaped")
            self.assertFalse((actual/"escaped").exists())


class CLIAndDocsTests(unittest.TestCase):
    def test_cli_complete_and_nonoverwriting(self):
        with TemporaryDirectory() as tmp:
            root=Path(tmp); cfg=root/"config.json"
            cfg.write_text(json.dumps(demo_config()),encoding="utf-8")
            dest=root/"experiment"
            args=[sys.executable,"-m","motorpulse.experiment",
                  "--config",str(cfg),"--out-dir",str(dest)]
            env={**os.environ,"PYTHONPATH":str(ROOT)}
            p=subprocess.run(args,cwd=root,env=env,text=True,capture_output=True,timeout=90)
            self.assertEqual(p.returncode,0,p.stderr)
            self.assertTrue((dest/"experiment-index.json").exists())
            again=subprocess.run(args,cwd=root,env=env,text=True,capture_output=True,timeout=90)
            self.assertEqual(again.returncode,2)
            self.assertIn("error:",again.stderr)

    def test_cli_rejects_bad_config_without_writing(self):
        with TemporaryDirectory() as tmp:
            root=Path(tmp);cfg=root/"config.json";dest=root/"experiment"
            config=demo_config();config["seeds"]=[11,11,22]
            cfg.write_text(json.dumps(config),encoding="utf-8")
            proc=subprocess.run([sys.executable,"-m","motorpulse.experiment",
                "--config",str(cfg),"--out-dir",str(dest)],
                cwd=root,env={**os.environ,"PYTHONPATH":str(ROOT)},
                text=True,capture_output=True,timeout=20)
            self.assertEqual(proc.returncode,2)
            self.assertFalse(dest.exists())

    def test_readme_todo_docs_and_entrypoint(self):
        guide=(ROOT/"docs/EXPERIMENTS.md").read_text(encoding="utf-8")
        todo=(ROOT/"TODO.md").read_text(encoding="utf-8")
        readme=(ROOT/"README.md").read_text(encoding="utf-8")
        for term in ("MP-033","MP-030","MP-010","MP-011",
                     "synthetic","deterministic","data leakage","RUL"):
            with self.subTest(term=term):
                self.assertIn(term.lower(),guide.lower())
        self.assertIn("docs/EXPERIMENTS.md",readme)
        self.assertIn("| MP-033 | DONE |",todo)


if __name__ == "__main__":
    unittest.main()
