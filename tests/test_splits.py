"""MP-030: whole-run leakage guards and purged synthetic time holdout tests."""
from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest

from motorpulse.export import export_dataset
from motorpulse.ims import inspect_ims_directory, write_local_manifest
from motorpulse.splits import (
    DEFAULT_RATIOS, _allocate, chronological_split, group_split,
)

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests/fixtures/ims_style_synthetic"
STAMP1 = "2004.02.12.10.32.39"
STAMP2 = "2004.02.12.10.32.49"


def synthetic_runs(root: Path, seeds=(11,22,33,44,55), ticks=20) -> list[Path]:
    result = []
    for seed in seeds:
        folder = root / f"synthetic-{seed}"
        export_dataset(folder, ticks=ticks, seed=seed)
        result.append(folder / "manifest.json")
    return result


def ims_runs(root: Path, test_sets=("1","2","3")) -> list[Path]:
    result = []
    for set_id in test_sets:
        folder = root / f"ims-{set_id}"
        folder.mkdir()
        for number, timestamp in enumerate((STAMP1, STAMP2)):
            # The raw numbers are invented; each synthetic test set is distinct
            # to avoid falsely shared source-waveform hashes across runs.
            original = (FIXTURE / timestamp).read_text(encoding="ascii")
            prefix = str(int(set_id)*10 + number)
            (folder / timestamp).write_text(
                "\n".join(prefix + " " + line for line in original.splitlines()) + "\n",
                encoding="ascii",
            )
        source = inspect_ims_directory(
            folder, test_set=set_id, sample_rate_hz=8,
            expected_samples=4, expected_channels=5,
        )
        output = root / f"inspection-{set_id}.json"
        write_local_manifest(output, source)
        result.append(output)
    return result


class WholeRunSplitTests(unittest.TestCase):
    def test_synthetic_three_run_default_nonempty_partitions(self):
        with TemporaryDirectory() as tmp:
            paths = synthetic_runs(Path(tmp), seeds=(1,2,3))
            plan = group_split(paths, source_type="synthetic")
            self.assertEqual(plan["policy"],"whole_run_grouped")
            self.assertEqual(plan["source_type"],"synthetic_motor_feature_events")
            self.assertEqual([plan["partitions"][p]["groups"] for p in
                              ("train","validation","test")],[1,1,1])
            self.assertEqual(set(plan["partitions"]),{"train","validation","test"})
            self.assertEqual(len(plan["sources"]),3)
            self.assertTrue(plan["label_blind_assignment"])
            self.assertNotIn("synthetic_fault_labels",json.dumps(plan))
            self.assertEqual(len(plan["plan_sha256"]),64)
            self.assertTrue(all(s["group_id"].startswith("synthetic-run:")
                                for s in plan["sources"]))
            ids=[sid for group in plan["partitions"].values() for sid in group["group_ids"]]
            self.assertEqual(len(ids),len(set(ids)))

    def test_seed_replay_input_order_and_real_creation_time_independent(self):
        with TemporaryDirectory() as tmp:
            paths = synthetic_runs(Path(tmp))
            first = group_split(paths,source_type="synthetic",seed=24)
            second = group_split(list(reversed(paths)),source_type="synthetic",seed=24)
            self.assertEqual(first,second)
            self.assertEqual(first["partitions"]["train"]["groups"],3)
            self.assertEqual(first["partitions"]["validation"]["groups"],1)
            self.assertEqual(first["partitions"]["test"]["groups"],1)
            # Generated-at wall-clock may vary; split identity must not depend on it.
            manifest_path=paths[0]
            meta=json.loads(manifest_path.read_text(encoding="utf-8"))
            meta["created_at_utc"]="2030-01-01T00:00:00+00:00"
            manifest_path.write_text(json.dumps(meta),encoding="utf-8")
            self.assertEqual(first,group_split(paths,source_type="synthetic",seed=24))

    def test_same_seed_config_start_shortened_export_is_same_run(self):
        with TemporaryDirectory() as tmp:
            root=Path(tmp)
            export_dataset(root/"full",ticks=18,seed=7)
            export_dataset(root/"short",ticks=8,seed=7)
            export_dataset(root/"other",ticks=18,seed=8)
            with self.assertRaisesRegex(ValueError,"duplicate/overlapping run group"):
                group_split([root/x/"manifest.json" for x in ("full","short","other")],
                            source_type="synthetic")

    def test_copy_of_exact_export_rejected(self):
        with TemporaryDirectory() as tmp:
            paths=synthetic_runs(Path(tmp),seeds=(1,2,3))
            with self.assertRaisesRegex(ValueError,"duplicate"):
                group_split([paths[0],paths[0],paths[2]],source_type="synthetic")

    def test_ratios_allocate_whole_groups_not_rows(self):
        self.assertEqual(_allocate(3,DEFAULT_RATIOS),(1,1,1))
        self.assertEqual(_allocate(4,DEFAULT_RATIOS),(2,1,1))
        self.assertEqual(_allocate(5,DEFAULT_RATIOS),(3,1,1))
        self.assertEqual(_allocate(10,DEFAULT_RATIOS),(6,2,2))
        for ratios in ((0,0.5,0.5),(.4,.4,.4),
                       (float("nan"),.1,.9),("0.6",.2,.2)):
            with self.subTest(ratios=ratios), self.assertRaises(ValueError):
                _allocate(5,ratios)
        with self.assertRaises(ValueError):
            _allocate(2,DEFAULT_RATIOS)

    def test_invalid_seed_ratios_and_insufficient_sources(self):
        with TemporaryDirectory() as tmp:
            paths=synthetic_runs(Path(tmp),seeds=(1,2,3))
            for seed in (True,-1,2**32,"42"):
                with self.subTest(seed=seed), self.assertRaises(ValueError):
                    group_split(paths,source_type="synthetic",seed=seed)
            for r in ((),(1,0,0),(0.6,.2,.3),(.5,.5)):
                with self.subTest(ratios=r), self.assertRaises(ValueError):
                    group_split(paths,source_type="synthetic",ratios=r)
            with self.assertRaises(ValueError):
                group_split(paths[:2],source_type="synthetic")
            with self.assertRaises(ValueError):
                group_split(paths,source_type="incorrect")

    def test_ims_three_whole_runs_keep_all_channels_and_unknown_labels(self):
        with TemporaryDirectory() as tmp:
            sources=ims_runs(Path(tmp))
            plan=group_split(sources,source_type="ims",seed=10)
            self.assertEqual(plan["source_type"],"user_supplied_local_ims_style")
            self.assertEqual([plan["partitions"][p]["groups"] for p in
                              ("train","validation","test")],[1,1,1])
            self.assertEqual(sum(p["records"] for p in plan["partitions"].values()),30)
            self.assertTrue(all(x["window_fault_labels"] is None for x in plan["sources"]))
            self.assertTrue(all(x["timestamp_timezone"]=="unknown" for x in plan["sources"]))
            self.assertTrue(all(x["publication_status"]=="local_only_do_not_redistribute"
                                for x in plan["sources"]))
            self.assertNotIn("record_hashes",json.dumps(plan))
            self.assertIn("test set",plan["group_boundary"])

    def test_ims_same_test_set_even_different_files_rejected(self):
        with TemporaryDirectory() as tmp:
            paths=ims_runs(Path(tmp))
            source=json.loads(paths[0].read_text(encoding="utf-8"))
            source["records"]=source["records"][:1]
            source["record_count"]=1
            source["channel_record_count"]=5
            duplicate=Path(tmp)/"partial.json"
            write_local_manifest(duplicate,source)
            with self.assertRaisesRegex(ValueError,"duplicate/overlapping"):
                group_split([paths[0],duplicate,paths[1]],source_type="ims")

    def test_ims_duplicate_record_digest_across_nominal_runs_rejected(self):
        with TemporaryDirectory() as tmp:
            paths=ims_runs(Path(tmp))
            a=json.loads(paths[0].read_text(encoding="utf-8"))
            b=json.loads(paths[1].read_text(encoding="utf-8"))
            b["records"][0]["sha256"]=a["records"][0]["sha256"]
            paths[1].write_text(json.dumps(b),encoding="utf-8")
            with self.assertRaisesRegex(ValueError,"identical raw-record SHA-256"):
                group_split(paths,source_type="ims")

    def test_ims_unknown_failure_truth_cannot_be_used_for_stratification(self):
        with TemporaryDirectory() as tmp:
            paths=ims_runs(Path(tmp))
            doc=json.loads(paths[0].read_text(encoding="utf-8"))
            doc["ground_truth"]["window_fault_label"]="bearing_fault"
            paths[0].write_text(json.dumps(doc),encoding="utf-8")
            with self.assertRaisesRegex(ValueError,"must not invent"):
                group_split(paths,source_type="ims")


class ChronologicalSplitTests(unittest.TestCase):
    def test_purged_boundaries_do_not_share_timestamps(self):
        with TemporaryDirectory() as tmp:
            path=synthetic_runs(Path(tmp),seeds=(42,),ticks=32)[0]
            plan=chronological_split(path)
            self.assertEqual(plan["policy"],"synthetic_chronological_exploratory")
            self.assertEqual(plan["purge_ticks"],4)
            p=plan["partitions"]
            self.assertLess(p["train"]["tick_end"]+4,p["validation"]["tick_start"])
            self.assertLess(p["validation"]["tick_end"]+4,p["test"]["tick_start"])
            total=sum(x["ticks"] for x in p.values())
            self.assertEqual(total+8,32)
            self.assertEqual(p["test"]["tick_end"],32)
            self.assertEqual(p["train"]["tick_start"],1)
            self.assertIn("NOT independent-run validation",plan["evaluation_warning"])
            self.assertTrue(plan["label_blind_assignment"])

    def test_short_runs_and_no_purge_rejected(self):
        with TemporaryDirectory() as tmp:
            small=synthetic_runs(Path(tmp),seeds=(7,),ticks=10)[0]
            with self.assertRaisesRegex(ValueError,"at least three"):
                chronological_split(small)
            big=synthetic_runs(Path(tmp),seeds=(8,),ticks=30)[0]
            for gap in (0,1,3,-1,True,4.5):
                with self.subTest(gap=gap), self.assertRaises(ValueError):
                    chronological_split(big,purge_ticks=gap)

    def test_subsecond_virtual_step_requires_larger_purge(self):
        with TemporaryDirectory() as tmp:
            p=Path(tmp)/"fast"
            export_dataset(p,ticks=60,step_seconds=.1)
            with self.assertRaisesRegex(ValueError,"purge_ticks must be >= 10"):
                chronological_split(p/"manifest.json",purge_ticks=4)
            plan=chronological_split(p/"manifest.json",purge_ticks=10)
            self.assertEqual(plan["minimum_purge_ticks"],10)
            self.assertEqual(plan["partitions"]["test"]["tick_end"],60)

    def test_chronological_manifest_replays_deterministically(self):
        with TemporaryDirectory() as tmp:
            p=synthetic_runs(Path(tmp),seeds=(10,),ticks=25)[0]
            one=chronological_split(p,ratios=(.5,.25,.25),purge_ticks=4)
            two=chronological_split(p,ratios=(.5,.25,.25),purge_ticks=4)
            self.assertEqual(one,two)
            self.assertEqual(one["plan_sha256"],two["plan_sha256"])


class SplitCommandTests(unittest.TestCase):
    def test_cli_group_and_chronological_write_once(self):
        with TemporaryDirectory() as tmp:
            root=Path(tmp)
            manifests=synthetic_runs(root,seeds=(1,2,3))
            env=dict(os.environ);env["PYTHONPATH"]=str(ROOT)
            grouped=root/"grouped.json"
            args=[sys.executable,"-m","motorpulse.splits","--source","synthetic",
                  "--input",*(str(x) for x in manifests),"--out",str(grouped)]
            result=subprocess.run(args,cwd=root,env=env,capture_output=True,text=True,timeout=30)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertEqual(json.loads(grouped.read_text())["policy"],"whole_run_grouped")
            again=subprocess.run(args,cwd=root,env=env,capture_output=True,text=True,timeout=30)
            self.assertEqual(again.returncode,2)
            self.assertIn("error:",again.stderr)
            chrono=root/"chronological.json"
            args=[sys.executable,"-m","motorpulse.splits","--source","synthetic",
                  "--input",str(manifests[0]),"--out",str(chrono),"--chronological"]
            result=subprocess.run(args,cwd=root,env=env,capture_output=True,text=True,timeout=30)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertEqual(json.loads(chrono.read_text())["policy"],
                             "synthetic_chronological_exploratory")

    def test_cli_prevents_ims_chronological_and_bad_group_flag(self):
        with TemporaryDirectory() as tmp:
            root=Path(tmp); paths=ims_runs(root)
            env=dict(os.environ);env["PYTHONPATH"]=str(ROOT)
            bad=root/"bad.json"
            args=[sys.executable,"-m","motorpulse.splits","--source","ims",
                  "--input",str(paths[0]),"--out",str(bad),"--chronological"]
            result=subprocess.run(args,cwd=root,env=env,capture_output=True,text=True,timeout=30)
            self.assertEqual(result.returncode,2)
            self.assertFalse(bad.exists())
            args=[sys.executable,"-m","motorpulse.splits","--source","ims",
                  "--input",*(str(p) for p in paths),"--out",str(bad),
                  "--purge-ticks","10"]
            result=subprocess.run(args,cwd=root,env=env,capture_output=True,text=True,timeout=30)
            self.assertEqual(result.returncode,2)
            self.assertFalse(bad.exists())


if __name__ == "__main__":
    unittest.main()
