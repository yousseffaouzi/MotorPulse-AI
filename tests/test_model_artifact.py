"""MP-035 portable model artifact contracts, tampering and CLI regression tests."""
from __future__ import annotations

from copy import deepcopy
import json
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from motorpulse.anomaly import score_partition, train_baseline
from motorpulse.evaluation import evaluate
from motorpulse.export import export_dataset
from motorpulse.model_artifact import (
    ARTIFACT_VERSION, MAX_ARTIFACT_BYTES, build_model_artifact,
    load_model_artifact, save_model_artifact, validate_model_artifact,
    verify_model_artifact,
)
from motorpulse.splits import _hash, group_split

ROOT = Path(__file__).resolve().parents[1]


def fixture(root: Path, *, seeds=(11, 22, 33), ticks=12):
    manifests = []
    for seed in seeds:
        folder = root / f"run-{seed}"
        export_dataset(folder, seed=seed, ticks=ticks, file_format="jsonl")
        manifests.append(folder / "manifest.json")
    plan = group_split(manifests, source_type="synthetic", seed=42)
    model = train_baseline(plan, manifests)
    return plan, manifests, model


def resign(artifact):
    """Recompute all outer self-checks, not forge actual source provenance."""
    model = artifact["model"]
    model["feature_processing"]["pipeline_sha256"] = _hash({
        k: v for k,v in model["feature_processing"].items() if k != "pipeline_sha256"
    })
    artifact["processor_sha256"] = model["feature_processing"]["pipeline_sha256"]
    model["model_sha256"] = _hash({k:v for k,v in model.items() if k != "model_sha256"})
    artifact["model_sha256"] = model["model_sha256"]
    artifact["artifact_sha256"] = _hash({k:v for k,v in artifact.items() if k != "artifact_sha256"})
    return artifact


class ModelArtifactRoundTripTests(unittest.TestCase):
    def test_roundtrip_preserves_frozen_model_and_source_ids(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            plan, manifests, model = fixture(root)
            artifact = build_model_artifact(plan, manifests, model)
            self.assertEqual(artifact["artifact_version"], ARTIFACT_VERSION)
            self.assertEqual(artifact["model_version"], "1.0.0")
            self.assertEqual(artifact["model_sha256"], model["model_sha256"])
            self.assertEqual(artifact["processor_sha256"],
                             model["feature_processing"]["pipeline_sha256"])
            self.assertEqual(artifact["split_plan_sha256"], plan["plan_sha256"])
            self.assertEqual(len(artifact["source_runs"]), 3)
            self.assertEqual({r["partition"] for r in artifact["source_runs"]},
                             {"train","validation","test"})
            self.assertEqual(artifact["training_groups"],model["training"]["groups"])
            self.assertFalse(artifact["claimed_failure_probability"])
            self.assertIsNone(artifact["remaining_useful_life"])
            validate_model_artifact(artifact)
            out = root / "portable.json"
            save_model_artifact(out, artifact)
            self.assertEqual(load_model_artifact(out, plan=plan, manifests=manifests), model)
            self.assertEqual(artifact, json.loads(out.read_text(encoding="utf-8")))

    def test_reversed_sources_and_different_folder_not_in_artifact(self):
        with TemporaryDirectory() as tmp:
            root=Path(tmp)
            plan,manifests,model=fixture(root,seeds=(11,22,33,44))
            a=build_model_artifact(plan,manifests,model)
            b=build_model_artifact(plan,list(reversed(manifests)),model)
            self.assertEqual(a,b)
            serialized=json.dumps(a)
            self.assertNotIn(str(root),serialized)
            self.assertNotIn("created_at_utc",serialized)
            self.assertNotIn("events_sample",serialized)
            self.assertEqual(a["runtime"]["runtime_dependencies"],[])
            self.assertRegex(a["runtime"]["producer_sha256"],"^[0-9a-f]{64}$")

    def test_portable_model_scores_validation_test_without_refit(self):
        with TemporaryDirectory() as tmp:
            root=Path(tmp)
            plan,paths,model=fixture(root)
            artifact=build_model_artifact(plan,paths,model)
            before=json.dumps(model,sort_keys=True)
            loaded=verify_model_artifact(artifact,plan,paths)
            self.assertEqual(loaded,model)
            self.assertIsNot(loaded,model)
            val=evaluate(plan,paths,loaded,partition="validation",max_events=0)
            test=evaluate(plan,paths,loaded,partition="test",max_events=0)
            self.assertEqual(val["trained_model_sha256"],model["model_sha256"])
            self.assertEqual(test["feature_pipeline_sha256"],artifact["processor_sha256"])
            self.assertEqual(json.dumps(model,sort_keys=True),before)
            scored=score_partition(plan,paths,loaded,partition="test",max_events=2)
            self.assertEqual(scored["displayed_events"],2)

    def test_saved_artifact_is_reproducible_and_write_once(self):
        with TemporaryDirectory() as tmp:
            root=Path(tmp)
            plan,paths,model=fixture(root)
            artifact=build_model_artifact(plan,paths,model)
            out=root/"model-artifact.json"
            save_model_artifact(out,artifact)
            initial=out.read_bytes()
            self.assertLess(len(initial),MAX_ARTIFACT_BYTES)
            with self.assertRaises(FileExistsError):
                save_model_artifact(out,artifact)
            self.assertEqual(initial,out.read_bytes())
            other=root/"copy.json"
            save_model_artifact(other,build_model_artifact(plan,list(reversed(paths)),model))
            self.assertEqual(initial,other.read_bytes())

    def test_source_integrity_changed_after_fit_refused(self):
        with TemporaryDirectory() as tmp:
            root=Path(tmp)
            plan,paths,model=fixture(root)
            artifact=build_model_artifact(plan,paths,model)
            out=root/"model.json"
            save_model_artifact(out,artifact)
            original=paths[1].parent/"events.jsonl"
            original.write_bytes(original.read_bytes()+b"corrupt")
            with self.assertRaisesRegex(ValueError,"integrity check"):
                load_model_artifact(out,plan=plan,manifests=paths)

    def test_other_split_plan_cannot_load_artifact(self):
        with TemporaryDirectory() as tmp:
            root=Path(tmp)
            plan,paths,model=fixture(root,seeds=(11,22,33,44,55))
            artifact=build_model_artifact(plan,paths,model)
            changed=deepcopy(plan)
            changed["seed"]=29
            changed["plan_sha256"]=_hash({k:v for k,v in changed.items() if k!="plan_sha256"})
            with self.assertRaisesRegex(ValueError,"split|partition|provenance"):
                verify_model_artifact(artifact,changed,paths)


class ArtifactIntegrityTests(unittest.TestCase):
    def test_reject_unsupported_future_version_kind_and_extra_fields(self):
        with TemporaryDirectory() as tmp:
            plan,paths,model=fixture(Path(tmp))
            good=build_model_artifact(plan,paths,model)
            for key,value in (("artifact_version","2.0.0"),
                              ("kind","python_pickle"),
                              ("model_version","9.9.9"),
                              ("claimed_failure_probability",True)):
                with self.subTest(key=key),self.assertRaises(ValueError):
                    trial=deepcopy(good)
                    trial[key]=value
                    validate_model_artifact(trial)
            trial=deepcopy(good)
            trial["unexpected"]="execute-me"
            with self.assertRaisesRegex(ValueError,"top-level"):
                validate_model_artifact(trial)

    def test_reject_tampered_model_scalar_and_outer_digest(self):
        with TemporaryDirectory() as tmp:
            plan,paths,model=fixture(Path(tmp))
            original=build_model_artifact(plan,paths,model)
            tampered=deepcopy(original)
            tampered["model"]["center"][0] += 1
            with self.assertRaisesRegex(ValueError,"embedded model checksum"):
                validate_model_artifact(tampered)
            tampered=deepcopy(original)
            tampered["artifact_sha256"]="0"*64
            with self.assertRaisesRegex(ValueError,"artifact checksum"):
                validate_model_artifact(tampered)

    def test_reject_resigned_fitted_scale_mismatch(self):
        with TemporaryDirectory() as tmp:
            plan,paths,model=fixture(Path(tmp))
            bad=build_model_artifact(plan,paths,model)
            bad["model"]["center"]=list(bad["model"]["center"])
            bad["model"]["center"][0]+=1
            resign(bad)
            with self.assertRaisesRegex(ValueError,"incompatible fitted parameters"):
                validate_model_artifact(bad)

    def test_reject_resigned_wrong_feature_order_and_units(self):
        with TemporaryDirectory() as tmp:
            plan,paths,model=fixture(Path(tmp))
            good=build_model_artifact(plan,paths,model)
            for field,alternative in (("names",list(reversed(good["feature_contract"]["names"]))),
                                      ("units",["unknown"]*5)):
                with self.subTest(field=field):
                    bad=deepcopy(good)
                    bad["model"]["feature_contract"][field]=alternative
                    bad["feature_contract"][field]=alternative
                    resign(bad)
                    with self.assertRaisesRegex(ValueError,"feature"):
                        validate_model_artifact(bad)

    def test_reject_resigned_nonfinite_or_nonpositive_fitted_numeric(self):
        with TemporaryDirectory() as tmp:
            plan,paths,model=fixture(Path(tmp))
            good=build_model_artifact(plan,paths,model)
            for value in (0,-1,True,float("inf")):
                with self.subTest(value=value):
                    bad=deepcopy(good)
                    # Mutate both copies deliberately to test numeric contract,
                    # not just the duplicate-field consistency guard.
                    bad["model"]["effective_scales"][0]=value
                    bad["model"]["feature_processing"]["effective_scales"][0]=value
                    if value==float("inf"):
                        # JSON hashing itself rejects Infinity before writing.
                        with self.assertRaises(ValueError):
                            resign(bad)
                    else:
                        resign(bad)
                        with self.assertRaisesRegex(ValueError,"fitted parameters"):
                            validate_model_artifact(bad)

    def test_reject_modified_train_threshold_even_with_outer_hashes(self):
        with TemporaryDirectory() as tmp:
            plan,paths,model=fixture(Path(tmp))
            bad=build_model_artifact(plan,paths,model)
            bad["model"]["calibration"]["partition"]="test"
            resign(bad)
            with self.assertRaisesRegex(ValueError,"threshold"):
                validate_model_artifact(bad)

    def test_reject_resigned_source_digest_and_card_forgery(self):
        with TemporaryDirectory() as tmp:
            plan,paths,model=fixture(Path(tmp))
            good=build_model_artifact(plan,paths,model)
            bad=deepcopy(good)
            bad["source_runs"][1]["source_data_sha256"]="f"*64
            bad["artifact_sha256"]=_hash({k:v for k,v in bad.items() if k!="artifact_sha256"})
            with self.assertRaisesRegex(ValueError,"source|train-data|provenance"):
                verify_model_artifact(bad,plan,paths)
            bad=deepcopy(good)
            bad["source_runs"][0]["dataset_card_id"]="fake-card"
            bad["artifact_sha256"]=_hash({k:v for k,v in bad.items() if k!="artifact_sha256"})
            with self.assertRaisesRegex(ValueError,"card|source"):
                verify_model_artifact(bad,plan,paths)

    def test_strict_reader_rejects_duplicate_keys_nan_and_symlink(self):
        with TemporaryDirectory() as tmp:
            root=Path(tmp)
            plan,paths,model=fixture(root)
            out=root/"artifact.json"
            save_model_artifact(out,build_model_artifact(plan,paths,model))
            out.write_text('{"artifact_version":"1.0.0","artifact_version":"2.0.0"}',encoding="utf-8")
            with self.assertRaisesRegex(ValueError,"duplicate JSON"):
                load_model_artifact(out,plan=plan,manifests=paths)
            out.write_text('{"threshold":NaN}',encoding="utf-8")
            with self.assertRaisesRegex(ValueError,"non-finite"):
                load_model_artifact(out,plan=plan,manifests=paths)
            out.write_text(" "*(MAX_ARTIFACT_BYTES+1),encoding="utf-8")
            with self.assertRaisesRegex(ValueError,"bytes"):
                load_model_artifact(out,plan=plan,manifests=paths)
            link=root/"alias.json"
            try:
                link.symlink_to(out)
            except (OSError,NotImplementedError):
                return
            with self.assertRaisesRegex(ValueError,"non-symlink"):
                load_model_artifact(link,plan=plan,manifests=paths)

    def test_oversized_artifact_refused_before_writing(self):
        with TemporaryDirectory() as tmp:
            root=Path(tmp)
            plan,paths,model=fixture(root)
            artifact=build_model_artifact(plan,paths,model)
            artifact["limitations"]="A"*(MAX_ARTIFACT_BYTES+100)
            artifact["artifact_sha256"]=_hash({k:v for k,v in artifact.items() if k!="artifact_sha256"})
            with self.assertRaisesRegex(ValueError,"512 KiB"):
                save_model_artifact(root/"too-large.json",artifact)
            self.assertFalse((root/"too-large.json").exists())


class ArtifactCLIAndDocsTests(unittest.TestCase):
    def test_cli_save_verify_and_refuse_overwrite(self):
        with TemporaryDirectory() as tmp:
            root=Path(tmp)
            plan,paths,model=fixture(root)
            split=root/"split.json"; split.write_text(json.dumps(plan),encoding="utf-8")
            trained=root/"trained.json"; trained.write_text(json.dumps({"model":model}),encoding="utf-8")
            dest=root/"model-artifact.json"
            base=[sys.executable,"-m","motorpulse.model_artifact"]
            env={**os.environ,"PYTHONPATH":str(ROOT)}
            args=[*base,"save","--split",str(split),"--input",*(str(p) for p in paths),
                  "--model",str(trained),"--out",str(dest)]
            proc=subprocess.run(args,cwd=root,env=env,text=True,capture_output=True,timeout=60)
            self.assertEqual(proc.returncode,0,proc.stderr)
            self.assertTrue(dest.exists())
            verify=[*base,"verify","--split",str(split),"--input",
                    *(str(p) for p in paths),"--artifact",str(dest)]
            proc=subprocess.run(verify,cwd=root,env=env,text=True,capture_output=True,timeout=60)
            self.assertEqual(proc.returncode,0,proc.stderr)
            self.assertIn("Verified model artifact",proc.stdout)
            again=subprocess.run(args,cwd=root,env=env,text=True,capture_output=True,timeout=60)
            self.assertEqual(again.returncode,2)
            self.assertIn("error:",again.stderr)

    def test_evaluation_cli_accepts_portable_json_model_and_legacy_wrapper(self):
        with TemporaryDirectory() as tmp:
            root=Path(tmp)
            plan,paths,model=fixture(root)
            split=root/"split.json";split.write_text(json.dumps(plan),encoding="utf-8")
            portable=root/"portable.json"
            save_model_artifact(portable,build_model_artifact(plan,paths,model))
            legacy=root/"legacy.json";legacy.write_text(json.dumps({"model":model}),encoding="utf-8")
            env={**os.environ,"PYTHONPATH":str(ROOT)}
            reports=[]
            for file,tag in ((portable,"portable"),(legacy,"legacy")):
                out=root/(tag+"-metrics.json")
                args=[sys.executable,"-m","motorpulse.evaluation",
                      "--split",str(split),"--model",str(file),"--input",
                      *(str(x) for x in paths),"--out",str(out)]
                proc=subprocess.run(args,cwd=root,env=env,text=True,capture_output=True,timeout=60)
                self.assertEqual(proc.returncode,0,proc.stderr)
                reports.append(json.loads(out.read_text(encoding="utf-8")))
            self.assertEqual(reports[0],reports[1])

    def test_experiment_index_links_saved_portable_artifact(self):
        from motorpulse.experiment import run_experiment
        from motorpulse.model_artifact import load_model_artifact
        with TemporaryDirectory() as tmp:
            root=Path(tmp)
            cfg={
                "experiment_version":"1.0.0","seeds":[11,22,33],"ticks":9,
                "assets":{"assets":[
                    {"asset_id":"MTR-AA","name":"Healthy","scenario":"healthy"},
                    {"asset_id":"MTR-BB","name":"Fault","scenario":"imbalance",
                     "severity":0.6,"onset_tick":3}]},
                "virtual_start_utc":"2026-01-01T00:00:00+00:00",
                "step_seconds":1.5,"split_seed":42,"split_ratios":[.6,.2,.2]
            }
            target=root/"experiment"
            index=run_experiment(cfg,target)
            portable=target/"model-artifact.json"
            self.assertTrue(portable.is_file())
            data=json.loads(portable.read_text(encoding="utf-8"))
            self.assertEqual(index["model_artifact_version"],ARTIFACT_VERSION)
            self.assertEqual(index["model_artifact_sha256"],data["artifact_sha256"])
            self.assertEqual(index["stable_artifact_sha256"]["model-artifact.json"],
                             __import__("hashlib").sha256(portable.read_bytes()).hexdigest())
            paths=[target/"runs"/f"seed-{n:010d}"/"manifest.json" for n in (11,22,33)]
            split=json.loads((target/"split-plan.json").read_text(encoding="utf-8"))
            self.assertEqual(load_model_artifact(portable,plan=split,manifests=paths),
                             json.loads((target/"trained-model.json").read_text())["model"])

    def test_documentation_and_installed_entrypoint_are_present(self):
        readme=(ROOT/"README.md").read_text(encoding="utf-8")
        doc=(ROOT/"docs/MODEL_ARTIFACTS.md").read_text(encoding="utf-8")
        todo=(ROOT/"TODO.md").read_text(encoding="utf-8")
        for term in ("MP-035","MP-034","JSON","source","split",
                     "training only","failure probability","RUL","SHA-256"):
            with self.subTest(term=term):
                self.assertIn(term.lower(),doc.lower())
        self.assertIn("docs/MODEL_ARTIFACTS.md",readme)
        self.assertIn("| MP-035 | DONE |",todo)


if __name__=="__main__":
    unittest.main()
