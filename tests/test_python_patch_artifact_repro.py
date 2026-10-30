"""MP-056 portable-artifact reproducibility across Python patch releases."""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from motorpulse.anomaly import train_baseline
from motorpulse.export import export_dataset
from motorpulse.model_artifact import build_model_artifact
from motorpulse.splits import group_split


class PythonPatchArtifactReproTests(unittest.TestCase):
    def test_same_python_major_minor_ignores_patch_version(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifests = []
            for seed in (11, 22, 33):
                folder = root / f"run-{seed}"
                export_dataset(folder, seed=seed, ticks=12, file_format="jsonl")
                manifests.append(folder / "manifest.json")

            plan = group_split(manifests, source_type="synthetic", seed=42)
            model = train_baseline(plan, manifests)

            with patch("motorpulse.model_artifact.sys.version_info", (3, 13, 16)):
                first = build_model_artifact(plan, manifests, model)
            with patch("motorpulse.model_artifact.sys.version_info", (3, 13, 17)):
                second = build_model_artifact(plan, manifests, model)

            self.assertEqual(first, second)
            self.assertEqual(first["runtime"]["python_version"], "3.13")
            self.assertEqual(first["artifact_sha256"], second["artifact_sha256"])


if __name__ == "__main__":
    unittest.main()
