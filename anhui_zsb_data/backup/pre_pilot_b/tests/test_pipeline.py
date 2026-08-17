from __future__ import annotations

import csv
import json
import sqlite3
import subprocess
import sys
import unittest
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from build_normalized import CanonicalBuilder  # noqa: E402
from common import (  # noqa: E402
    NORMALIZED_DIR,
    PLAN_FIELDS,
    canonical_file_hashes,
    load_json,
    parse_score,
    sha256_file,
    stable_id,
)
from pipeline import run_pipeline  # noqa: E402
from validate import Validator  # noqa: E402


def read_csv(name: str) -> list[dict[str, str]]:
    with (NORMALIZED_DIR / name).open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


class PipelineTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        result = run_pipeline(strict_state=True)
        if result != 0:
            raise RuntimeError("Pipeline did not pass before tests")

    def test_core_counts(self) -> None:
        expected = {
            "institutions.csv": 5,
            "program_years.csv": 82,
            "program_offerings.csv": 89,
            "enrollment_plans.csv": 356,
            "exam_subjects.csv": 328,
            "exam_sessions.csv": 246,
            "major_eligibility.csv": 82,
            "eligibility_rule_sets.csv": 82,
            "eligibility_rule_items.csv": 295,
            "admission_scores.csv": 305,
            "admission_rules.csv": 15,
            "fact_sources.csv": 1585,
        }
        self.assertEqual({name: len(read_csv(name)) for name in expected}, expected)

    def test_yearly_counts(self) -> None:
        expected = {
            "program_years.csv": {2024: 28, 2025: 28, 2026: 26},
            "program_offerings.csv": {2024: 30, 2025: 31, 2026: 28},
            "exam_subjects.csv": {2024: 112, 2025: 112, 2026: 104},
            "exam_sessions.csv": {2024: 84, 2025: 84, 2026: 78},
            "major_eligibility.csv": {2024: 28, 2025: 28, 2026: 26},
        }
        for filename, expected_counts in expected.items():
            counts = Counter(int(row["year"]) for row in read_csv(filename))
            self.assertEqual(dict(counts), expected_counts, filename)

    def test_plan_slots_and_business_english_regression(self) -> None:
        plans = read_csv("enrollment_plans.csv")
        offerings = read_csv("program_offerings.csv")
        programs = {row["program_year_id"]: row for row in read_csv("program_years.csv")}
        offering_by_id = {row["offering_id"]: row for row in offerings}

        self.assertEqual(len(plans), len(offerings) * len(PLAN_FIELDS))
        self.assertEqual(
            Counter(row["value_status"] for row in plans),
            Counter({"explicit_value": 335, "blank_in_source": 21}),
        )
        by_offering = Counter(row["offering_id"] for row in plans)
        self.assertTrue(all(count == 4 for count in by_offering.values()))

        rows = [
            row
            for row in plans
            if row["plan_type"] == "retired_soldier_non_exempt"
            and offering_by_id[row["offering_id"]]["year"] == "2026"
            and programs[offering_by_id[row["offering_id"]]["program_year_id"]]["major_name_std"] == "商务英语"
        ]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["plan_value"], "1")
        self.assertEqual(rows[0]["value_status"], "explicit_value")

    def test_eligibility_exact_coverage_and_foreign_keys(self) -> None:
        programs = read_csv("program_years.csv")
        eligibility = read_csv("major_eligibility.csv")
        program_ids = {row["program_year_id"] for row in programs}
        self.assertTrue(all(row["program_year_id"] in program_ids for row in eligibility))

        program_sets: dict[int, set[str]] = defaultdict(set)
        eligibility_sets: dict[int, set[str]] = defaultdict(set)
        for row in programs:
            program_sets[int(row["year"])].add(row["major_name_std"])
        for row in eligibility:
            eligibility_sets[int(row["year"])].add(row["undergraduate_major_std"])
        self.assertEqual(program_sets, eligibility_sets)
        self.assertIn("制药工程", eligibility_sets[2025])
        self.assertIn("新能源材料与器件", eligibility_sets[2025])
        self.assertIn("新能源材料与器件", eligibility_sets[2026])
        self.assertNotIn("材料科学与工程", eligibility_sets[2026])
        self.assertNotIn("数据科学与大数据技术", eligibility_sets[2026])

    def test_score_matrix_ids_and_numeric_values(self) -> None:
        scores = read_csv("admission_scores.csv")
        self.assertEqual(len({row["admission_score_id"] for row in scores}), len(scores))
        natural_keys = {
            (
                row["offering_id"],
                row["candidate_category"],
                row["score_metric"],
                row["admission_round"],
            )
            for row in scores
        }
        self.assertEqual(len(natural_keys), len(scores))
        self.assertEqual(
            Counter(row["value_status"] for row in scores),
            Counter({"published_value": 200, "blank_in_source": 105}),
        )
        counts = Counter(row["offering_id"] for row in scores)
        self.assertTrue(all(count == 5 for count in counts.values()))
        for row in scores:
            if row["value_status"] == "published_value":
                float(row["score_value_numeric"])
            else:
                self.assertEqual(row["score_value_numeric"], "")

    def test_score_parser(self) -> None:
        parsed = parse_score("364(专业课1:69)")
        self.assertEqual(parsed["score_value_numeric"], "364")
        detail = json.loads(parsed["threshold_detail_json"])
        self.assertEqual(detail["tie_break_metric"], "professional_1")
        self.assertEqual(detail["tie_break_score"], "69")
        self.assertEqual(parse_score("472.5")["score_value_numeric"], "472.5")
        self.assertEqual(parse_score("472.5")["threshold_detail_json"], "")

    def test_main_school_training_semantics(self) -> None:
        main_rows = [row for row in read_csv("program_offerings.csv") if row["training_type"] == "main_school"]
        self.assertTrue(main_rows)
        self.assertTrue(all(row["training_campus"] == "" for row in main_rows))
        self.assertTrue(all(row["training_campus_status"] == "not_published" for row in main_rows))
        self.assertTrue(all("校本部" not in row["remarks_source_raw"] for row in main_rows))

    def test_exam_session_model(self) -> None:
        sessions = read_csv("exam_sessions.csv")
        by_program = Counter(row["program_year_id"] for row in sessions)
        self.assertTrue(all(count == 3 for count in by_program.values()))
        professional = [row for row in sessions if row["session_type"] == "professional_combined"]
        self.assertTrue(all(row["duration_minutes"] == "180" for row in professional))
        published_sites = [row for row in professional if row["year"] in {"2025", "2026"}]
        self.assertTrue(all(row["exam_site_raw"] == "合肥师范学院锦绣校区" for row in published_sites))
        self.assertTrue(all(row["exam_site_status"] == "published" for row in published_sites))

    def test_source_assets_hashes_and_all_locators_resolve(self) -> None:
        assets = {row["asset_id"]: row for row in read_csv("source_assets.csv")}
        documents = {row["source_document_id"]: row for row in read_csv("source_documents.csv")}
        self.assertEqual(len(assets), 3)
        for asset in assets.values():
            path = ROOT / asset["local_path"]
            self.assertTrue(path.is_file(), asset["local_path"])
            self.assertEqual(str(path.stat().st_size), asset["file_size"])
            self.assertEqual(sha256_file(path), asset["sha256"])

        locator_tables = (
            "program_years.csv",
            "program_offerings.csv",
            "enrollment_plans.csv",
            "exam_subjects.csv",
            "exam_sessions.csv",
            "major_eligibility.csv",
            "eligibility_rule_sets.csv",
            "admission_scores.csv",
            "admission_rules.csv",
        )
        checked = 0
        for filename in locator_tables:
            for row in read_csv(filename):
                locator = json.loads(row["source_locator"])
                self.assertIsInstance(locator, dict)
                if "asset_id" in locator:
                    self.assertIn(locator["asset_id"], assets)
                    self.assertEqual(assets[locator["asset_id"]]["source_document_id"], row["source_id"])
                else:
                    self.assertEqual(locator.get("url"), documents[row["source_id"]]["url"])
                checked += 1
        self.assertEqual(checked, 1585)

    def test_fact_source_links_are_complete(self) -> None:
        specs = {
            "program_years": ("program_years.csv", "program_year_id"),
            "program_offerings": ("program_offerings.csv", "offering_id"),
            "enrollment_plans": ("enrollment_plans.csv", "enrollment_plan_id"),
            "exam_subjects": ("exam_subjects.csv", "exam_subject_id"),
            "exam_sessions": ("exam_sessions.csv", "exam_session_id"),
            "major_eligibility": ("major_eligibility.csv", "eligibility_id"),
            "eligibility_rule_sets": ("eligibility_rule_sets.csv", "eligibility_rule_set_id"),
            "admission_scores": ("admission_scores.csv", "admission_score_id"),
            "admission_rules": ("admission_rules.csv", "rule_id"),
        }
        expected = {
            (table, row[pk])
            for table, (filename, pk) in specs.items()
            for row in read_csv(filename)
        }
        actual = {(row["table_name"], row["record_id"]) for row in read_csv("fact_sources.csv")}
        self.assertEqual(actual, expected)

    def test_canonical_manifest_has_no_ghost_tables(self) -> None:
        manifest = load_json(ROOT / "schema" / "canonical_tables.json")
        expected = set(manifest["canonical_tables"] + manifest.get("compatibility_exports", []))
        actual = {path.name for path in NORMALIZED_DIR.glob("*.csv")}
        self.assertEqual(actual, expected)
        self.assertFalse((NORMALIZED_DIR / "school_major_years.csv").exists())
        self.assertFalse((NORMALIZED_DIR / "source_inventory.csv").exists())

    def test_sqlite_integrity_and_views(self) -> None:
        db_path = ROOT / "db" / "anhui_zsb.sqlite"
        self.assertTrue(db_path.is_file())
        connection = sqlite3.connect(db_path)
        try:
            self.assertEqual(connection.execute("PRAGMA foreign_key_check").fetchall(), [])
            self.assertEqual(connection.execute("PRAGMA user_version").fetchone()[0], 300)
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM program_years").fetchone()[0], 82)
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM fact_sources").fetchone()[0], 1585)
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM v_program_offerings").fetchone()[0], 89)
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM v_published_admission_scores").fetchone()[0], 200)
        finally:
            connection.close()

    def test_stable_ids_and_idempotent_canonical_build(self) -> None:
        self.assertEqual(stable_id("TEST", "HFNU", 2026, "商务英语"), stable_id("TEST", "HFNU", 2026, "商务英语"))
        manifest = load_json(ROOT / "schema" / "canonical_tables.json")
        paths = [NORMALIZED_DIR / name for name in manifest["canonical_tables"] + manifest.get("compatibility_exports", [])]
        paths.append(ROOT / "raw_manifest.csv")
        before = canonical_file_hashes(paths)
        CanonicalBuilder().build()
        after = canonical_file_hashes(paths)
        self.assertEqual(after, before)

    def test_validator_and_staging_verifier(self) -> None:
        result = Validator(strict_state=True).run()
        self.assertTrue(result.ok, result.errors)
        self.assertEqual(result.errors, [])
        process = subprocess.run(
            [sys.executable, "extract.py"],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(process.returncode, 0, process.stdout + process.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)
