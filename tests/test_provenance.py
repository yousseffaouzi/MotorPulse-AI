"""MP-027 offline integrity checks for third-party dataset source cards.

These tests verify project documentation and conservative reuse policy;
they do NOT confer a license or access external datasets.
"""
from __future__ import annotations

from datetime import date
import json
from pathlib import Path
from urllib.parse import urlparse
import unittest

ROOT = Path(__file__).resolve().parents[1]
CARD = ROOT / "docs/sources/ims-bearings.source.json"
GUIDE = ROOT / "docs/DATA_PROVENANCE.md"


class IMSProvenanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.card = json.loads(CARD.read_text(encoding="utf-8"))
        cls.guide = GUIDE.read_text(encoding="utf-8")

    def test_source_card_is_well_formed_and_identifiable(self):
        self.assertEqual(self.card["schema_version"], "1.0.0")
        self.assertEqual(self.card["source_id"], "nasa-pcoe-ims-bearings")
        self.assertIn("IMS", self.card["title"])
        self.assertIn("experimental", self.card["source_kind"])
        self.assertTrue(self.card["attribution"]["original_provider"])
        self.assertTrue(self.card["attribution"]["distributor"])

    def test_review_date_and_unknown_acquisition_are_distinct(self):
        review = self.card["review"]
        self.assertEqual(date.fromisoformat(review["reviewed_on_utc"]),
                         date(2026, 10, 11))
        self.assertEqual(review["review_method"], "official_public_metadata_only")
        self.assertFalse(review["data_acquired"])
        self.assertFalse(review["archive_inspected"])
        self.assertFalse(review["rights_holder_contacted"])
        for key in ("raw_archive_sha256", "raw_archive_bytes", "acquisition_date_utc"):
            with self.subTest(key=key):
                self.assertIsNone(review[key], "Never fabricate an unmeasured acquisition fact")

    def test_primary_reference_urls_use_expected_official_hosts(self):
        urls = self.card["sources"]
        for key in ("nasa_pcoe_page", "nasa_open_data_page",
                    "nasa_catalog_page", "nasa_open_data_archive",
                    "nasa_pcoe_archive", "phm_society_mirror",
                    "nasa_data_license_guidance"):
            with self.subTest(key=key):
                url = urlparse(urls[key])
                self.assertEqual(url.scheme, "https")
                self.assertTrue(url.hostname)
                self.assertFalse(url.username)
                self.assertFalse(url.password)
                self.assertIn(url.hostname, {
                    "www.nasa.gov", "data.nasa.gov", "catalog.data.gov",
                    "phm-datasets.s3.amazonaws.com", "data.phmsociety.org",
                    "science.data.nasa.gov",
                })
                self.assertIn(urls[key], self.guide)
        self.assertEqual(urls["nasa_open_data_page"],
                         "https://data.nasa.gov/dataset/ims-bearings")

    def test_original_donor_and_citation_are_preserved(self):
        info = self.card["attribution"]
        self.assertIn("University of Cincinnati", info["original_provider"])
        self.assertIn("Rexnord", info["collaborating_contributor"])
        for important in ("J. Lee", "H. Qiu", "G. Yu", "J. Lin",
                          "Rexnord", "NASA Prognostics Data Repository"):
            with self.subTest(important=important):
                self.assertIn(important, info["upstream_citation"])
                self.assertIn(important, self.guide)

    def test_catalog_license_is_not_misrepresented_as_redistribution_grant(self):
        legal = self.card["license_and_use"]
        self.assertEqual(legal["catalog_license_label"], "other-license-specified")
        self.assertEqual(legal["catalog_metadata_license_url"],
                         "https://www.usa.gov/government-works")
        self.assertIsNone(legal["dataset_specific_spdx_license"])
        self.assertFalse(legal["archive_license_file_checked"])
        self.assertEqual(legal["redistribution_permission"], "unverified")
        self.assertEqual(legal["derivative_republication_permission"], "unverified")
        self.assertEqual(legal["clearance_status"], "hold")
        self.assertEqual(legal["clearance_contact_status"], "not_contacted")
        self.assertIn("not a legal ruling", self.guide)
        self.assertIn("not substitutes for a dataset-specific license", self.guide)

    def test_publication_policy_blocks_unreviewed_archives_and_derivatives(self):
        policy = self.card["publication_policy"]
        self.assertFalse(policy["bundle_original_archive"])
        self.assertFalse(policy["commit_raw_waveforms"])
        self.assertFalse(policy["publish_processed_reconstructable_waveforms"])
        self.assertEqual(policy["publish_derived_features"],
                         "pending_rights_and_provenance_review")
        self.assertTrue(policy["cite_upstream"])
        self.assertTrue(policy["refer_users_to_original_download_pages"])

    def test_unknown_physical_dataset_parameters_remain_null(self):
        observation = self.card["observations"]
        self.assertFalse(observation["archive_content_examined"])
        for key in ("sample_rate_hz", "samples_per_record", "channel_mapping",
                    "physical_unit", "test_set_count"):
            with self.subTest(key=key):
                self.assertIsNone(observation[key])
        checks = " ".join(observation["pending_checks"]).lower()
        for required in ("archive", "sample rate", "channel", "fault", "run"):
            self.assertIn(required, checks)
        self.assertIn("unknown", observation["labeling_basis"].lower())

    def test_raw_paths_ignored_without_ignoring_source_cards(self):
        ignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
        self.assertIn("data/raw/", ignore)
        self.assertIn("data/external/", ignore)
        self.assertNotIn("docs/sources/", ignore)
        self.assertNotIn("docs/DATA_PROVENANCE.md", ignore)

    def test_guide_covers_verification_and_nonleaky_splits(self):
        for part in ("sha256", "acquisition timestamp", "original", "bearing",
                     "metadata", "train", "license", "MP-009",
                     "MP-028", "local", "citation"):
            with self.subTest(part=part):
                self.assertIn(part.lower(), self.guide.lower())
        self.assertIn("No original archive has been downloaded", self.guide)
        self.assertIn("No contact has been made", self.guide)

    def test_project_readme_and_roadmap_link_guide(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        roadmap = (ROOT / "TODO.md").read_text(encoding="utf-8")
        self.assertIn("docs/DATA_PROVENANCE.md", readme)
        self.assertIn("| MP-027 | DONE |", roadmap)
        self.assertIn("MP-009", roadmap)
        self.assertIn("MP-028", roadmap)


if __name__ == "__main__":
    unittest.main()
