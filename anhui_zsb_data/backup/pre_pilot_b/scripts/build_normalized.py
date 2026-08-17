#!/usr/bin/env python3
"""Build canonical CSV tables from checked staging JSON and source metadata.

This is the only script allowed to write canonical files in ``normalized/``.
It deliberately derives all IDs from natural keys and never depends on input
row order or legacy id_mapping files.
"""

from __future__ import annotations

import json
import mimetypes
from pathlib import Path
from typing import Any

from common import (
    BASE_DIR,
    CONFIG_DIR,
    NORMALIZED_DIR,
    PLAN_FIELDS,
    RAW_DIR,
    SCORE_FIELDS,
    SCHOOL_ID,
    STAGING_DIR,
    YEARS,
    as_decimal_string,
    ensure_directories,
    extract_joint_institution,
    json_compact,
    load_json,
    normalize_major_name,
    normalize_text,
    normalize_track_raw,
    normalized_locator,
    parse_eligibility_item,
    parse_score,
    score_semantics,
    sha256_file,
    source_id,
    split_top_level_rules,
    stable_id,
    stable_major_id,
    stable_subject_id,
    track_code,
    write_csv,
)


class BuildError(RuntimeError):
    """Raised when staging data cannot be mapped without guessing."""


class CanonicalBuilder:
    def __init__(self) -> None:
        ensure_directories()
        self.source_catalog = load_json(CONFIG_DIR / "source_catalog.json")
        self.institution_config = load_json(CONFIG_DIR / "institutions.json")
        self.source_documents = {
            item["source_document_id"]: item for item in self.source_catalog["documents"]
        }
        self.institutions: list[dict[str, Any]] = []
        self.institution_by_name: dict[str, dict[str, Any]] = {}
        self.assets: list[dict[str, Any]] = []
        self.program_years: list[dict[str, Any]] = []
        self.program_offerings: list[dict[str, Any]] = []
        self.enrollment_plans: list[dict[str, Any]] = []
        self.exam_subjects: list[dict[str, Any]] = []
        self.exam_sessions: list[dict[str, Any]] = []
        self.major_eligibility: list[dict[str, Any]] = []
        self.eligibility_rule_sets: list[dict[str, Any]] = []
        self.eligibility_rule_items: list[dict[str, Any]] = []
        self.admission_scores: list[dict[str, Any]] = []
        self.admission_rules: list[dict[str, Any]] = []

        self.program_year_by_key: dict[tuple[int, str], dict[str, Any]] = {}
        self.offering_by_key: dict[tuple[int, str, str], dict[str, Any]] = {}

    def _staging_payload(self, year: int, filename: str) -> dict[str, Any]:
        path = STAGING_DIR / SCHOOL_ID / str(year) / filename
        if not path.exists():
            raise BuildError(f"Missing staging file: {path.relative_to(BASE_DIR)}")
        payload = load_json(path)
        if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
            raise BuildError(f"Invalid staging payload: {path.relative_to(BASE_DIR)}")
        return payload

    def build_institutions(self) -> None:
        rows: list[dict[str, Any]] = []
        for item in self.institution_config["institutions"]:
            name = normalize_text(item["institution_name_std"])
            institution_id = item.get("institution_id") or stable_id("INST", name)
            row = {
                "institution_id": institution_id,
                "institution_name_std": name,
                "institution_name_raw": normalize_text(item.get("institution_name_raw", name)),
                "institution_type": normalize_text(item.get("institution_type")),
                "institution_role": normalize_text(item.get("institution_role")),
                "city": normalize_text(item.get("city")),
                "official_code": normalize_text(item.get("official_code")),
                "official_url": normalize_text(item.get("official_url")),
                "address": normalize_text(item.get("address")),
                "address_source_id": normalize_text(item.get("address_source_id")),
                "address_source_locator": json_compact(item.get("address_source_locator")),
            }
            rows.append(row)
            self.institution_by_name[name] = row
        self.institutions = sorted(rows, key=lambda row: (row["institution_id"] != SCHOOL_ID, row["institution_name_std"]))
        write_csv(
            NORMALIZED_DIR / "institutions.csv",
            [
                "institution_id",
                "institution_name_std",
                "institution_name_raw",
                "institution_type",
                "institution_role",
                "city",
                "official_code",
                "official_url",
                "address",
                "address_source_id",
                "address_source_locator",
            ],
            self.institutions,
        )

    def _discover_assets(self) -> list[dict[str, Any]]:
        """Build source asset rows from immutable config plus actual files.

        ``raw_manifest.csv`` is an output, not an input. Keeping descriptive
        metadata in ``config/source_assets.json`` makes a clean rebuild fully
        reproducible and avoids a circular dependency on a previous build.
        """
        config_path = CONFIG_DIR / "source_assets.json"
        if not config_path.exists():
            raise BuildError(f"Missing source asset config: {config_path.relative_to(BASE_DIR)}")
        config = load_json(config_path)
        configured = config.get("assets")
        if not isinstance(configured, list) or not configured:
            raise BuildError("config/source_assets.json must contain a non-empty assets list")

        rows: list[dict[str, Any]] = []
        seen_ids: set[str] = set()
        seen_paths: set[str] = set()
        for item in configured:
            asset_id = normalize_text(item.get("asset_id"))
            source_document_id = normalize_text(item.get("source_document_id"))
            relative = normalize_text(item.get("local_path")).replace("\\", "/")
            if not asset_id or asset_id in seen_ids:
                raise BuildError(f"Missing or duplicate configured asset_id: {asset_id!r}")
            if not relative or relative in seen_paths:
                raise BuildError(f"Missing or duplicate configured local_path: {relative!r}")
            if source_document_id not in self.source_documents:
                raise BuildError(f"Configured asset has unknown source document: {source_document_id}")
            path = BASE_DIR / relative
            if not path.is_file():
                raise BuildError(f"Configured raw asset does not exist: {relative}")

            parent_asset_id = normalize_text(item.get("parent_asset_id"))
            mime_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
            rows.append(
                {
                    "asset_id": asset_id,
                    "source_document_id": source_document_id,
                    "local_path": relative,
                    "file_name": path.name,
                    "original_file_name": normalize_text(item.get("original_file_name")) or path.name,
                    "asset_type": normalize_text(item.get("asset_type")) or "raw_document",
                    "mime_type": mime_type,
                    "file_size": path.stat().st_size,
                    "sha256": sha256_file(path),
                    "retrieved_at": normalize_text(item.get("retrieved_at")),
                    "parent_asset_id": parent_asset_id,
                    "parser_name": normalize_text(item.get("parser_name")),
                    "parser_version": normalize_text(item.get("parser_version")),
                    "generated_at": normalize_text(item.get("generated_at")),
                }
            )
            seen_ids.add(asset_id)
            seen_paths.add(relative)

        configured_paths = {row["local_path"] for row in rows}
        unmanaged = [
            path.relative_to(BASE_DIR).as_posix()
            for path in sorted(RAW_DIR.rglob("*"))
            if path.is_file() and path.relative_to(BASE_DIR).as_posix() not in configured_paths
        ]
        if unmanaged:
            raise BuildError("Raw files are not registered in config/source_assets.json: " + ", ".join(unmanaged))

        for row in rows:
            parent = row["parent_asset_id"]
            if parent and parent not in seen_ids:
                raise BuildError(f"Configured parent asset does not exist: {parent}")
        return sorted(rows, key=lambda row: row["asset_id"])

    def build_sources(self) -> None:
        self.assets = self._discover_assets()
        asset_by_id = {row["asset_id"]: row for row in self.assets}

        sites = sorted(self.source_catalog["sites"], key=lambda row: row["source_site_id"])
        write_csv(
            NORMALIZED_DIR / "source_sites.csv",
            ["source_site_id", "organization_id", "organization_name", "site_name", "base_url", "source_level"],
            sites,
        )

        documents: list[dict[str, Any]] = []
        for item in self.source_catalog["documents"]:
            primary_asset_id = item.get("primary_asset_id", "")
            if primary_asset_id and primary_asset_id not in asset_by_id:
                raise BuildError(f"Primary asset does not exist: {primary_asset_id}")
            documents.append(dict(item))
        write_csv(
            NORMALIZED_DIR / "source_documents.csv",
            [
                "source_document_id",
                "source_site_id",
                "year",
                "school_id",
                "document_type",
                "title",
                "url",
                "publish_date",
                "retrieved_at",
                "source_level",
                "status",
                "primary_asset_id",
                "notes",
            ],
            documents,
        )
        write_csv(
            NORMALIZED_DIR / "source_assets.csv",
            [
                "asset_id",
                "source_document_id",
                "local_path",
                "file_name",
                "original_file_name",
                "asset_type",
                "mime_type",
                "file_size",
                "sha256",
                "retrieved_at",
                "parent_asset_id",
                "parser_name",
                "parser_version",
                "generated_at",
            ],
            self.assets,
        )
        # Root manifest mirrors source_assets for convenient external tooling.
        write_csv(
            BASE_DIR / "raw_manifest.csv",
            [
                "asset_id",
                "source_document_id",
                "local_path",
                "file_name",
                "original_file_name",
                "asset_type",
                "mime_type",
                "file_size",
                "sha256",
                "retrieved_at",
                "parent_asset_id",
                "parser_name",
                "parser_version",
                "generated_at",
            ],
            self.assets,
        )

        # Compatibility exports used by older notebooks.
        compatibility_sources: list[dict[str, Any]] = []
        compatibility_documents: list[dict[str, Any]] = []
        for item in documents:
            asset = asset_by_id.get(item.get("primary_asset_id", ""), {})
            compatibility_sources.append(
                {
                    "source_id": item["source_document_id"],
                    "source_level": item["source_level"],
                    "organization_name": next(
                        site["organization_name"] for site in sites if site["source_site_id"] == item["source_site_id"]
                    ),
                    "title": item["title"],
                    "url": item["url"],
                    "publish_date": item["publish_date"],
                    "accessed_at": item["retrieved_at"],
                    "file_name": asset.get("file_name", ""),
                    "local_path": asset.get("local_path", ""),
                    "content_hash": asset.get("sha256", ""),
                    "status": item["status"],
                    "notes": item.get("notes", ""),
                }
            )
            compatibility_documents.append(
                {
                    "document_id": item["source_document_id"].replace("SRC-", "DOC-", 1),
                    "source_id": item["source_document_id"],
                    "year": item["year"],
                    "school_id": item["school_id"],
                    "document_type": item["document_type"],
                    "title": item["title"],
                    "publish_date": item["publish_date"],
                    "url": item["url"],
                    "file_name": asset.get("file_name", ""),
                    "local_path": asset.get("local_path", ""),
                    "file_type": Path(asset.get("file_name", "")).suffix.lstrip(".") if asset else "html",
                    "content_hash": asset.get("sha256", ""),
                    "source_level": item["source_level"],
                    "retrieved_at": item["retrieved_at"],
                    "status": item["status"],
                }
            )
        write_csv(
            NORMALIZED_DIR / "sources.csv",
            [
                "source_id",
                "source_level",
                "organization_name",
                "title",
                "url",
                "publish_date",
                "accessed_at",
                "file_name",
                "local_path",
                "content_hash",
                "status",
                "notes",
            ],
            compatibility_sources,
        )
        write_csv(
            NORMALIZED_DIR / "documents.csv",
            [
                "document_id",
                "source_id",
                "year",
                "school_id",
                "document_type",
                "title",
                "publish_date",
                "url",
                "file_name",
                "local_path",
                "file_type",
                "content_hash",
                "source_level",
                "retrieved_at",
                "status",
            ],
            compatibility_documents,
        )

    def _institution_for_plan(self, plan: dict[str, Any]) -> dict[str, Any]:
        training_type = normalize_text(plan.get("training_type"))
        if training_type == "main_school":
            return self.institution_by_name["合肥师范学院"]
        if training_type != "joint_training":
            raise BuildError(f"Unsupported training_type: {training_type!r}")
        name = normalize_text(plan.get("training_institution_name")) or extract_joint_institution(
            plan.get("remarks_source_raw")
        )
        if not name:
            raise BuildError(f"Joint-training row has no institution: {plan!r}")
        try:
            return self.institution_by_name[name]
        except KeyError:
            raise BuildError(f"Unknown joint-training institution: {name}") from None

    def build_programs_and_plans(self) -> None:
        program_rows: dict[tuple[int, str], dict[str, Any]] = {}
        offering_rows: dict[tuple[int, str, str], dict[str, Any]] = {}
        plan_rows: list[dict[str, Any]] = []

        for year in YEARS:
            payload = self._staging_payload(year, "enrollment_plans.json")
            source = source_id(year, "admission_policy")
            publish_date = self.source_documents[source]["publish_date"]
            for plan in payload["data"]:
                major_raw = normalize_text(plan["major_name_raw"])
                major_std = normalize_major_name(major_raw)
                raw_track = normalize_track_raw(plan["admission_track_raw"])
                program_key = (year, major_std)
                locator = normalized_locator(
                    plan.get("source_locator"),
                    year=year,
                    document_type="admission_policy",
                    row_key=major_std,
                    section="招生专业计划",
                )
                if program_key not in program_rows:
                    py_id = stable_id("PY", SCHOOL_ID, year, major_std)
                    program_rows[program_key] = {
                        "program_year_id": py_id,
                        "year": year,
                        "admission_school_id": SCHOOL_ID,
                        "undergraduate_major_id": stable_major_id(major_std),
                        "major_name_raw": major_raw,
                        "major_name_std": major_std,
                        "admission_track_raw": raw_track,
                        "admission_track_code": track_code(raw_track),
                        "study_years": 2,
                        "source_id": source,
                        "source_locator": locator,
                    }
                elif program_rows[program_key]["admission_track_code"] != track_code(raw_track):
                    raise BuildError(f"Conflicting admission track for {year} {major_std}")

                institution = self._institution_for_plan(plan)
                offering_key = (year, major_std, institution["institution_id"])
                if offering_key in offering_rows:
                    raise BuildError(f"Duplicate offering natural key: {offering_key}")
                offering_id = stable_id(
                    "OFF",
                    program_rows[program_key]["program_year_id"],
                    plan.get("training_type"),
                    institution["institution_id"],
                    "",
                )
                training_type = normalize_text(plan.get("training_type"))
                remarks_raw = normalize_text(plan.get("remarks_source_raw"))
                offering = {
                    "offering_id": offering_id,
                    "program_year_id": program_rows[program_key]["program_year_id"],
                    "year": year,
                    "training_type": training_type,
                    "training_institution_id": institution["institution_id"],
                    "training_institution_name": institution["institution_name_std"],
                    "training_campus": "",
                    "training_campus_status": "not_published",
                    "training_address": institution.get("address", "") if training_type == "joint_training" else "",
                    "tuition_value": as_decimal_string(plan.get("tuition_value")),
                    "study_years": 2,
                    "remarks_source_raw": remarks_raw,
                    "training_type_is_derived": training_type == "main_school",
                    "training_type_derivation_method": (
                        "official_plan_row_without_joint_training_remark" if training_type == "main_school" else ""
                    ),
                    "source_id": source,
                    "source_locator": locator,
                }
                offering_rows[offering_key] = offering

                for plan_type, field_name in PLAN_FIELDS:
                    raw_value = plan.get(field_name)
                    if raw_value is None or raw_value == "":
                        value = ""
                        value_status = "blank_in_source"
                    else:
                        value = as_decimal_string(raw_value)
                        value_status = "explicit_zero" if value == "0" else "explicit_value"
                    plan_rows.append(
                        {
                            "enrollment_plan_id": stable_id("PLAN", offering_id, plan_type, "original"),
                            "offering_id": offering_id,
                            "plan_type": plan_type,
                            "plan_value": value,
                            "value_status": value_status,
                            "plan_version": "original",
                            "announcement_date": publish_date,
                            "is_derived": False,
                            "derivation_method": "",
                            "raw_value": "" if raw_value is None else normalize_text(raw_value),
                            "source_id": source,
                            "source_locator": locator,
                        }
                    )

        self.program_years = sorted(program_rows.values(), key=lambda row: (row["year"], row["major_name_std"]))
        self.program_offerings = sorted(
            offering_rows.values(),
            key=lambda row: (row["year"], self._major_for_program(row["program_year_id"]), row["training_institution_name"]),
        )
        self.enrollment_plans = sorted(
            plan_rows,
            key=lambda row: (self._offering_sort_key(row["offering_id"]), self._plan_order(row["plan_type"])),
        )
        self.program_year_by_key = program_rows
        self.offering_by_key = offering_rows

        write_csv(
            NORMALIZED_DIR / "program_years.csv",
            [
                "program_year_id",
                "year",
                "admission_school_id",
                "undergraduate_major_id",
                "major_name_raw",
                "major_name_std",
                "admission_track_raw",
                "admission_track_code",
                "study_years",
                "source_id",
                "source_locator",
            ],
            self.program_years,
        )
        write_csv(
            NORMALIZED_DIR / "program_offerings.csv",
            [
                "offering_id",
                "program_year_id",
                "year",
                "training_type",
                "training_institution_id",
                "training_institution_name",
                "training_campus",
                "training_campus_status",
                "training_address",
                "tuition_value",
                "study_years",
                "remarks_source_raw",
                "training_type_is_derived",
                "training_type_derivation_method",
                "source_id",
                "source_locator",
            ],
            self.program_offerings,
        )
        write_csv(
            NORMALIZED_DIR / "enrollment_plans.csv",
            [
                "enrollment_plan_id",
                "offering_id",
                "plan_type",
                "plan_value",
                "value_status",
                "plan_version",
                "announcement_date",
                "is_derived",
                "derivation_method",
                "raw_value",
                "source_id",
                "source_locator",
            ],
            self.enrollment_plans,
        )

    def _major_for_program(self, program_year_id: str) -> str:
        for row in self.program_years:
            if row["program_year_id"] == program_year_id:
                return row["major_name_std"]
        return ""

    def _offering_sort_key(self, offering_id: str) -> tuple[Any, ...]:
        row = next(item for item in self.program_offerings if item["offering_id"] == offering_id)
        return (row["year"], self._major_for_program(row["program_year_id"]), row["training_institution_name"])

    @staticmethod
    def _plan_order(plan_type: str) -> int:
        return [item[0] for item in PLAN_FIELDS].index(plan_type)

    def _program_for_major(self, year: int, major: str) -> dict[str, Any]:
        key = (year, normalize_major_name(major))
        try:
            return self.program_year_by_key[key]
        except KeyError:
            raise BuildError(f"No program year for {year} {major}") from None

    def build_exam_data(self) -> None:
        subject_rows: list[dict[str, Any]] = []
        session_rows: list[dict[str, Any]] = []
        for year in YEARS:
            payload = self._staging_payload(year, "exam_subjects.json")
            source = source_id(year, "admission_policy")
            seen_programs: set[str] = set()
            for item in payload["data"]:
                major_std = normalize_major_name(item["major_name_raw"])
                program = self._program_for_major(year, major_std)
                py_id = program["program_year_id"]
                if py_id in seen_programs:
                    raise BuildError(f"Duplicate exam-subject row for {year} {major_std}")
                seen_programs.add(py_id)
                locator = normalized_locator(
                    item.get("source_locator"),
                    year=year,
                    document_type="admission_policy",
                    row_key=major_std,
                    section="考试科目",
                )
                slots = (
                    ("public_1", item.get("public_subject_1")),
                    ("public_2", item.get("public_subject_2")),
                    ("professional_1", item.get("professional_subject_1")),
                    ("professional_2", item.get("professional_subject_2")),
                )
                for slot, subject_raw in slots:
                    subject_name = normalize_text(subject_raw)
                    if not subject_name:
                        raise BuildError(f"Missing {slot} for {year} {major_std}")
                    subject_rows.append(
                        {
                            "exam_subject_id": stable_id("EXAM", py_id, slot),
                            "program_year_id": py_id,
                            "year": year,
                            "subject_slot": slot,
                            "subject_id": stable_subject_id(subject_name),
                            "subject_name_raw": subject_name,
                            "subject_name_std": subject_name,
                            "score_max": 150,
                            "exam_duration_minutes": 120 if slot == "public_1" else 90 if slot == "public_2" else "",
                            "exam_method": "笔试",
                            "source_id": source,
                            "source_locator": locator,
                        }
                    )
                session_rows.extend(self._exam_sessions_for_program(program, source, locator))

        self.exam_subjects = sorted(subject_rows, key=lambda row: (row["year"], self._major_for_program(row["program_year_id"]), row["subject_slot"]))
        self.exam_sessions = sorted(session_rows, key=lambda row: (row["year"], self._major_for_program(row["program_year_id"]), row["session_type"]))
        write_csv(
            NORMALIZED_DIR / "exam_subjects.csv",
            [
                "exam_subject_id",
                "program_year_id",
                "year",
                "subject_slot",
                "subject_id",
                "subject_name_raw",
                "subject_name_std",
                "score_max",
                "exam_duration_minutes",
                "exam_method",
                "source_id",
                "source_locator",
            ],
            self.exam_subjects,
        )
        write_csv(
            NORMALIZED_DIR / "exam_sessions.csv",
            [
                "exam_session_id",
                "program_year_id",
                "year",
                "session_type",
                "subject_slots_json",
                "duration_minutes",
                "exam_date",
                "start_time",
                "end_time",
                "exam_site_raw",
                "exam_site_status",
                "source_id",
                "source_locator",
            ],
            self.exam_sessions,
        )

    def _exam_sessions_for_program(self, program: dict[str, Any], source: str, subject_locator: str) -> list[dict[str, Any]]:
        year = int(program["year"])
        py_id = program["program_year_id"]
        track = program["admission_track_code"]
        timetable: dict[str, tuple[str, str, str]] = {}
        if year == 2025:
            timetable = {
                "public_1": ("2025-04-19", "09:00", "11:00"),
                "public_2": ("2025-04-19", "14:00", "15:30"),
                "professional_combined": (
                    "2025-04-20",
                    "14:00" if track == "science" else "08:00",
                    "17:00" if track == "science" else "11:00",
                ),
            }
        elif year == 2026:
            timetable = {
                "public_1": ("2026-04-18", "09:00", "11:00"),
                "public_2": ("2026-04-18", "14:00", "15:30"),
                "professional_combined": (
                    "2026-04-19",
                    "14:00" if track == "science" else "08:00",
                    "17:00" if track == "science" else "11:00",
                ),
            }
        session_specs = (
            ("public_1", ["public_1"], 120),
            ("public_2", ["public_2"], 90),
            ("professional_combined", ["professional_1", "professional_2"], 180),
        )
        rows = []
        schedule_locator = subject_locator
        if year in {2025, 2026}:
            schedule_locator = normalized_locator(
                {"asset_id": f"ASSET-HFNU-{year}-ZC-PDF", "page": 13 if year == 2025 else 12},
                year=year,
                document_type="admission_policy",
                row_key=program["major_name_std"],
                section="考试时间和考试地点",
            )
        for session_type, slots, duration in session_specs:
            date, start, end = timetable.get(session_type, ("", "", ""))
            if session_type == "professional_combined" and year in {2025, 2026}:
                site = "合肥师范学院锦绣校区"
                site_status = "published"
            else:
                site = ""
                site_status = "not_published"
            loc = schedule_locator if year in {2025, 2026} else subject_locator
            rows.append(
                {
                    "exam_session_id": stable_id("SESSION", py_id, session_type),
                    "program_year_id": py_id,
                    "year": year,
                    "session_type": session_type,
                    "subject_slots_json": slots,
                    "duration_minutes": duration,
                    "exam_date": date,
                    "start_time": start,
                    "end_time": end,
                    "exam_site_raw": site,
                    "exam_site_status": site_status,
                    "source_id": source,
                    "source_locator": loc,
                }
            )
        return rows

    def build_eligibility(self) -> None:
        eligibility_rows: list[dict[str, Any]] = []
        rule_sets: list[dict[str, Any]] = []
        rule_items: list[dict[str, Any]] = []
        for year in YEARS:
            payload = self._staging_payload(year, "eligibility.json")
            source = source_id(year, "admission_policy")
            seen: set[str] = set()
            for item in payload["data"]:
                major_std = normalize_major_name(item["undergraduate_major_std"])
                program = self._program_for_major(year, major_std)
                py_id = program["program_year_id"]
                if py_id in seen:
                    raise BuildError(f"Duplicate eligibility row: {year} {major_std}")
                seen.add(py_id)
                raw_scope = normalize_text(item.get("allowed_major_categories_raw"))
                raw_restriction = normalize_text(item.get("restriction_raw_text")) or raw_scope
                parts = split_top_level_rules(raw_scope)
                parsed_parts = [parse_eligibility_item(part) for part in parts]
                categories_std = ",".join(part["scope_name_raw"] for part in parsed_parts)
                locator = normalized_locator(
                    item.get("source_locator"),
                    year=year,
                    document_type="admission_policy",
                    row_key=major_std,
                    section="招生专业范围",
                )
                eligibility_id = stable_id("ELIG", py_id)
                rule_set_id = stable_id("ELIGSET", py_id)
                eligibility_rows.append(
                    {
                        "eligibility_id": eligibility_id,
                        "program_year_id": py_id,
                        "year": year,
                        "undergraduate_major_raw": normalize_text(item.get("undergraduate_major_raw", major_std)),
                        "undergraduate_major_std": major_std,
                        "allowed_major_categories_raw": raw_scope,
                        "allowed_major_categories_std": categories_std,
                        "restriction_raw_text": raw_restriction,
                        "source_id": source,
                        "source_locator": locator,
                    }
                )
                rule_sets.append(
                    {
                        "eligibility_rule_set_id": rule_set_id,
                        "program_year_id": py_id,
                        "year": year,
                        "raw_text": raw_restriction,
                        "source_id": source,
                        "source_locator": locator,
                    }
                )
                for ordinal, parsed in enumerate(parsed_parts, 1):
                    rule_items.append(
                        {
                            "eligibility_rule_item_id": stable_id("ELIGITEM", rule_set_id, ordinal, parsed["scope_name_raw"]),
                            "eligibility_rule_set_id": rule_set_id,
                            "ordinal": ordinal,
                            "scope_type": "major_category",
                            "include_or_exclude": "include",
                            "category_code": "",
                            "category_name_raw": parsed["scope_name_raw"],
                            "major_code": "",
                            "major_name_raw": "",
                            "condition_raw": parsed["condition_raw"],
                        }
                    )

        self.major_eligibility = sorted(eligibility_rows, key=lambda row: (row["year"], row["undergraduate_major_std"]))
        self.eligibility_rule_sets = sorted(rule_sets, key=lambda row: (row["year"], self._major_for_program(row["program_year_id"])))
        self.eligibility_rule_items = sorted(rule_items, key=lambda row: (row["eligibility_rule_set_id"], int(row["ordinal"])))
        write_csv(
            NORMALIZED_DIR / "major_eligibility.csv",
            [
                "eligibility_id",
                "program_year_id",
                "year",
                "undergraduate_major_raw",
                "undergraduate_major_std",
                "allowed_major_categories_raw",
                "allowed_major_categories_std",
                "restriction_raw_text",
                "source_id",
                "source_locator",
            ],
            self.major_eligibility,
        )
        write_csv(
            NORMALIZED_DIR / "eligibility_rule_sets.csv",
            ["eligibility_rule_set_id", "program_year_id", "year", "raw_text", "source_id", "source_locator"],
            self.eligibility_rule_sets,
        )
        write_csv(
            NORMALIZED_DIR / "eligibility_rule_items.csv",
            [
                "eligibility_rule_item_id",
                "eligibility_rule_set_id",
                "ordinal",
                "scope_type",
                "include_or_exclude",
                "category_code",
                "category_name_raw",
                "major_code",
                "major_name_raw",
                "condition_raw",
            ],
            self.eligibility_rule_items,
        )

    def _resolve_score_offering(self, year: int, score: dict[str, Any]) -> dict[str, Any]:
        major_std = normalize_major_name(score["major_name_raw"])
        notes = normalize_text(score.get("notes_raw"))
        institution_name = notes if notes in self.institution_by_name else "合肥师范学院"
        institution_id = self.institution_by_name[institution_name]["institution_id"]
        key = (year, major_std, institution_id)
        try:
            return self.offering_by_key[key]
        except KeyError:
            raise BuildError(f"Cannot resolve score offering: {year} {major_std} {notes!r}") from None

    def build_admission_scores(self) -> None:
        rows: list[dict[str, Any]] = []
        for year in (2024, 2025):
            payload = self._staging_payload(year, "admission_scores.json")
            source = source_id(year, "admission_scores")
            seen_offering_rows: set[str] = set()
            for item in payload["data"]:
                offering = self._resolve_score_offering(year, item)
                offering_id = offering["offering_id"]
                if offering_id in seen_offering_rows:
                    raise BuildError(f"Duplicate score source row for offering: {offering_id}")
                seen_offering_rows.add(offering_id)
                major_std = self._major_for_program(offering["program_year_id"])
                locator = normalized_locator(
                    item.get("source_locator"),
                    year=year,
                    document_type="admission_scores",
                    row_key=f"{major_std}|{offering['training_institution_name']}",
                    section="录取最低分",
                )
                for candidate_category, field_name in SCORE_FIELDS:
                    raw_value = item.get(field_name)
                    raw = normalize_text(raw_value)
                    semantics = score_semantics(candidate_category)
                    parsed = parse_score(raw) if raw else {
                        "score_value_numeric": "",
                        "score_max_from_raw": "",
                        "threshold_detail_json": "",
                    }
                    score_max = parsed["score_max_from_raw"] or semantics["score_max"]
                    value_status = "published_value" if raw else "blank_in_source"
                    admission_round = "first_choice"
                    rows.append(
                        {
                            "admission_score_id": stable_id(
                                "SCORE", offering_id, candidate_category, semantics["score_metric"], admission_round
                            ),
                            "offering_id": offering_id,
                            "year": year,
                            "candidate_category": candidate_category,
                            "admission_round": admission_round,
                            "score_metric": semantics["score_metric"],
                            "score_basis": semantics["score_basis"],
                            "score_max": score_max,
                            "score_value_numeric": parsed["score_value_numeric"],
                            "score_raw": raw,
                            "value_status": value_status,
                            "threshold_detail_json": parsed["threshold_detail_json"],
                            "assessment_name": semantics["assessment_name"],
                            "notes_source_raw": normalize_text(item.get("notes_raw")),
                            "is_official_direct": True,
                            "is_derived": False,
                            "derivation_method": "",
                            "source_id": source,
                            "source_locator": locator,
                        }
                    )
        self.admission_scores = sorted(
            rows,
            key=lambda row: (self._offering_sort_key(row["offering_id"]), [item[0] for item in SCORE_FIELDS].index(row["candidate_category"])),
        )
        write_csv(
            NORMALIZED_DIR / "admission_scores.csv",
            [
                "admission_score_id",
                "offering_id",
                "year",
                "candidate_category",
                "admission_round",
                "score_metric",
                "score_basis",
                "score_max",
                "score_value_numeric",
                "score_raw",
                "value_status",
                "threshold_detail_json",
                "assessment_name",
                "notes_source_raw",
                "is_official_direct",
                "is_derived",
                "derivation_method",
                "source_id",
                "source_locator",
            ],
            self.admission_scores,
        )

    def build_admission_rules(self) -> None:
        rows: list[dict[str, Any]] = []
        for year in YEARS:
            payload = self._staging_payload(year, "admission_rules.json")
            source = source_id(year, "admission_policy")
            for item in payload["data"]:
                rule_type = normalize_text(item["rule_type"])
                locator = normalized_locator(
                    item.get("source_locator"),
                    year=year,
                    document_type="admission_policy",
                    row_key=rule_type,
                    section="录取规则",
                )
                rows.append(
                    {
                        "rule_id": stable_id("RULE", SCHOOL_ID, year, rule_type, item.get("rule_scope", "")),
                        "year": year,
                        "school_id": SCHOOL_ID,
                        "rule_type": rule_type,
                        "rule_scope": normalize_text(item.get("rule_scope")),
                        "rule_raw_text": normalize_text(item.get("rule_raw_text")),
                        "rule_structured_json": json_compact(item.get("rule_structured_json")),
                        "source_id": source,
                        "source_locator": locator,
                    }
                )
        self.admission_rules = sorted(rows, key=lambda row: (row["year"], row["rule_type"]))
        write_csv(
            NORMALIZED_DIR / "admission_rules.csv",
            [
                "rule_id",
                "year",
                "school_id",
                "rule_type",
                "rule_scope",
                "rule_raw_text",
                "rule_structured_json",
                "source_id",
                "source_locator",
            ],
            self.admission_rules,
        )

    def build_supporting_tables(self) -> None:
        hfnu = self.institution_by_name["合肥师范学院"]
        write_csv(
            NORMALIZED_DIR / "schools.csv",
            [
                "school_id",
                "school_name_std",
                "school_name_raw",
                "school_nature",
                "school_type",
                "city",
                "official_website",
                "admission_website",
            ],
            [
                {
                    "school_id": SCHOOL_ID,
                    "school_name_std": hfnu["institution_name_std"],
                    "school_name_raw": hfnu["institution_name_raw"],
                    "school_nature": "公办",
                    "school_type": "普通本科",
                    "city": hfnu["city"],
                    "official_website": hfnu["official_url"],
                    "admission_website": "https://zsb.hfnu.edu.cn/",
                }
            ],
        )
        write_csv(
            NORMALIZED_DIR / "school_years.csv",
            ["school_year_id", "year", "school_id", "policy_source_id", "collection_status"],
            [
                {
                    "school_year_id": stable_id("SY", SCHOOL_ID, year),
                    "year": year,
                    "school_id": SCHOOL_ID,
                    "policy_source_id": source_id(year, "admission_policy"),
                    "collection_status": "partial" if year == 2026 else "complete_core",
                }
                for year in YEARS
            ],
        )
        write_csv(
            NORMALIZED_DIR / "dim_school_alias.csv",
            ["school_id", "alias_raw", "alias_type", "notes"],
            [
                {"school_id": SCHOOL_ID, "alias_raw": "合肥师范学院", "alias_type": "official", "notes": "学校官方全称"},
                {"school_id": SCHOOL_ID, "alias_raw": "合师院", "alias_type": "common_alias", "notes": "常用简称"},
                {"school_id": SCHOOL_ID, "alias_raw": "合肥师范大学", "alias_type": "mistaken_name", "notes": "用户误称，非官方名称"},
                {"school_id": SCHOOL_ID, "alias_raw": "Hefei Normal University", "alias_type": "english_name", "notes": "英文名称"},
            ],
        )
        # Preserve useful subject aliases but derive official rows from current subject facts.
        subjects = sorted({row["subject_name_std"] for row in self.exam_subjects})
        short_aliases = {
            "大学语文": ["语文"],
            "高等数学": ["高数"],
            "英语": ["大学英语"],
            "管理学原理": ["管理学"],
            "会计学原理": ["会计学"],
            "C语言程序设计": ["C语言"],
        }
        subject_alias_rows: list[dict[str, str]] = []
        for subject in subjects:
            subject_alias_rows.append(
                {"subject_name_std": subject, "alias_raw": subject, "alias_type": "official", "notes": ""}
            )
            for alias in short_aliases.get(subject, []):
                subject_alias_rows.append(
                    {"subject_name_std": subject, "alias_raw": alias, "alias_type": "short_alias", "notes": ""}
                )
        write_csv(
            NORMALIZED_DIR / "dim_subject_alias.csv",
            ["subject_name_std", "alias_raw", "alias_type", "notes"],
            subject_alias_rows,
        )
        write_csv(
            NORMALIZED_DIR / "dim_major_alias.csv",
            ["major_name_std", "alias_raw", "alias_type", "notes"],
            [],
        )
        # Empty future tables use explicit schemas instead of ambiguous blank files.
        empty_schemas = {
            "syllabus.csv": [
                "syllabus_id", "program_year_id", "subject_id", "title", "raw_text", "source_id", "source_locator"
            ],
            "reference_books.csv": [
                "reference_book_id", "program_year_id", "subject_id", "book_name", "author", "publisher", "edition", "isbn", "source_id", "source_locator"
            ],
            "adjustments.csv": [
                "adjustment_id", "offering_id", "adjustment_type", "plan_value", "requirements_raw", "source_id", "source_locator"
            ],
            "application_statistics.csv": [
                "application_statistic_id", "offering_id", "applicant_count", "qualified_count", "admitted_count", "source_id", "source_locator"
            ],
        }
        for filename, headers in empty_schemas.items():
            write_csv(NORMALIZED_DIR / filename, headers, [])

    def build_fact_sources(self) -> None:
        table_specs = {
            "program_years": (self.program_years, "program_year_id"),
            "program_offerings": (self.program_offerings, "offering_id"),
            "enrollment_plans": (self.enrollment_plans, "enrollment_plan_id"),
            "exam_subjects": (self.exam_subjects, "exam_subject_id"),
            "exam_sessions": (self.exam_sessions, "exam_session_id"),
            "major_eligibility": (self.major_eligibility, "eligibility_id"),
            "eligibility_rule_sets": (self.eligibility_rule_sets, "eligibility_rule_set_id"),
            "admission_scores": (self.admission_scores, "admission_score_id"),
            "admission_rules": (self.admission_rules, "rule_id"),
        }
        rows: list[dict[str, Any]] = []
        for table_name, (records, id_field) in table_specs.items():
            for record in records:
                rows.append(
                    {
                        "fact_source_id": stable_id("FACTSRC", table_name, record[id_field], record["source_id"]),
                        "table_name": table_name,
                        "record_id": record[id_field],
                        "source_id": record["source_id"],
                        "relation_type": "primary_evidence",
                        "source_locator": record.get("source_locator", ""),
                    }
                )
        write_csv(
            NORMALIZED_DIR / "fact_sources.csv",
            ["fact_source_id", "table_name", "record_id", "source_id", "relation_type", "source_locator"],
            sorted(rows, key=lambda row: (row["table_name"], row["record_id"])),
        )

    def build(self) -> dict[str, int]:
        self.build_institutions()
        self.build_sources()
        self.build_programs_and_plans()
        self.build_exam_data()
        self.build_eligibility()
        self.build_admission_scores()
        self.build_admission_rules()
        self.build_supporting_tables()
        self.build_fact_sources()
        return {
            "institutions": len(self.institutions),
            "program_years": len(self.program_years),
            "program_offerings": len(self.program_offerings),
            "enrollment_plans": len(self.enrollment_plans),
            "exam_subjects": len(self.exam_subjects),
            "exam_sessions": len(self.exam_sessions),
            "major_eligibility": len(self.major_eligibility),
            "eligibility_rule_items": len(self.eligibility_rule_items),
            "admission_scores": len(self.admission_scores),
            "admission_rules": len(self.admission_rules),
        }


def main() -> int:
    builder = CanonicalBuilder()
    counts = builder.build()
    print("Canonical build complete")
    for name, count in counts.items():
        print(f"  {name}: {count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
