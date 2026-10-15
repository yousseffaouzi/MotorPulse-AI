"""MP-048 contracts for baseline model cards and failure-mode disclosure."""

from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
CARD_PATH = ROOT / "docs" / "MODEL_CARDS.md"


class ModelCardDocumentationTests(unittest.TestCase):
    def test_canonical_model_card_document_exists(self):
        self.assertTrue(CARD_PATH.is_file())
        text = CARD_PATH.read_text(encoding="utf-8")
        self.assertIn("# MotorPulse AI — Baseline model cards", text)
        self.assertIn("## Card 1 — Illustrative rule baseline", text)
        self.assertIn("## Card 2 — Healthy-trained anomaly baseline", text)

    def test_each_baseline_card_has_required_disclosure_sections(self):
        text = CARD_PATH.read_text(encoding="utf-8")
        cards = text.split("## Card ")[1:]
        self.assertEqual(len(cards), 2)
        required = (
            "### Source data",
            "### Intended use",
            "### Inputs and outputs",
            "### Validation evidence",
            "### Failure modes",
            "### Limitations and prohibited claims",
        )
        for card in cards:
            for heading in required:
                with self.subTest(card=card.splitlines()[0], heading=heading):
                    self.assertIn(heading, card)

    def test_rule_card_pins_thresholds_and_sensor_abstention(self):
        text = CARD_PATH.read_text(encoding="utf-8")
        rule = text.split("## Card 1 — Illustrative rule baseline", 1)[1].split(
            "## Card 2 — Healthy-trained anomaly baseline", 1
        )[0]
        for contract in (
            "`rms_g >= 0.36`",
            "`temperature_c >= 82.0`",
            "`crest_factor >= 2.7`",
            "`rms_g >= 0.20`",
            "`rms_g >= 0.55`",
            "`temperature_c >= 92.0`",
            'sensor_quality="missing"',
            'sensor_quality="outlier"',
            "not trained",
        ):
            with self.subTest(contract=contract):
                self.assertIn(contract, rule)

    def test_anomaly_card_pins_training_features_threshold_and_claim_limits(self):
        text = CARD_PATH.read_text(encoding="utf-8")
        anomaly = text.split("## Card 2 — Healthy-trained anomaly baseline", 1)[1]
        for contract in (
            "`rms_g`",
            "`crest_factor`",
            "`band_80_400_rms_g`",
            "`temperature_c`",
            "`rpm`",
            "whole_run_grouped",
            "healthy",
            'sensor_quality="good"',
            "99th percentile",
            "`score > threshold`",
            "MP-011",
            "failure probability",
            "remaining useful life",
        ):
            with self.subTest(contract=contract):
                self.assertIn(contract, anomaly)

    def test_cards_explicitly_state_no_rul_model_exists(self):
        text = CARD_PATH.read_text(encoding="utf-8")
        self.assertIn("No RUL model exists in MotorPulse AI", text)
        self.assertIn("RUL_RESEARCH.md", text)
        self.assertIn("metadata-only", text)
        self.assertIn("no predictions", text)


if __name__ == "__main__":
    unittest.main()
