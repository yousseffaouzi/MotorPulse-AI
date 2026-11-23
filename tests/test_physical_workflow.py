from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from motorpulse import physical_workflow as workflow
from motorpulse.physical_final_test_scorer import score_physical_final_test
from motorpulse.physical_training_approval_request import _sha
from test_physical_final_test_scorer import _approved


def _manifest(root: Path):
    record, request, decision, chain, sources = _approved(root)
    result = score_physical_final_test(record, request, decision, *chain)
    payloads = {
        "final_test_result": result,
        "final_test_approval_record": record,
        "final_test_request": request,
        "final_test_decision": decision,
    }
    for name, value in zip(
        (
            "validation_result",
            "evaluation_approval_record",
            "evaluation_request",
            "evaluation_decision",
            "model",
            "training_approval_record",
            "training_request",
            "training_decision",
            "preregistration",
            "bundle",
            "readiness",
            "split",
        ),
        chain[:12],
    ):
        payloads[name] = value
    payloads["protocol"] = chain[15]
    artifacts = {}
    for name, value in payloads.items():
        path = root / f"{name}.json"
        path.write_text(json.dumps(value), encoding="utf-8")
        artifacts[name] = path.name
    for name, paths in (
        ("cards", sources[5]),
        ("reviews", sources[6]),
        ("features", sources[4]),
    ):
        artifacts[name] = [str(path.relative_to(root)) for path in paths]
    manifest = root / "workflow.json"
    manifest.write_text(
        json.dumps(
            {"workflow_manifest_version": "1.0.0", "artifacts": artifacts}
        ),
        encoding="utf-8",
    )
    return manifest, artifacts, chain, result


class PhysicalWorkflowTests(unittest.TestCase):
    def test_all_four_explicit_stages_match_original_artifacts(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest, _, chain, final_result = _manifest(root)
            expected = {
                "train": chain[4],
                "validation": chain[0],
                "test": final_result,
            }
            for stage, original in expected.items():
                with self.subTest(stage=stage):
                    output = root / f"{stage}-output.json"
                    actual = workflow.run_workflow_stage(manifest, stage, output)
                    self.assertEqual(actual, original)
                    self.assertEqual(json.loads(output.read_text()), original)
            report = workflow.run_workflow_stage(
                manifest, "report", root / "report.json"
            )
            self.assertEqual(
                json.loads((root / "report.json").read_text()), report
            )
            self.assertEqual(report["final_test_result_sha256"], _sha(final_result))
            self.assertIsNone(report["label_dependent_metrics"])

    def test_missing_decision_never_calls_scoring(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest, artifacts, _, _ = _manifest(root)
            del artifacts["final_test_decision"]
            manifest.write_text(
                json.dumps(
                    {"workflow_manifest_version": "1.0.0", "artifacts": artifacts}
                ),
                encoding="utf-8",
            )
            with patch.object(workflow, "final_test_files") as score:
                with self.assertRaisesRegex(ValueError, "final_test_decision"):
                    workflow.run_workflow_stage(
                        manifest, "test", root / "no-approval.json"
                    )
                score.assert_not_called()
            self.assertFalse((root / "no-approval.json").exists())

    def test_generic_continue_cannot_authorize_scoring(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest, artifacts, _, _ = _manifest(root)
            path = root / artifacts["final_test_decision"]
            decision = json.loads(path.read_text())
            decision["human_affirmation"] = "continue"
            path.write_text(json.dumps(decision), encoding="utf-8")
            with self.assertRaises(ValueError):
                workflow.run_workflow_stage(
                    manifest, "test", root / "unapproved.json"
                )
            self.assertFalse((root / "unapproved.json").exists())

    def test_strict_manifest_schema_and_local_paths(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest, artifacts, _, _ = _manifest(root)
            for key, value in (
                ("workflow_manifest_version", "2.0.0"),
                ("artifacts", {**artifacts, "network_upload": "https://bad"}),
            ):
                invalid = {
                    "workflow_manifest_version": "1.0.0",
                    "artifacts": artifacts,
                }
                invalid[key] = value
                manifest.write_text(json.dumps(invalid), encoding="utf-8")
                with self.subTest(key=key), self.assertRaises(ValueError):
                    workflow.stage_paths(manifest, "train")
            artifacts["protocol"] = "https://example.com/protocol"
            manifest.write_text(
                json.dumps(
                    {"workflow_manifest_version": "1.0.0", "artifacts": artifacts}
                ),
                encoding="utf-8",
            )
            with self.assertRaises(ValueError):
                workflow.stage_paths(manifest, "train")

    def test_duplicate_manifest_keys_are_rejected(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "workflow.json"
            path.write_text(
                '{"workflow_manifest_version":"1.0.0",'
                '"workflow_manifest_version":"1.0.0","artifacts":{}}',
                encoding="utf-8",
            )
            with self.assertRaises(ValueError):
                workflow.stage_paths(path, "train")

    def test_write_once_and_markdown_restrictions(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest, _, _, _ = _manifest(root)
            output = root / "frozen-model.json"
            workflow.run_workflow_stage(manifest, "train", output)
            with self.assertRaisesRegex(ValueError, "refusing to overwrite"):
                workflow.run_workflow_stage(manifest, "train", output)
            with self.assertRaisesRegex(ValueError, "Markdown output"):
                workflow.run_workflow_stage(
                    manifest,
                    "train",
                    root / "wrong.md",
                    output_format="markdown",
                )

    def test_markdown_cli_and_stage_isolation(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest, _, _, _ = _manifest(root)
            output = root / "summary.md"
            with patch.object(
                workflow, "train_files", side_effect=AssertionError("new fit")
            ):
                self.assertEqual(
                    workflow.main(
                        [
                            "--stage", "report",
                            "--manifest", str(manifest),
                            "--out", str(output),
                            "--format", "markdown",
                        ]
                    ),
                    0,
                )
            summary = output.read_text(encoding="utf-8")
            self.assertIn("Physical experiment report", summary)
            self.assertIn("Flagged / scored", summary)

    def test_changed_source_bytes_rejected(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest, artifacts, _, _ = _manifest(root)
            path = root / artifacts["features"][0]
            path.write_bytes(path.read_bytes() + b" ")
            with self.assertRaises(ValueError):
                workflow.run_workflow_stage(
                    manifest, "report", root / "stale-report.json"
                )
            self.assertFalse((root / "stale-report.json").exists())


if __name__ == "__main__":
    unittest.main()
