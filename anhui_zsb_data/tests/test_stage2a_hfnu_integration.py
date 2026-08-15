from __future__ import annotations

import csv
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def read_csv(table: str) -> list[dict[str, str]]:
    path = ROOT / "normalized" / f"{table}.csv"
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


class Stage2AHfnuIntegrationTest(unittest.TestCase):
    def test_evidence_promotion_is_complete_and_hash_preserving(self) -> None:
        report = json.loads(
            (ROOT / "reports" / "stage2a_hfnu_evidence_integration.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertTrue(report["ok"])
        self.assertEqual(report["hfnu"]["source_count"], 8)
        self.assertEqual(report["hfnu"]["asset_count"], 26)
        self.assertEqual(report["hash_verification"], {"checked": 26, "mismatches": 0})
        self.assertFalse(report["scope"]["schema_modified"])
        self.assertFalse(report["scope"]["ahua_modified"])

    def test_stage2a_staging_files_are_hfnu_only_and_evidence_backed(self) -> None:
        files = sorted((ROOT / "staging" / "HFNU").rglob("stage2a_*.json"))
        self.assertEqual(len(files), 8)
        expected = {
            (2024, "application_statistics"),
            (2024, "syllabus"),
            (2024, "reference_books"),
            (2025, "syllabus"),
            (2025, "reference_books"),
            (2026, "admission_scores"),
            (2026, "syllabus"),
            (2026, "reference_books"),
        }
        observed = set()
        for path in files:
            payload = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(payload["schema_version"], "stage2a-hfnu-staging-v1")
            self.assertEqual(payload["school_id"], "HFNU")
            self.assertTrue(payload["source_id"].startswith("SRC-HFNU-"))
            self.assertTrue(payload["source_document_id"].startswith("DOC-HFNU-"))
            self.assertTrue(payload["source_asset_id"].startswith("ASSET-HFNU-"))
            self.assertGreater(len(payload["records"]), 0)
            for record in payload["records"]:
                self.assertTrue(record["source_locator"])
                self.assertTrue(record["source_quote"])
            observed.add((int(payload["year"]), payload["record_type"]))
        self.assertEqual(observed, expected)
        self.assertFalse((ROOT / "staging" / "AHUA").exists())

    def test_2026_scores_are_numeric_and_offering_linked(self) -> None:
        payload = json.loads(
            (
                ROOT
                / "staging"
                / "HFNU"
                / "2026"
                / "stage2a_admission_scores.json"
            ).read_text(encoding="utf-8")
        )
        self.assertGreater(len(payload["records"]), 0)
        ids = set()
        for record in payload["records"]:
            self.assertTrue(record["offering_id"])
            self.assertTrue(record["program_year_id"])
            self.assertGreaterEqual(float(record["score_value"]), 100)
            self.assertLessEqual(float(record["score_value"]), 999)
            self.assertNotIn(record["staging_id"], ids)
            ids.add(record["staging_id"])

    def test_application_statistics_and_reference_materials_are_nonempty(self) -> None:
        statistics = json.loads(
            (
                ROOT
                / "staging"
                / "HFNU"
                / "2024"
                / "stage2a_application_statistics.json"
            ).read_text(encoding="utf-8")
        )["records"]
        self.assertGreater(len(statistics), 0)
        self.assertTrue(all(int(row["applicant_count"]) > 0 for row in statistics))
        for year in (2024, 2025, 2026):
            syllabus = json.loads(
                (
                    ROOT
                    / "staging"
                    / "HFNU"
                    / str(year)
                    / "stage2a_syllabus.json"
                ).read_text(encoding="utf-8")
            )["records"]
            books = json.loads(
                (
                    ROOT
                    / "staging"
                    / "HFNU"
                    / str(year)
                    / "stage2a_reference_books.json"
                ).read_text(encoding="utf-8")
            )["records"]
            self.assertGreater(len(syllabus), 0)
            self.assertGreater(len(books), 0)
            self.assertTrue(all(row["exam_subject_id"] for row in syllabus))
            self.assertTrue(all(row["book_title"] for row in books))

    def test_canonical_extension_is_additive_and_stable_ids_pass(self) -> None:
        baseline = json.loads(
            (ROOT / "reports" / "stage2a_baseline.json").read_text(encoding="utf-8")
        )
        current = {
            table: len(read_csv(table))
            for table in (
                "admission_scores",
                "application_statistics",
                "syllabus",
                "reference_books",
                "fact_sources",
            )
        }
        self.assertGreater(
            current["admission_scores"], baseline["normalized_counts"]["admission_scores"]
        )
        self.assertGreater(current["application_statistics"], 0)
        self.assertGreater(current["syllabus"], 0)
        self.assertGreater(current["reference_books"], 0)
        self.assertGreater(current["fact_sources"], baseline["normalized_counts"]["fact_sources"])
        stable = json.loads(
            (ROOT / "reports" / "stage2a_stable_ids_verification.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertTrue(stable["ok"])
        self.assertEqual(stable["failures"], [])


if __name__ == "__main__":
    unittest.main()
