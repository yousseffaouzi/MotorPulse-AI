from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from motorpulse import physical_offline_trainer as trainer
from motorpulse import physical_validation_scorer as validation
from motorpulse.physical_feature_snapshot import snapshot_features
from test_physical_final_test_scorer import _approved


class PhysicalFeatureSnapshotTests(unittest.TestCase):
    def test_nested_scope_reuses_copies_and_cleans_up_on_error(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            sources = [root / f"{i}.jsonl" for i in range(3)]
            for path in sources:
                path.write_bytes(b"fixture")
            captured = []
            with self.assertRaisesRegex(RuntimeError, "fixture error"):
                with snapshot_features(sources) as outer:
                    captured.extend(outer)
                    with snapshot_features(outer) as inner:
                        self.assertEqual(inner, outer)
                        self.assertIsNot(inner, outer)
                        with self.assertRaisesRegex(ValueError, "size limit"):
                            with snapshot_features(inner, max_bytes=1):
                                self.fail("limit bypass")
                    raise RuntimeError("fixture error")
            self.assertTrue(all(not path.exists() for path in captured))
            with snapshot_features(sources) as fresh:
                self.assertNotEqual(fresh, captured)

    def test_training_uses_captured_bytes_after_approval(self):
        with TemporaryDirectory() as tmp:
            _, _, _, chain, sources = _approved(Path(tmp))
            original = sources[4][0]
            validate = trainer.validate_approval_record

            def change_source(*args):
                validate(*args)
                original.write_bytes(original.read_bytes() + b" ")

            with patch.object(
                trainer, "validate_approval_record", side_effect=change_source
            ):
                actual = trainer.train_physical_model(*chain[5:])
            self.assertEqual(actual, chain[4])
            with self.assertRaises(ValueError):
                trainer.train_physical_model(*chain[5:])

    def test_validation_uses_captured_bytes_after_approval(self):
        with TemporaryDirectory() as tmp:
            _, _, _, chain, sources = _approved(Path(tmp))
            original = sources[4][0]
            validate = validation.validate_evaluation_approval_record

            def change_source(*args):
                validate(*args)
                original.write_bytes(original.read_bytes() + b" ")

            with patch.object(
                validation,
                "validate_evaluation_approval_record",
                side_effect=change_source,
            ):
                actual = validation.score_physical_validation(*chain[1:])
            self.assertEqual(actual, chain[0])
            with self.assertRaises(ValueError):
                validation.score_physical_validation(*chain[1:])

    def test_standalone_replay_uses_same_captured_bytes(self):
        with TemporaryDirectory() as tmp:
            _, _, _, chain, sources = _approved(Path(tmp))
            original = sources[4][0]
            raw = original.read_bytes()
            validate = trainer.validate_approval_record

            def change_source(*args):
                validate(*args)
                original.write_bytes(raw + b" ")

            with patch.object(
                trainer, "validate_approval_record", side_effect=change_source
            ):
                trainer.validate_physical_model(chain[4], *chain[5:])
            with self.assertRaises(ValueError):
                trainer.validate_physical_model(chain[4], *chain[5:])
            original.write_bytes(raw)
            validate_evaluation = validation.validate_evaluation_approval_record

            def change_validation_source(*args):
                validate_evaluation(*args)
                original.write_bytes(raw + b" ")

            with patch.object(
                validation,
                "validate_evaluation_approval_record",
                side_effect=change_validation_source,
            ):
                validation.validate_physical_validation_result(*chain)
            with self.assertRaises(ValueError):
                validation.validate_physical_validation_result(*chain)


if __name__ == "__main__":
    unittest.main()
