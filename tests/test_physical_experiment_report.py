from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from motorpulse import physical_experiment_report as reporting
from motorpulse.physical_final_test_scorer import score_physical_final_test
from motorpulse.physical_training_approval_request import _sha
from test_physical_final_test_scorer import _approved


def _completed(root):
    record, request, decision, chain, sources = _approved(root)
    args = (record, request, decision, *chain)
    result = score_physical_final_test(*args)
    return result, args, sources


class PhysicalExperimentReportTests(unittest.TestCase):
    def test_summary_binds_exact_results_and_denominators(self):
        with TemporaryDirectory() as tmp:
            result, args, _ = _completed(Path(tmp))
            report = reporting.create_experiment_report(result, *args)
            self.assertEqual(report["final_test_result_sha256"], _sha(result))
            self.assertEqual(report["validation_result_sha256"], _sha(args[3]))
            for name, raw in (("validation", args[3]), ("test", result)):
                summary = report[name]
                counts = raw["counts"]
                scored = counts[f"{name}_rows_scored"]
                self.assertEqual(summary["windows_scored"], scored)
                self.assertEqual(summary["windows_total"], counts[f"{name}_rows_total"])
                self.assertEqual(
                    summary["windows_abstained"], counts[f"{name}_rows_abstained"]
                )
                self.assertEqual(summary["review_flags"], counts["review_flags"])
                self.assertEqual(
                    summary["review_flag_fraction_of_scored"],
                    counts["review_flags"] / scored,
                )
                self.assertLessEqual(summary["score_min"], summary["score_median"])
                self.assertLessEqual(summary["score_median"], summary["score_max"])
            self.assertIsNone(report["label_dependent_metrics"])
            self.assertIs(report["field_performance_validated"], False)
            self.assertIs(report["redistribution_cleared"], False)
            self.assertIs(report["deployment_authorized"], False)
            self.assertNotIn("input_frame_sha256", json.dumps(report))
            self.assertNotIn(tmp, json.dumps(report))

    def test_undefined_denominator_is_null(self):
        self.assertIsNone(reporting._rate(0, 0))
        summary = reporting._summary(
            {"rows": [{"status": "abstained", "score": None, "review_flag": None}]},
            [{"asset_id": "fixture"}],
        )
        self.assertIsNone(summary["review_flag_fraction_of_scored"])
        self.assertIsNone(summary["score_median"])
        self.assertEqual(summary["abstained_fraction_of_total"], 1)

    def test_forged_inputs_and_report_rejected(self):
        with TemporaryDirectory() as tmp:
            result, args, _ = _completed(Path(tmp))
            report = reporting.create_experiment_report(result, *args)
            with self.assertRaises(ValueError):
                reporting.create_experiment_report(
                    {**result, "deployment_authorized": True}, *args
                )
            with self.assertRaises(ValueError):
                reporting.validate_experiment_report(
                    {**report, "field_performance_validated": True}, result, *args
                )
            reporting.validate_experiment_report(report, result, *args)

    def test_markdown_and_write_once(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            result, args, _ = _completed(root)
            report = reporting.create_experiment_report(result, *args)
            text = reporting.render_markdown(report)
            self.assertIn("Flagged / scored", text)
            self.assertIn("not verified faults or false alarms", text)
            self.assertIn(report["final_test_result_sha256"], text)
            for kind in ("json", "markdown"):
                path = root / kind
                reporting.write_experiment_report(path, report, output_format=kind)
                with self.assertRaisesRegex(ValueError, "refusing to overwrite"):
                    reporting.write_experiment_report(path, report, output_format=kind)
            self.assertEqual(json.loads((root / "json").read_text()), report)
            self.assertEqual((root / "markdown").read_text(encoding="utf-8"), text)

    def test_source_order_and_byte_changes(self):
        with TemporaryDirectory() as tmp:
            result, args, sources = _completed(Path(tmp))
            first = reporting.create_experiment_report(result, *args)
            reordered = list(args)
            for index in (15, 16, 17):
                reordered[index] = list(reversed(reordered[index]))
            self.assertEqual(
                first, reporting.create_experiment_report(result, *reordered)
            )
            path = sources[4][0]
            path.write_bytes(path.read_bytes() + b" ")
            with self.assertRaises(ValueError):
                reporting.create_experiment_report(result, *args)

    def test_cli_with_exact_result(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            result, args, sources = _completed(root)
            names = (
                "final-test-result",
                "final-test-approval-record",
                "final-test-request",
                "final-test-decision",
                "validation-result",
                "evaluation-approval-record",
                "evaluation-request",
                "evaluation-decision",
                "model",
                "training-approval-record",
                "training-request",
                "training-decision",
                "preregistration",
                "bundle",
                "readiness",
                "split",
            )
            cli = []
            for name, value in zip(names, (result, *args[:15])):
                path = root / f"{name}.json"
                path.write_text(json.dumps(value), encoding="utf-8")
                cli.extend((f"--{name}", str(path)))
            protocol = root / "protocol.json"
            protocol.write_text(json.dumps(args[18]), encoding="utf-8")
            for name, entries in (
                ("card", sources[5]),
                ("review", sources[6]),
                ("feature", sources[4]),
            ):
                for path in entries:
                    cli.extend((f"--{name}", str(path)))
            output = root / "report.md"
            cli.extend(("--protocol", str(protocol), "--out", str(output)))
            cli.extend(("--format", "markdown"))
            self.assertEqual(reporting.main(cli), 0)
            expected = reporting.render_markdown(
                reporting.create_experiment_report(result, *args)
            )
            self.assertEqual(output.read_text(encoding="utf-8"), expected)


if __name__ == "__main__":
    unittest.main()
