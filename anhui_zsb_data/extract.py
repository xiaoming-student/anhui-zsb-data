#!/usr/bin/env python3
"""Validate checked staging JSON without modifying it.

The legacy hard-coded extractor is archived under ``legacy/``. New WorkBuddy
extractions must be written to ``staging/<school_id>/<year>/*.json`` and pass
this verifier before canonical normalization runs.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
STAGING = ROOT / "staging"
SOURCE_CATALOG = ROOT / "config" / "source_catalog.json"

REQUIRED_CORE = (
    "enrollment_plans.json",
    "eligibility.json",
    "exam_subjects.json",
    "admission_rules.json",
)
OPTIONAL = (
    "admission_scores.json",
    "syllabus.json",
    "reference_books.json",
    "application_statistics.json",
)


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def row_key(filename: str, row: dict[str, Any]) -> tuple[str, ...]:
    if filename == "enrollment_plans.json":
        qualifier = (
            str(row.get("training_institution_name", "")).strip()
            or str(row.get("remarks_source_raw", "")).strip()
            or "main_school"
        )
        return (
            str(row.get("major_name_raw", "")).strip(),
            str(row.get("training_type", "")).strip(),
            qualifier,
            str(row.get("training_campus", "")).strip(),
        )
    if filename == "eligibility.json":
        return (str(row.get("undergraduate_major_std", "")).strip(),)
    if filename == "exam_subjects.json":
        return (str(row.get("major_name_raw", "")).strip(),)
    if filename == "admission_rules.json":
        return (
            str(row.get("rule_type", "")).strip(),
            str(row.get("rule_scope", "")).strip(),
        )
    if filename == "admission_scores.json":
        return (
            str(row.get("major_name_raw", "")).strip(),
            str(row.get("notes_raw", "")).strip(),
        )
    if filename == "syllabus.json":
        return (
            str(row.get("major_name_raw", "")).strip(),
            str(row.get("subject_name_raw", "")).strip(),
        )
    if filename == "reference_books.json":
        return (
            str(row.get("major_name_raw", "")).strip(),
            str(row.get("subject_name_raw", "")).strip(),
            str(row.get("reference_key_raw", "")).strip(),
        )
    if filename == "application_statistics.json":
        return (
            str(row.get("major_name_raw", "")).strip(),
            str(row.get("training_institution_name_raw", "")).strip() or "main_school",
        )
    return (json.dumps(row, ensure_ascii=False, sort_keys=True),)


def verify_payload(path: Path, *, school_id: str, year: str, source_ids: set[str]) -> list[str]:
    errors: list[str] = []
    try:
        payload = load_json(path)
    except (OSError, json.JSONDecodeError) as exc:
        return [f"{path.relative_to(ROOT)}: cannot read JSON: {exc}"]

    if not isinstance(payload, dict):
        return [f"{path.relative_to(ROOT)}: root must be an object"]
    rows = payload.get("data")
    if not isinstance(rows, list):
        return [f"{path.relative_to(ROOT)}: data must be an array"]
    if path.name in REQUIRED_CORE and not rows:
        errors.append(f"{path.relative_to(ROOT)}: required data array is empty")

    if str(payload.get("source_school_id", "")) != school_id:
        errors.append(f"{path.relative_to(ROOT)}: source_school_id does not match directory")
    if str(payload.get("source_year", "")) != year:
        errors.append(f"{path.relative_to(ROOT)}: source_year does not match directory")
    source_document_id = str(payload.get("source_document_id", ""))
    if source_document_id not in source_ids:
        errors.append(f"{path.relative_to(ROOT)}: unknown source_document_id={source_document_id!r}")
    if not payload.get("schema_version"):
        errors.append(f"{path.relative_to(ROOT)}: schema_version is missing")
    if not payload.get("extraction_method"):
        errors.append(f"{path.relative_to(ROOT)}: extraction_method is missing")

    seen: set[tuple[str, ...]] = set()
    for index, row in enumerate(rows, 1):
        if not isinstance(row, dict):
            errors.append(f"{path.relative_to(ROOT)} row {index}: row must be an object")
            continue
        key = row_key(path.name, row)
        required_parts = key
        if path.name == "enrollment_plans.json":
            required_parts = key[:3]  # training_campus may be blank
        elif path.name == "admission_scores.json":
            required_parts = key[:1]  # blank notes identify the main-school offering
        if not all(required_parts):
            errors.append(f"{path.relative_to(ROOT)} row {index}: natural key is incomplete: {key}")
        elif key in seen:
            errors.append(f"{path.relative_to(ROOT)} row {index}: duplicate natural key: {key}")
        seen.add(key)
        locator = row.get("source_locator")
        if not isinstance(locator, dict) or not locator:
            errors.append(f"{path.relative_to(ROOT)} row {index}: source_locator must be a non-empty object")
    return errors


def main() -> int:
    if not SOURCE_CATALOG.exists():
        print("ERROR: config/source_catalog.json is missing")
        return 1
    catalog = load_json(SOURCE_CATALOG)
    source_ids = {str(item.get("source_document_id")) for item in catalog.get("documents", [])}

    errors: list[str] = []
    checked = 0
    year_dirs = sorted(path for path in STAGING.glob("*/20??") if path.is_dir())
    if not year_dirs:
        print("ERROR: no staging/<school_id>/<year> directories found")
        return 1

    for year_dir in year_dirs:
        school_id = year_dir.parent.name
        year = year_dir.name
        for filename in REQUIRED_CORE:
            path = year_dir / filename
            if not path.exists():
                errors.append(f"missing {path.relative_to(ROOT)}")
                continue
            errors.extend(verify_payload(path, school_id=school_id, year=year, source_ids=source_ids))
            checked += 1
        for filename in OPTIONAL:
            path = year_dir / filename
            if path.exists():
                errors.extend(verify_payload(path, school_id=school_id, year=year, source_ids=source_ids))
                checked += 1
        print(f"{school_id}/{year}: staging checked")

    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        print(f"Staging verification failed: {len(errors)} error(s)")
        return 1
    print(f"Staging verification passed: {checked} JSON files checked; no files were modified.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
