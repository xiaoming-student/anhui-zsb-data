#!/usr/bin/env python3
"""Merge Stage 2A HFNU staging into normalized CSV outputs.

This hook runs after the existing normalized builder and before validation and
SQLite generation. It adds deterministic records for 2026 admission scores,
2024 application statistics, and 2024-2026 syllabus/reference books. Existing
records are never mutated; a conflicting primary key fails the build.
"""
from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
STAGING_ROOT = ROOT / "staging" / "HFNU"
REPORT_PATH = ROOT / "reports" / "stage2a_hfnu_normalized_extension.json"


def stable(prefix: str, *parts: Any) -> str:
    digest = hashlib.sha1("|".join(map(str, parts)).encode("utf-8")).hexdigest()[:16]
    return f"{prefix}-{digest.upper()}"


def find_csv(table: str) -> Path:
    direct = ROOT / "normalized" / f"{table}.csv"
    if direct.is_file():
        return direct
    matches = list((ROOT / "normalized").rglob(f"{table}.csv"))
    if len(matches) != 1:
        raise RuntimeError(f"cannot resolve normalized table {table!r}: {matches}")
    return matches[0]


def read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        return list(reader.fieldnames or []), list(reader)


def write_csv(path: Path, fields: list[str], rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=fields,
            extrasaction="ignore",
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(rows)


def column(
    fields: list[str],
    includes: tuple[str, ...],
    excludes: tuple[str, ...] = (),
) -> str | None:
    for field in fields:
        lowered = field.lower()
        if all(token in lowered for token in includes) and not any(
            token in lowered for token in excludes
        ):
            return field
    return None


def set_semantic(
    row: dict[str, str],
    fields: list[str],
    includes: tuple[str, ...],
    value: Any,
    excludes: tuple[str, ...] = (),
) -> str | None:
    field = column(fields, includes, excludes)
    if field:
        row[field] = "" if value is None else str(value)
    return field


def primary_key(fields: list[str], table: str) -> str:
    exact = column(fields, (table.rstrip("s"), "id"))
    if exact:
        return exact
    candidates = [field for field in fields if field.endswith("_id")]
    if not candidates:
        raise RuntimeError(f"no primary key column for {table}: {fields}")
    return candidates[0]


def load_stage(kind: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in sorted(STAGING_ROOT.rglob(f"stage2a_{kind}.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        for record in payload["records"]:
            rows.append(
                {
                    **record,
                    "_year": payload["year"],
                    "_source_document_id": payload["source_document_id"],
                    "_source_asset_id": payload["source_asset_id"],
                    "_stage_path": path.relative_to(ROOT).as_posix(),
                }
            )
    return rows


def merge(table: str, new_rows: list[dict[str, str]]) -> dict[str, Any]:
    path = find_csv(table)
    fields, rows = read_csv(path)
    key = primary_key(fields, table)
    existing = {row[key]: row for row in rows}
    added_ids: list[str] = []
    for row in new_rows:
        row_id = row[key]
        if row_id in existing:
            if existing[row_id] != row:
                raise RuntimeError(f"non-idempotent collision: {table}:{row_id}")
            continue
        existing[row_id] = row
        rows.append(row)
        added_ids.append(row_id)
    rows.sort(key=lambda row: row.get(key, ""))
    write_csv(path, fields, rows)
    return {
        "table": table,
        "path": path.relative_to(ROOT).as_posix(),
        "primary_key": key,
        "before": len(rows) - len(added_ids),
        "added": len(added_ids),
        "after": len(rows),
        "added_ids": added_ids,
    }


def blank(fields: list[str]) -> dict[str, str]:
    return {field: "" for field in fields}


def build_score_rows() -> list[tuple[dict[str, str], dict[str, Any]]]:
    path = find_csv("admission_scores")
    fields, existing = read_csv(path)
    key = primary_key(fields, "admission_scores")
    offering_id = column(fields, ("offering", "id"))
    program_year_id = column(fields, ("program", "year", "id"))
    score_value = (
        column(fields, ("minimum", "score"))
        or column(fields, ("min", "score"))
        or column(fields, ("score", "value"))
        or column(fields, ("score",), ("id", "type", "category", "note"))
    )
    if not offering_id or not score_value or not existing:
        raise RuntimeError(f"admission_scores columns unsupported: {fields}")

    category_fields = [
        field
        for field in fields
        if any(
            token in field.lower()
            for token in ("type", "category", "candidate", "plan_type", "score_kind")
        )
        and not field.endswith("_id")
    ]
    templates = {
        tuple(row.get(field, "") for field in category_fields): row
        for row in existing
    }
    default_template = existing[0]
    result: list[tuple[dict[str, str], dict[str, Any]]] = []

    for staged in load_stage("admission_scores"):
        category_tuple = tuple(
            str(staged.get("category_fields", {}).get(field, ""))
            for field in category_fields
        )
        row = dict(templates.get(category_tuple, default_template))
        row[key] = stable(
            "AS-HFNU-2026",
            staged["offering_id"],
            *category_tuple,
            staged["official_column_index"],
        )
        row[offering_id] = staged["offering_id"]
        if program_year_id:
            row[program_year_id] = staged["program_year_id"]
        row[score_value] = str(staged["score_value"])
        for field, value in staged.get("category_fields", {}).items():
            if field in row:
                row[field] = str(value)
        mappings = [
            (("year",), staged["_year"], ("id",)),
            (("major", "name"), staged["major_name"], ()),
            (("training", "institution", "id"), staged["training_institution_id"], ()),
            (("source", "document", "id"), staged["_source_document_id"], ()),
            (("source", "asset", "id"), staged["_source_asset_id"], ()),
            (("source", "locator"), staged["source_locator"], ()),
            (("note",), staged["source_quote"], ()),
        ]
        for includes, value, excludes in mappings:
            set_semantic(row, fields, includes, value, excludes)
        result.append((row, staged))
    return result


def build_generic_rows(
    table: str,
    stage_kind: str,
    prefix: str,
) -> list[tuple[dict[str, str], dict[str, Any]]]:
    fields, _existing = read_csv(find_csv(table))
    key = primary_key(fields, table)
    result: list[tuple[dict[str, str], dict[str, Any]]] = []
    for staged in load_stage(stage_kind):
        row = blank(fields)
        row[key] = stable(prefix, staged["staging_id"])
        mappings = [
            (("program", "year", "id"), staged.get("program_year_id"), ()),
            (("offering", "id"), staged.get("offering_id"), ()),
            (("exam", "subject", "id"), staged.get("exam_subject_id"), ()),
            (("major", "name"), staged.get("major_name"), ()),
            (("subject", "name"), staged.get("subject_name"), ()),
            (("applicant", "count"), staged.get("applicant_count"), ()),
            (("application", "count"), staged.get("applicant_count"), ()),
            (("syllabus", "text"), staged.get("syllabus_text"), ()),
            (("content",), staged.get("syllabus_text"), ()),
            (("book", "title"), staged.get("book_title"), ()),
            (("title",), staged.get("book_title"), ()),
            (("citation",), staged.get("citation_text"), ()),
            (("reference", "text"), staged.get("citation_text"), ()),
            (("year",), staged.get("_year"), ("id",)),
            (("school", "id"), "HFNU", ()),
            (("source", "document", "id"), staged.get("_source_document_id"), ()),
            (("source", "asset", "id"), staged.get("_source_asset_id"), ()),
            (("source", "locator"), staged.get("source_locator"), ()),
            (("source", "quote"), staged.get("source_quote"), ()),
            (("note",), staged.get("source_quote"), ()),
        ]
        for includes, value, excludes in mappings:
            if value not in (None, ""):
                set_semantic(row, fields, includes, value, excludes)
        for field in fields:
            lowered = field.lower()
            if lowered in {"status", "data_status"} and not row[field]:
                row[field] = "official"
            elif "source_level" in lowered and not row[field]:
                row[field] = "S"
            elif "confidence" in lowered and not row[field]:
                row[field] = "high"
        result.append((row, staged))
    return result


def build_fact_source_rows(
    entities: list[tuple[str, dict[str, str], dict[str, Any]]]
) -> list[dict[str, str]]:
    fields, _existing = read_csv(find_csv("fact_sources"))
    key = primary_key(fields, "fact_sources")
    rows: list[dict[str, str]] = []
    for table, entity, staged in entities:
        entity_key = primary_key(list(entity), table)
        entity_id = entity[entity_key]
        row = blank(fields)
        row[key] = stable(
            "FS-STAGE2A",
            table,
            entity_id,
            staged["_source_document_id"],
            staged.get("source_locator", ""),
        )
        mappings = [
            (("entity", "type"), table, ()),
            (("table", "name"), table, ()),
            (("entity", "id"), entity_id, ()),
            (("fact", "id"), entity_id, ()),
            (("source", "document", "id"), staged["_source_document_id"], ()),
            (("source", "asset", "id"), staged["_source_asset_id"], ()),
            (("source", "locator"), staged.get("source_locator", ""), ()),
            (("source", "quote"), staged.get("source_quote", ""), ()),
            (("source", "level"), "S", ()),
            (("year",), staged["_year"], ("id",)),
        ]
        for includes, value, excludes in mappings:
            set_semantic(row, fields, includes, value, excludes)
        rows.append(row)
    return rows


def apply_stage2a_normalized() -> dict[str, Any]:
    table_reports: list[dict[str, Any]] = []
    entities: list[tuple[str, dict[str, str], dict[str, Any]]] = []

    score_rows = build_score_rows()
    table_reports.append(merge("admission_scores", [row for row, _ in score_rows]))
    entities.extend(("admission_scores", row, staged) for row, staged in score_rows)

    for table, stage_kind, prefix in (
        ("application_statistics", "application_statistics", "APPSTAT-HFNU"),
        ("syllabus", "syllabus", "SYL-HFNU"),
        ("reference_books", "reference_books", "BOOK-HFNU"),
    ):
        rows = build_generic_rows(table, stage_kind, prefix)
        table_reports.append(merge(table, [row for row, _ in rows]))
        entities.extend((table, row, staged) for row, staged in rows)

    fact_rows = build_fact_source_rows(entities)
    table_reports.append(merge("fact_sources", fact_rows))

    payload = {
        "schema_version": "stage2a-hfnu-normalized-extension-v1",
        "ok": True,
        "tables": table_reports,
        "entity_rows": len(entities),
        "fact_source_rows": table_reports[-1]["added"],
    }
    REPORT_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(
        "Stage 2A HFNU normalized extension: PASS",
        {report["table"]: report["added"] for report in table_reports},
    )
    return payload


if __name__ == "__main__":
    apply_stage2a_normalized()
