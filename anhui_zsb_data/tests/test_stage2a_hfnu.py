from __future__ import annotations

import csv
import hashlib
import json
import re
import subprocess
import sys
import unittest
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from pipeline import run_pipeline  # noqa: E402


def read_csv(name: str) -> list[dict[str, str]]:
    with (ROOT / "normalized" / name).open(
        "r", encoding="utf-8-sig", newline=""
    ) as handle:
        return list(csv.DictReader(handle))


def load_json(relative: str) -> dict:
    with (ROOT / relative).open("r", encoding="utf-8") as handle:
        return json.load(handle)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class Stage2AHFNUIntegrationTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if run_pipeline(strict_state=True) != 0:
            raise RuntimeError("Stage 2A pipeline did not pass before tests")

    def test_evidence_raw_promotion_is_byte_identical_and_closed(self) -> None:
        mapping = load_json("config/stage2a_hfnu_asset_mapping.json")
        self.assertEqual(mapping["evidence_asset_count"], 26)
        self.assertEqual(mapping["promoted_count"], 26)
        self.assertEqual(mapping["not_promoted_count"], 0)
        self.assertEqual(mapping["sha_mismatch_count"], 0)
        self.assertEqual(mapping["unmanaged_raw_files"], [])
        self.assertEqual(
            (ROOT / "config/stage2a_hfnu_asset_mapping.json").read_bytes(),
            (ROOT / "reports/stage2a_hfnu_asset_mapping.json").read_bytes(),
        )

        for item in mapping["mapping"]:
            evidence = ROOT / item["evidence_path"]
            raw = ROOT / item["canonical_raw_path"]
            self.assertTrue(evidence.is_file(), item["evidence_path"])
            self.assertTrue(raw.is_file(), item["canonical_raw_path"])
            self.assertEqual(evidence.stat().st_size, raw.stat().st_size)
            self.assertEqual(sha256(evidence), item["evidence_sha256"])
            self.assertEqual(sha256(raw), item["canonical_sha256"])
            self.assertEqual(sha256(evidence), sha256(raw))

        self.assertFalse((ROOT / "raw/2024/AHUA").exists())
        self.assertFalse((ROOT / "raw/2025/AHUA").exists())
        self.assertFalse((ROOT / "raw/2026/AHUA").exists())

        configured = load_json("config/source_assets.json")["assets"]
        configured_paths = {item["local_path"] for item in configured}
        raw_paths = {
            path.relative_to(ROOT).as_posix()
            for path in (ROOT / "raw").rglob("*")
            if path.is_file()
        }
        self.assertEqual(raw_paths, configured_paths)
        self.assertEqual(len(raw_paths), 29)

    def test_promotion_and_staging_tools_are_reproducible(self) -> None:
        commands = (
            [sys.executable, "scripts/promote_hfnu_evidence.py", "--check"],
            [sys.executable, "scripts/build_stage2a_hfnu_staging.py", "--check"],
        )
        for command in commands:
            process = subprocess.run(
                command,
                cwd=ROOT,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(
                process.returncode,
                0,
                process.stdout + process.stderr,
            )

    def test_source_catalog_and_assets_are_formally_registered(self) -> None:
        documents = {
            row["source_document_id"]: row
            for row in read_csv("source_documents.csv")
        }
        assets = {row["asset_id"]: row for row in read_csv("source_assets.csv")}
        self.assertEqual(len(documents), 10)
        self.assertEqual(len(assets), 29)

        required_sources = {
            "SRC-HFNU-2024-BMRS",
            "SRC-HFNU-2024-DG",
            "SRC-HFNU-2024-LQ",
            "SRC-HFNU-2024-ZC",
            "SRC-HFNU-2025-DG",
            "SRC-HFNU-2025-LQ",
            "SRC-HFNU-2026-DG",
            "SRC-HFNU-2026-LQ",
        }
        self.assertTrue(required_sources <= set(documents))
        for source_id in required_sources:
            row = documents[source_id]
            self.assertEqual(row["status"], "verified")
            self.assertIn(row["primary_asset_id"], assets)
            self.assertEqual(
                assets[row["primary_asset_id"]]["source_document_id"], source_id
            )
        self.assertEqual(
            documents["SRC-HFNU-2026-LQ"]["primary_asset_id"],
            "ASSET-HFNU-2026-LQ-EMBEDDED-PDF",
        )
        for year in (2024, 2025, 2026):
            self.assertEqual(
                documents[f"SRC-HFNU-{year}-DG"]["primary_asset_id"],
                f"ASSET-HFNU-{year}-DG-PDF",
            )
        self.assertNotIn(
            "extracted_unarchived", {row["status"] for row in documents.values()}
        )
        for stable_asset in (
            "ASSET-HFNU-2025-ZC-PDF",
            "ASSET-HFNU-2025-ZC-PARSED-TXT",
            "ASSET-HFNU-2026-ZC-PDF",
        ):
            self.assertIn(stable_asset, assets)

    def test_existing_business_ids_and_rows_do_not_drift(self) -> None:
        self.assertEqual(
            (ROOT / "config/stage2a_baseline.json").read_bytes(),
            (ROOT / "reports/stage2a_baseline.json").read_bytes(),
        )
        self.assertEqual(
            (ROOT / "config/stage2a_stable_ids_baseline.json").read_bytes(),
            (ROOT / "reports/stage2a_stable_ids_baseline.json").read_bytes(),
        )
        baseline = load_json("config/stage2a_stable_ids_baseline.json")
        for table_name, table_baseline in baseline["tables"].items():
            current = {
                row[table_baseline["id_column"]]: row
                for row in read_csv(f"{table_name}.csv")
            }
            for item in table_baseline["rows"]:
                self.assertIn(item["id"], current, f"{table_name}:{item['id']}")
                self.assertEqual(
                    current[item["id"]],
                    item["row"],
                    f"stable row drift: {table_name}:{item['id']}",
                )

        report = load_json("reports/stage2a_hfnu_integration_report.json")
        self.assertEqual(report["stable_id"]["existing_id_drift_count"], 0)
        self.assertTrue(
            all(change["deleted"] == 0 for change in report["canonical_changes"].values())
        )
        self.assertEqual(
            report["canonical_changes"]["source_documents"],
            {"before": 5, "after": 10, "added": 5, "updated": 3, "deleted": 0},
        )
        self.assertEqual(
            report["canonical_changes"]["documents"],
            {"before": 5, "after": 10, "added": 5, "updated": 3, "deleted": 0},
        )
        self.assertEqual(
            report["stable_id"]["new_id_counts"],
            {
                "admission_scores": 140,
                "application_statistics": 30,
                "reference_books": 199,
                "syllabus": 164,
            },
        )

    def test_2026_admission_scores_use_official_pdf_and_preserve_blanks(self) -> None:
        staging_path = ROOT / "staging/HFNU/2026/admission_scores.json"
        self.assertTrue(staging_path.is_file())
        staging = load_json("staging/HFNU/2026/admission_scores.json")["data"]
        self.assertEqual(len(staging), 28)
        self.assertTrue(
            all(
                item["source_locator"]["asset_id"]
                == "ASSET-HFNU-2026-LQ-EMBEDDED-PDF"
                for item in staging
            )
        )
        self.assertEqual({item["source_locator"]["page"] for item in staging}, {1, 2})
        notes_by_major = {
            (item["major_name_raw"], item["source_locator"]["row_key"]): item["notes_raw"]
            for item in staging
        }
        self.assertIn("师范", notes_by_major[("学前教育", "学前教育|合肥师范学院")])
        self.assertEqual(
            notes_by_major[("财务管理", "财务管理|安徽工业经济职业技术学院")],
            "与安徽工业经济职业技术学院联合培养",
        )
        self.assertEqual(
            notes_by_major[("小学教育", "小学教育|淮北职业技术学院")],
            "师范；与淮北职业技术学院联合培养",
        )

        scores = [row for row in read_csv("admission_scores.csv") if row["year"] == "2026"]
        self.assertEqual(len(scores), 140)
        by_offering = Counter(row["offering_id"] for row in scores)
        self.assertEqual(len(by_offering), 28)
        self.assertTrue(all(count == 5 for count in by_offering.values()))
        for row in scores:
            self.assertEqual(row["source_id"], "SRC-HFNU-2026-LQ")
            locator = json.loads(row["source_locator"])
            self.assertEqual(locator["asset_id"], "ASSET-HFNU-2026-LQ-EMBEDDED-PDF")
            self.assertIn(locator["page"], {1, 2})
            if row["value_status"] == "blank_in_source":
                self.assertEqual(row["score_value_numeric"], "")
                self.assertEqual(row["score_raw"], "")
            else:
                self.assertEqual(row["value_status"], "published_value")
                float(row["score_value_numeric"])

    def test_syllabus_and_reference_books_map_to_professional_subjects(self) -> None:
        for year in (2024, 2025, 2026):
            self.assertTrue((ROOT / f"staging/HFNU/{year}/syllabus.json").is_file())
            self.assertTrue(
                (ROOT / f"staging/HFNU/{year}/reference_books.json").is_file()
            )

        programs = {row["program_year_id"]: row for row in read_csv("program_years.csv")}
        professional: dict[str, set[str]] = defaultdict(set)
        for row in read_csv("exam_subjects.csv"):
            if row["subject_slot"] in {"professional_1", "professional_2"}:
                professional[row["program_year_id"]].add(row["subject_id"])

        syllabus = read_csv("syllabus.csv")
        books = read_csv("reference_books.csv")
        self.assertEqual(len(syllabus), 164)
        self.assertEqual(len(books), 199)
        self.assertEqual(
            Counter(programs[row["program_year_id"]]["year"] for row in syllabus),
            Counter({"2024": 56, "2025": 56, "2026": 52}),
        )
        self.assertEqual(
            Counter(programs[row["program_year_id"]]["year"] for row in books),
            Counter({"2024": 70, "2025": 70, "2026": 59}),
        )
        for row in syllabus + books:
            self.assertIn(row["subject_id"], professional[row["program_year_id"]])
            year = programs[row["program_year_id"]]["year"]
            self.assertEqual(row["source_id"], f"SRC-HFNU-{year}-DG")
            locator = json.loads(row["source_locator"])
            self.assertEqual(locator["asset_id"], f"ASSET-HFNU-{year}-DG-PDF")
            self.assertTrue(locator.get("page"))
            self.assertTrue(locator.get("section"))
        self.assertTrue(all(row["book_name"] for row in books))
        self.assertTrue(all("http" not in row["book_name"].lower() for row in books))
        self.assertGreaterEqual(sum(bool(row["author"]) for row in books), 180)
        self.assertGreaterEqual(sum(bool(row["publisher"]) for row in books), 190)
        self.assertTrue(all(not row["publisher"] or row["publisher"].endswith("出版社") for row in books))

        bibliographic_samples = {
            row["book_name"]: (row["author"], row["publisher"])
            for row in books
            if row["book_name"] in {
                "基础会计",
                "管理学原理",
                "心理学",
                "速写",
                "康复功能评定学",
            }
        }
        self.assertEqual(bibliographic_samples["基础会计"][0], "张凤明、唐淑文编著")
        self.assertEqual(bibliographic_samples["管理学原理"][1], "中国人民大学出版社")
        self.assertEqual(bibliographic_samples["心理学"][0], "姚本先主编")
        self.assertEqual(bibliographic_samples["速写"][1], "辽宁美术出版社")
        self.assertEqual(bibliographic_samples["康复功能评定学"][1], "人民卫生出版社")

    def test_application_statistics_are_official_and_plan_reconciled(self) -> None:
        staging = load_json(
            "staging/HFNU/2024/application_statistics.json"
        )["data"]
        statistics = read_csv("application_statistics.csv")
        self.assertEqual(len(staging), 30)
        self.assertEqual(len(statistics), 30)
        offering_ids = {row["offering_id"] for row in read_csv("program_offerings.csv")}
        for row in statistics:
            self.assertIn(row["offering_id"], offering_ids)
            self.assertEqual(row["source_id"], "SRC-HFNU-2024-BMRS")
            self.assertGreaterEqual(int(row["applicant_count"]), 0)
            self.assertEqual(row["qualified_count"], "")
            self.assertEqual(row["admitted_count"], "")
            locator = json.loads(row["source_locator"])
            self.assertEqual(locator["asset_id"], "ASSET-HFNU-2024-BMRS-HTML")

        report = load_json(
            "reports/stage2a_hfnu_application_plan_reconciliation.json"
        )
        self.assertEqual(
            report["summary"],
            {
                "canonical_missing": 0,
                "conflict": 0,
                "consistent": 30,
                "official_missing": 0,
                "unmapped": 0,
            },
        )

    def test_fact_sources_and_sqlite_include_stage2a_tables(self) -> None:
        facts = {
            (row["table_name"], row["record_id"])
            for row in read_csv("fact_sources.csv")
        }
        specs = {
            "syllabus": ("syllabus.csv", "syllabus_id"),
            "reference_books": ("reference_books.csv", "reference_book_id"),
            "application_statistics": (
                "application_statistics.csv",
                "application_statistic_id",
            ),
        }
        for table_name, (filename, pk) in specs.items():
            for row in read_csv(filename):
                self.assertIn((table_name, row[pk]), facts)

        import sqlite3

        connection = sqlite3.connect(ROOT / "db/anhui_zsb.sqlite")
        try:
            self.assertEqual(connection.execute("PRAGMA foreign_key_check").fetchall(), [])
            for table_name, (filename, _pk) in specs.items():
                expected = len(read_csv(filename))
                actual = connection.execute(
                    f"SELECT COUNT(*) FROM {table_name}"
                ).fetchone()[0]
                self.assertEqual(actual, expected)
        finally:
            connection.close()

    def test_qa_and_progress_reflect_stage2a_without_claiming_completion(self) -> None:
        with (ROOT / "qa/missing_data.csv").open(
            "r", encoding="utf-8-sig", newline=""
        ) as handle:
            missing_rows = list(csv.DictReader(handle))
        self.assertEqual(len(missing_rows), 9)
        self.assertEqual(
            Counter(row["field_name"] for row in missing_rows),
            Counter(
                {
                    "adjustments": 3,
                    "application_statistics": 2,
                    "admission_scores": 4,
                }
            ),
        )
        state = load_json("progress/task_state.json")
        self.assertEqual(state["schema_version"], "0.3.0")
        self.assertEqual(state["run_mode"], "pilot")
        self.assertFalse(state["stages"]["batch_ready"])
        self.assertFalse(state["stages"]["source_fetch_complete"])
        self.assertEqual(state["partial_schools"], ["HFNU"])
        self.assertEqual(state["completed_schools"], [])
        self.assertEqual(state["stage"], "stage2a_hfnu_evidence_integration_complete")

        report = load_json("reports/stage2a_hfnu_integration_report.json")
        self.assertEqual(report["qa"]["p0"], 0)
        self.assertEqual(report["qa"]["p1"], 0)
        self.assertIn(report["tests"]["local_quality_gate"], {"PASS", "NOT_RUN"})
        self.assertEqual(report["tests"]["unit_tests"]["count"], 29)
        self.assertIn(
            report["tests"]["unit_tests"]["status"],
            {"PASS", "PENDING_CURRENT_GATE"},
        )
        self.assertIn(report["tests"]["idempotence"], {"PASS", "NOT_RUN"})
        self.assertIn(report["tests"]["clean_rebuild"], {"PASS", "NOT_RUN"})
        self.assertFalse(report["scope"]["ahua_canonical_written"])
        self.assertFalse(report["scope"]["batch_ready"])

    def test_no_candidate_personal_records_were_introduced(self) -> None:
        chinese_id = re.compile(r"(?<!\d)\d{17}[\dXx](?!\d)")
        phone = re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)")
        candidate_list = re.compile(
            r"(?:身份证号|考生号|准考证号).{0,80}(?:身份证号|考生号|准考证号)",
            re.S,
        )
        roots = [
            ROOT / "raw",
            ROOT / "staging/HFNU",
            ROOT / "normalized",
            ROOT / "reports",
        ]
        checked = 0
        for root in roots:
            for path in root.rglob("*"):
                if not path.is_file() or path.suffix.lower() not in {
                    ".txt",
                    ".html",
                    ".json",
                    ".csv",
                    ".md",
                }:
                    continue
                data = path.read_bytes()
                text = None
                for encoding in ("utf-8-sig", "utf-8", "gb18030"):
                    try:
                        text = data.decode(encoding)
                        break
                    except UnicodeDecodeError:
                        continue
                if text is None:
                    continue
                self.assertIsNone(chinese_id.search(text), path.relative_to(ROOT))
                self.assertIsNone(phone.search(text), path.relative_to(ROOT))
                self.assertIsNone(candidate_list.search(text), path.relative_to(ROOT))
                checked += 1
        self.assertGreater(checked, 50)


if __name__ == "__main__":
    unittest.main(verbosity=2)
