#!/usr/bin/env python3
"""Validate canonical data, provenance and pipeline state.

Exit status is non-zero when any P0 error is found. The module can also be
imported by tests and report generation.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

from common import (
    BASE_DIR,
    NORMALIZED_DIR,
    PLAN_FIELDS,
    PROGRESS_DIR,
    REPORTS_DIR,
    SCORE_FIELDS,
    SCHEMA_DIR,
    SCHEMA_VERSION,
    YEARS,
    load_json,
    read_csv,
    sha256_file,
)


@dataclass
class ValidationResult:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    info: list[str] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return not self.errors

    def error(self, message: str) -> None:
        self.errors.append(message)

    def warning(self, message: str) -> None:
        self.warnings.append(message)

    def note(self, message: str) -> None:
        self.info.append(message)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "p0_error_count": len(self.errors),
            "p1_warning_count": len(self.warnings),
            "errors": self.errors,
            "warnings": self.warnings,
            "info": self.info,
            "metrics": self.metrics,
        }


class Validator:
    def __init__(self, *, strict_state: bool = False) -> None:
        self.strict_state = strict_state
        self.result = ValidationResult()
        self.tables: dict[str, list[dict[str, str]]] = {}

    def _load(self, filename: str, required: bool = True) -> list[dict[str, str]]:
        if filename in self.tables:
            return self.tables[filename]
        path = NORMALIZED_DIR / filename
        if not path.exists():
            if required:
                self.result.error(f"Missing canonical file: normalized/{filename}")
            rows: list[dict[str, str]] = []
        else:
            rows = read_csv(path)
        self.tables[filename] = rows
        return rows

    def _unique(self, filename: str, key: str) -> None:
        rows = self._load(filename)
        values = [row.get(key, "") for row in rows]
        blanks = sum(not value for value in values)
        duplicates = [value for value, count in Counter(values).items() if value and count > 1]
        if blanks:
            self.result.error(f"{filename}.{key} has {blanks} blank primary keys")
        if duplicates:
            self.result.error(f"{filename}.{key} has {len(duplicates)} duplicate values")
        else:
            self.result.note(f"PK unique: {filename}.{key} ({len(rows)} rows)")

    def _fk(self, child_file: str, child_key: str, parent_file: str, parent_key: str, *, allow_blank: bool = False) -> None:
        child = self._load(child_file)
        parent = self._load(parent_file)
        parent_values = {row[parent_key] for row in parent if row.get(parent_key)}
        blank = [row for row in child if not row.get(child_key)]
        orphan = [row for row in child if row.get(child_key) and row[child_key] not in parent_values]
        if blank and not allow_blank:
            self.result.error(f"{child_file}.{child_key} has {len(blank)} blank foreign keys")
        if orphan:
            self.result.error(f"{child_file}.{child_key} has {len(orphan)} orphan foreign keys")
        if not blank and not orphan:
            self.result.note(f"FK valid: {child_file}.{child_key} -> {parent_file}.{parent_key}")

    def check_manifest(self) -> None:
        manifest = read_csv(BASE_DIR / "raw_manifest.csv")
        if not manifest:
            self.result.error("raw_manifest.csv is missing or empty")
            return
        for row in manifest:
            path = BASE_DIR / row["local_path"]
            if not path.exists():
                self.result.error(f"Raw asset path does not exist: {row['local_path']}")
                continue
            actual_size = str(path.stat().st_size)
            actual_hash = sha256_file(path)
            if actual_size != row["file_size"]:
                self.result.error(f"File-size mismatch: {row['local_path']}")
            if actual_hash != row["sha256"]:
                self.result.error(f"SHA-256 mismatch: {row['local_path']}")
        normalized_assets = read_csv(NORMALIZED_DIR / "source_assets.csv")
        manifest_by_id = {row.get("asset_id", ""): row for row in manifest}
        normalized_by_id = {row.get("asset_id", ""): row for row in normalized_assets}
        if set(manifest_by_id) != set(normalized_by_id):
            self.result.error("raw_manifest.csv and normalized/source_assets.csv contain different asset IDs")
        else:
            comparable = ("source_document_id", "local_path", "file_size", "sha256", "parent_asset_id")
            mismatches = 0
            for asset_id, manifest_row in manifest_by_id.items():
                normalized_row = normalized_by_id[asset_id]
                if any(manifest_row.get(field, "") != normalized_row.get(field, "") for field in comparable):
                    mismatches += 1
            if mismatches:
                self.result.error(f"raw_manifest.csv differs from source_assets.csv for {mismatches} assets")
        self.result.metrics["raw_asset_count"] = len(manifest)
        self.result.note(f"Raw manifest verified: {len(manifest)} assets")

    def check_sources(self) -> None:
        self._unique("source_sites.csv", "source_site_id")
        self._unique("source_documents.csv", "source_document_id")
        self._unique("source_assets.csv", "asset_id")
        self._fk("source_documents.csv", "source_site_id", "source_sites.csv", "source_site_id")
        self._fk("source_assets.csv", "source_document_id", "source_documents.csv", "source_document_id")

        assets = {row["asset_id"]: row for row in self._load("source_assets.csv")}
        for asset in assets.values():
            parent = asset.get("parent_asset_id", "")
            if parent and parent not in assets:
                self.result.error(f"Source asset parent_asset_id does not exist: {parent}")
        for document in self._load("source_documents.csv"):
            primary = document.get("primary_asset_id", "")
            if primary and primary not in assets:
                self.result.error(f"Source document primary_asset_id does not exist: {primary}")
            elif primary and assets[primary]["source_document_id"] != document["source_document_id"]:
                self.result.error(
                    f"Source document primary asset belongs to another document: {document['source_document_id']} -> {primary}"
                )
            if document["status"] == "verified" and not primary:
                self.result.error(f"Verified source has no primary asset: {document['source_document_id']}")

        for row in self._load("documents.csv"):
            local_path = row.get("local_path", "")
            if local_path and not (BASE_DIR / local_path).exists():
                self.result.error(f"Compatibility documents.csv path does not exist: {local_path}")

    def check_primary_and_foreign_keys(self) -> None:
        pk_specs = {
            "institutions.csv": "institution_id",
            "program_years.csv": "program_year_id",
            "program_offerings.csv": "offering_id",
            "enrollment_plans.csv": "enrollment_plan_id",
            "exam_subjects.csv": "exam_subject_id",
            "exam_sessions.csv": "exam_session_id",
            "major_eligibility.csv": "eligibility_id",
            "eligibility_rule_sets.csv": "eligibility_rule_set_id",
            "eligibility_rule_items.csv": "eligibility_rule_item_id",
            "admission_scores.csv": "admission_score_id",
            "admission_rules.csv": "rule_id",
            "fact_sources.csv": "fact_source_id",
        }
        for filename, key in pk_specs.items():
            self._unique(filename, key)

        fk_specs = (
            ("program_years.csv", "admission_school_id", "institutions.csv", "institution_id"),
            ("program_offerings.csv", "program_year_id", "program_years.csv", "program_year_id"),
            ("program_offerings.csv", "training_institution_id", "institutions.csv", "institution_id"),
            ("enrollment_plans.csv", "offering_id", "program_offerings.csv", "offering_id"),
            ("exam_subjects.csv", "program_year_id", "program_years.csv", "program_year_id"),
            ("exam_sessions.csv", "program_year_id", "program_years.csv", "program_year_id"),
            ("major_eligibility.csv", "program_year_id", "program_years.csv", "program_year_id"),
            ("eligibility_rule_sets.csv", "program_year_id", "program_years.csv", "program_year_id"),
            ("eligibility_rule_items.csv", "eligibility_rule_set_id", "eligibility_rule_sets.csv", "eligibility_rule_set_id"),
            ("admission_scores.csv", "offering_id", "program_offerings.csv", "offering_id"),
        )
        for spec in fk_specs:
            self._fk(*spec)

        source_ids = {row["source_document_id"] for row in self._load("source_documents.csv")}
        source_tables = (
            "program_years.csv",
            "program_offerings.csv",
            "enrollment_plans.csv",
            "exam_subjects.csv",
            "exam_sessions.csv",
            "major_eligibility.csv",
            "eligibility_rule_sets.csv",
            "admission_scores.csv",
            "admission_rules.csv",
            "fact_sources.csv",
        )
        for filename in source_tables:
            rows = self._load(filename)
            bad = [row for row in rows if not row.get("source_id") or row["source_id"] not in source_ids]
            if bad:
                self.result.error(f"{filename} has {len(bad)} invalid source_id values")

    def check_json_fields_and_locators(self) -> None:
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
        assets = {row["asset_id"]: row for row in self._load("source_assets.csv")}
        documents = {row["source_document_id"]: row for row in self._load("source_documents.csv")}
        total = 0
        blank = 0
        invalid = 0
        unresolved = 0
        mismatched = 0
        for filename in locator_tables:
            for row in self._load(filename):
                total += 1
                raw = row.get("source_locator", "")
                if not raw:
                    blank += 1
                    continue
                try:
                    parsed = json.loads(raw)
                    if not isinstance(parsed, dict):
                        invalid += 1
                        continue
                except json.JSONDecodeError:
                    invalid += 1
                    continue

                source_document_id = row.get("source_id", "")
                asset_id = parsed.get("asset_id")
                url = parsed.get("url")
                if asset_id:
                    asset = assets.get(str(asset_id))
                    if asset is None:
                        unresolved += 1
                    elif asset["source_document_id"] != source_document_id:
                        mismatched += 1
                elif url:
                    document = documents.get(source_document_id)
                    if document is None or document.get("url") != str(url):
                        mismatched += 1
                else:
                    unresolved += 1
        if blank:
            self.result.error(f"Core source_locator coverage is incomplete: {blank}/{total} blank")
        if invalid:
            self.result.error(f"Core source_locator has {invalid} invalid JSON values")
        if unresolved:
            self.result.error(f"Core source_locator has {unresolved} unresolved evidence pointers")
        if mismatched:
            self.result.error(f"Core source_locator has {mismatched} pointers not belonging to row.source_id")
        self.result.metrics["source_locator_coverage"] = 0 if not total else round((total - blank) / total, 6)
        self.result.metrics["source_locator_resolved"] = total - blank - invalid - unresolved - mismatched

        json_fields = (
            ("admission_scores.csv", "threshold_detail_json"),
            ("admission_rules.csv", "rule_structured_json"),
            ("exam_sessions.csv", "subject_slots_json"),
        )
        for filename, field_name in json_fields:
            invalid_values = 0
            for row in self._load(filename):
                raw = row.get(field_name, "")
                if not raw:
                    continue
                try:
                    json.loads(raw)
                except json.JSONDecodeError:
                    invalid_values += 1
            if invalid_values:
                self.result.error(f"{filename}.{field_name} has {invalid_values} invalid JSON values")

        # Institution addresses are also evidence-backed facts.
        for row in self._load("institutions.csv"):
            source = row.get("address_source_id", "")
            locator_raw = row.get("address_source_locator", "")
            if not row.get("address"):
                continue
            if not source or source not in documents:
                self.result.error(f"Institution address has invalid source: {row.get('institution_id')}")
                continue
            try:
                locator = json.loads(locator_raw)
            except json.JSONDecodeError:
                self.result.error(f"Institution address locator is invalid JSON: {row.get('institution_id')}")
                continue
            asset_id = locator.get("asset_id") if isinstance(locator, dict) else None
            if asset_id:
                asset = assets.get(str(asset_id))
                if asset is None or asset["source_document_id"] != source:
                    self.result.error(f"Institution address locator is unresolved: {row.get('institution_id')}")

    def check_hfnu_core_counts(self) -> None:
        expected = {
            "program_years.csv": {2024: 28, 2025: 28, 2026: 26},
            "program_offerings.csv": {2024: 30, 2025: 31, 2026: 28},
            "exam_subjects.csv": {2024: 112, 2025: 112, 2026: 104},
            "exam_sessions.csv": {2024: 84, 2025: 84, 2026: 78},
            "major_eligibility.csv": {2024: 28, 2025: 28, 2026: 26},
        }
        for filename, by_year_expected in expected.items():
            counts = Counter(int(row["year"]) for row in self._load(filename))
            for year, expected_count in by_year_expected.items():
                if counts[year] != expected_count:
                    self.result.error(f"{filename} {year} count={counts[year]}, expected={expected_count}")
            self.result.metrics[filename.removesuffix(".csv") + "_by_year"] = dict(sorted(counts.items()))

        plans = self._load("enrollment_plans.csv")
        offerings = self._load("program_offerings.csv")
        if len(plans) != len(offerings) * len(PLAN_FIELDS):
            self.result.error(f"Plan slot count mismatch: {len(plans)} != {len(offerings)} × {len(PLAN_FIELDS)}")
        plan_status = Counter(row["value_status"] for row in plans)
        if plan_status != Counter({"explicit_value": 335, "blank_in_source": 21}):
            self.result.error(f"Unexpected plan status distribution: {dict(plan_status)}")
        self.result.metrics["plan_status"] = dict(plan_status)

        offering_by_id = {row["offering_id"]: row for row in offerings}
        program_by_id = {row["program_year_id"]: row for row in self._load("program_years.csv")}
        business_rows = [
            row
            for row in plans
            if row["plan_type"] == "retired_soldier_non_exempt"
            and offering_by_id[row["offering_id"]]["year"] == "2026"
            and program_by_id[offering_by_id[row["offering_id"]]["program_year_id"]]["major_name_std"] == "商务英语"
        ]
        if len(business_rows) != 1 or business_rows[0]["plan_value"] != "1" or business_rows[0]["value_status"] != "explicit_value":
            self.result.error("2026 商务英语非免试退役士兵专项计划必须为官方值 1")

        main_offerings = [row for row in offerings if row["training_type"] == "main_school"]
        bad_campus = [row for row in main_offerings if row.get("training_campus")]
        if bad_campus:
            self.result.error(f"{len(bad_campus)} main-school offerings contain unsupported training_campus values")
        bad_raw = [row for row in main_offerings if "校本部" in row.get("remarks_source_raw", "")]
        if bad_raw:
            self.result.error(f"{len(bad_raw)} remarks_source_raw rows contain inferred text '校本部'")

    def check_eligibility_coverage(self) -> None:
        programs = self._load("program_years.csv")
        eligibility = self._load("major_eligibility.csv")
        program_sets: dict[int, set[str]] = defaultdict(set)
        eligibility_sets: dict[int, set[str]] = defaultdict(set)
        for row in programs:
            program_sets[int(row["year"])].add(row["major_name_std"])
        for row in eligibility:
            eligibility_sets[int(row["year"])].add(row["undergraduate_major_std"])
        for year in YEARS:
            missing = program_sets[year] - eligibility_sets[year]
            extra = eligibility_sets[year] - program_sets[year]
            if missing:
                self.result.error(f"{year} eligibility missing majors: {sorted(missing)}")
            if extra:
                self.result.error(f"{year} eligibility extra majors: {sorted(extra)}")

    def check_exam_and_score_matrix(self) -> None:
        subject_counts = Counter(row["program_year_id"] for row in self._load("exam_subjects.csv"))
        bad_subjects = {key: count for key, count in subject_counts.items() if count != 4}
        if bad_subjects:
            self.result.error(f"Programs without exactly 4 exam subjects: {len(bad_subjects)}")
        session_counts = Counter(row["program_year_id"] for row in self._load("exam_sessions.csv"))
        bad_sessions = {key: count for key, count in session_counts.items() if count != 3}
        if bad_sessions:
            self.result.error(f"Programs without exactly 3 exam sessions: {len(bad_sessions)}")

        scores = self._load("admission_scores.csv")
        score_counts = Counter(row["offering_id"] for row in scores)
        expected_score_offerings = {
            row["offering_id"] for row in self._load("program_offerings.csv") if int(row["year"]) in {2024, 2025}
        }
        missing_offerings = expected_score_offerings - set(score_counts)
        if missing_offerings:
            self.result.error(f"Admission score matrix missing {len(missing_offerings)} offerings")
        bad_counts = {key: value for key, value in score_counts.items() if value != len(SCORE_FIELDS)}
        if bad_counts:
            self.result.error(f"Admission score matrix does not have 5 categories for {len(bad_counts)} offerings")
        if len(scores) != 305:
            self.result.error(f"admission_scores row count={len(scores)}, expected=305")
        status = Counter(row["value_status"] for row in scores)
        if status != Counter({"published_value": 200, "blank_in_source": 105}):
            self.result.error(f"Unexpected admission score status distribution: {dict(status)}")
        self.result.metrics["admission_score_status"] = dict(status)
        for row in scores:
            value = row["score_value_numeric"]
            if row["value_status"] == "published_value":
                if not value:
                    self.result.error(f"Published score has blank numeric value: {row['admission_score_id']}")
                else:
                    try:
                        float(value)
                    except ValueError:
                        self.result.error(f"Non-numeric score: {row['admission_score_id']}={value!r}")
            elif value:
                self.result.error(f"Blank score status contains numeric value: {row['admission_score_id']}")

    def check_fact_sources(self) -> None:
        table_specs = {
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
        expected: dict[tuple[str, str], dict[str, str]] = {}
        for table_name, (filename, pk) in table_specs.items():
            for row in self._load(filename):
                expected[(table_name, row[pk])] = row

        rows = self._load("fact_sources.csv")
        seen: set[tuple[str, str, str]] = set()
        invalid = 0
        mismatched = 0
        for row in rows:
            key = (row.get("table_name", ""), row.get("record_id", ""))
            fact = expected.get(key)
            if fact is None:
                invalid += 1
                continue
            relation_key = (key[0], key[1], row.get("source_id", ""))
            if relation_key in seen:
                invalid += 1
            seen.add(relation_key)
            if row.get("source_id") != fact.get("source_id"):
                mismatched += 1
            if row.get("source_locator") != fact.get("source_locator"):
                mismatched += 1
        missing = set(expected) - {(row.get("table_name", ""), row.get("record_id", "")) for row in rows}
        if invalid:
            self.result.error(f"fact_sources.csv has {invalid} invalid or duplicate fact references")
        if mismatched:
            self.result.error(f"fact_sources.csv has {mismatched} source/locator mismatches")
        if missing:
            self.result.error(f"fact_sources.csv is missing evidence links for {len(missing)} facts")
        self.result.metrics["fact_source_count"] = len(rows)

    def check_no_legacy_canonical_files(self) -> None:
        manifest_path = SCHEMA_DIR / "canonical_tables.json"
        if not manifest_path.exists():
            self.result.error("schema/canonical_tables.json is missing")
            return
        manifest = load_json(manifest_path)
        if str(manifest.get("schema_version")) != SCHEMA_VERSION:
            self.result.error(
                f"Canonical manifest schema_version={manifest.get('schema_version')}, expected={SCHEMA_VERSION}"
            )
        expected = set(manifest.get("canonical_tables", [])) | set(manifest.get("compatibility_exports", []))
        actual = {path.name for path in NORMALIZED_DIR.glob("*.csv")}
        missing = sorted(expected - actual)
        unregistered = sorted(actual - expected)
        if missing:
            self.result.error(f"Canonical files missing from normalized/: {missing}")
        if unregistered:
            self.result.error(f"Unregistered/legacy CSV files remain in normalized/: {unregistered}")

        forbidden = {"school_major_years.csv", "source_inventory.csv"}
        remaining_forbidden = sorted(actual & forbidden)
        if remaining_forbidden:
            self.result.error(f"Legacy tables must not remain in normalized/: {remaining_forbidden}")
        id_mapping = list((BASE_DIR / "staging").rglob("id_mapping.json"))
        if id_mapping:
            self.result.error(f"Legacy id_mapping.json files still exist: {len(id_mapping)}")

    def check_state_consistency(self) -> None:
        progress_path = PROGRESS_DIR / "collection_progress.csv"
        task_state_path = PROGRESS_DIR / "task_state.json"
        report_path = REPORTS_DIR / "pilot_report.md"
        if not self.strict_state:
            return
        if not progress_path.exists():
            self.result.error("progress/collection_progress.csv is missing")
            return
        if not task_state_path.exists():
            self.result.error("progress/task_state.json is missing")
            return
        if not report_path.exists():
            self.result.error("reports/pilot_report.md is missing")

        progress = read_csv(progress_path)
        table_by_year: dict[str, Counter[int]] = {}
        for filename in (
            "program_years.csv",
            "program_offerings.csv",
            "exam_subjects.csv",
            "major_eligibility.csv",
            "admission_scores.csv",
            "admission_rules.csv",
        ):
            table_by_year[filename] = Counter(int(row["year"]) for row in self._load(filename))
        plan_offering_year = {row["offering_id"]: int(row["year"]) for row in self._load("program_offerings.csv")}
        plans_by_year = Counter(plan_offering_year[row["offering_id"]] for row in self._load("enrollment_plans.csv"))
        progress_by_year = {int(row["year"]): row for row in progress}
        for year in YEARS:
            row = progress_by_year.get(year)
            if row is None:
                self.result.error(f"collection_progress missing year {year}")
                continue
            expected_values = {
                "program_years": table_by_year["program_years.csv"][year],
                "program_offerings": table_by_year["program_offerings.csv"][year],
                "enrollment_plans": plans_by_year[year],
                "exam_subjects": table_by_year["exam_subjects.csv"][year],
                "admission_scores": table_by_year["admission_scores.csv"][year],
                "major_eligibility": table_by_year["major_eligibility.csv"][year],
                "admission_rules": table_by_year["admission_rules.csv"][year],
            }
            for field_name, expected_value in expected_values.items():
                if int(row[field_name]) != expected_value:
                    self.result.error(
                        f"collection_progress {year}.{field_name}={row[field_name]}, expected={expected_value}"
                    )
        state = load_json(task_state_path)
        if not state.get("stages", {}).get("report_complete"):
            self.result.error("task_state.report_complete is false")
        if state.get("stage") != "pilot_2_3_complete":
            self.result.error(f"Unexpected task_state.stage: {state.get('stage')}")

    def run(self) -> ValidationResult:
        self.check_manifest()
        self.check_sources()
        self.check_primary_and_foreign_keys()
        self.check_json_fields_and_locators()
        self.check_hfnu_core_counts()
        self.check_eligibility_coverage()
        self.check_exam_and_score_matrix()
        self.check_fact_sources()
        self.check_no_legacy_canonical_files()
        self.check_state_consistency()
        self.result.metrics["canonical_counts"] = {
            filename.removesuffix(".csv"): len(rows)
            for filename, rows in sorted(self.tables.items())
            if filename not in {"sources.csv", "documents.csv"}
        }
        return self.result


def print_result(result: ValidationResult) -> None:
    print("=" * 72)
    print("安徽专升本数据系统验证报告")
    print("=" * 72)
    for message in result.info:
        print(f"[INFO] {message}")
    for message in result.warnings:
        print(f"[P1]   {message}")
    for message in result.errors:
        print(f"[P0]   {message}")
    print("-" * 72)
    print(f"P0 errors: {len(result.errors)} | P1 warnings: {len(result.warnings)}")
    print("PASS" if result.ok else "FAIL")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict-state", action="store_true", help="also validate progress/task/report consistency")
    parser.add_argument("--json-out", type=Path, help="write machine-readable validation result")
    args = parser.parse_args()

    result = Validator(strict_state=args.strict_state).run()
    print_result(result)
    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(result.to_dict(), ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
