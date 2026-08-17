#!/usr/bin/env python3
"""Verify that Stage 2A preserves every pre-change business stable ID.

The baseline snapshot was captured from the exact post-Gate-0 main commit. This
check is intentionally schema-agnostic: it accepts the committed snapshot's
``tables`` mapping (lists of IDs or row dictionaries), resolves each normalized
CSV, and requires all baseline IDs/rows to remain unchanged. Additive Stage 2A
rows are allowed; mutation or disappearance of a baseline row is not.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
BASELINE_PATH = ROOT / "reports" / "stage2a_stable_ids_baseline.json"
REPORT_PATH = ROOT / "reports" / "stage2a_stable_ids_verification.json"


def table_mapping(payload: dict[str, Any]) -> dict[str, Any]:
    if isinstance(payload.get("tables"), dict):
        return payload["tables"]
    ignored = {
        "schema_version",
        "generated_at",
        "base_sha",
        "row_count",
        "table_count",
        "sha256",
        "metadata",
    }
    candidates = {
        key: value
        for key, value in payload.items()
        if key not in ignored and isinstance(value, (list, dict))
    }
    if not candidates:
        raise RuntimeError("stable-ID baseline has no table mapping")
    return candidates


def locate_csv(table: str) -> Path:
    direct = ROOT / "normalized" / f"{table}.csv"
    if direct.is_file():
        return direct
    matches = list((ROOT / "normalized").rglob(f"{table}.csv"))
    if len(matches) != 1:
        raise RuntimeError(f"cannot resolve normalized CSV for table {table!r}: {matches}")
    return matches[0]


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def primary_key(fields: list[str], table: str) -> str:
    preferred = [
        f"{table[:-1]}_id" if table.endswith("s") else f"{table}_id",
        "id",
    ]
    for name in preferred:
        if name in fields:
            return name
    candidates = [name for name in fields if name.endswith("_id")]
    if not candidates:
        raise RuntimeError(f"no stable-ID column found for {table}: {fields}")
    return candidates[0]


def normalize_baseline_rows(value: Any) -> tuple[str, list[Any]]:
    if isinstance(value, dict):
        for key in ("rows", "ids", "records", "values"):
            if isinstance(value.get(key), list):
                return key, value[key]
        if all(not isinstance(item, (dict, list)) for item in value.values()):
            return "dict_values", list(value.values())
    if isinstance(value, list):
        return "list", value
    raise RuntimeError(f"unsupported baseline table payload: {type(value).__name__}")


def main() -> int:
    baseline = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    tables = table_mapping(baseline)
    failures: list[str] = []
    details: dict[str, Any] = {}

    for table, raw_baseline in sorted(tables.items()):
        _kind, baseline_rows = normalize_baseline_rows(raw_baseline)
        csv_path = locate_csv(table)
        current = read_rows(csv_path)
        fields = list(current[0].keys()) if current else []
        pk = primary_key(fields, table)
        current_by_id = {row.get(pk, ""): row for row in current}

        missing: list[str] = []
        changed: list[str] = []
        if baseline_rows and isinstance(baseline_rows[0], dict):
            for baseline_row in baseline_rows:
                baseline_id = str(baseline_row.get(pk, ""))
                if not baseline_id:
                    id_fields = [key for key in baseline_row if key.endswith("_id")]
                    if len(id_fields) == 1:
                        baseline_id = str(baseline_row[id_fields[0]])
                current_row = current_by_id.get(baseline_id)
                if current_row is None:
                    missing.append(baseline_id)
                    continue
                for key, expected in baseline_row.items():
                    if key in current_row and str(current_row[key]) != str(expected):
                        changed.append(f"{baseline_id}:{key}")
        else:
            for value in baseline_rows:
                baseline_id = str(value)
                if baseline_id not in current_by_id:
                    missing.append(baseline_id)

        if missing:
            failures.append(f"{table}: {len(missing)} baseline IDs missing")
        if changed:
            failures.append(f"{table}: {len(changed)} baseline field values changed")
        details[table] = {
            "primary_key": pk,
            "baseline_count": len(baseline_rows),
            "current_count": len(current),
            "missing_ids": missing,
            "changed_fields": changed,
            "ok": not missing and not changed,
        }

    report = {
        "schema_version": "stage2a-stable-id-verification-v1",
        "ok": not failures,
        "baseline_path": BASELINE_PATH.relative_to(ROOT).as_posix(),
        "table_count": len(details),
        "tables": details,
        "failures": failures,
    }
    REPORT_PATH.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    if failures:
        print("Stage 2A stable ID verification: FAIL")
        for failure in failures:
            print(f"- {failure}")
        return 1
    print(
        "Stage 2A stable ID verification: PASS "
        f"({len(details)} tables, additive rows allowed)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
