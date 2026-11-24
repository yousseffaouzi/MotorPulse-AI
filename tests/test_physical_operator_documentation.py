"""MP-077 operator-guide and roadmap navigation contracts."""

from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]


class PhysicalOperatorDocumentationTests(unittest.TestCase):
    def test_operator_guide_links_resolve(self):
        guide = ROOT / "docs" / "PHYSICAL_OPERATOR_GUIDE.md"
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("docs/PHYSICAL_OPERATOR_GUIDE.md", readme)
        body = guide.read_text(encoding="utf-8")
        links = re.findall(r"\]\(([A-Z_]+\.md)\)", body)
        self.assertGreaterEqual(len(set(links)), 20)
        for target in links:
            with self.subTest(target=target):
                self.assertTrue((guide.parent / target).is_file())

    def test_guide_preserves_operator_boundaries(self):
        guide = ROOT / "docs" / "PHYSICAL_OPERATOR_GUIDE.md"
        body = guide.read_text(encoding="utf-8")
        for term in (
            "three distinct physical assets",
            "local_only_do_not_redistribute",
            "not real authorization",
            "256 MiB per file and 1 GiB per cohort",
            "not cryptographically sealed",
            "MP-016 remains ON HOLD",
            "--stage train",
            "--stage validation",
            "--stage test",
            "--stage report",
        ):
            with self.subTest(term=term):
                self.assertIn(term, " ".join(body.split()))

    def test_roadmap_includes_completed_physical_software(self):
        body = (ROOT / "TODO.md").read_text(encoding="utf-8")
        for number in range(57, 77):
            with self.subTest(number=number):
                self.assertEqual(body.count(f"| MP-{number:03d} | DONE |"), 1)
        self.assertIn("| MP-016 | ON HOLD |", body)
        self.assertIn("45294823494", body)
