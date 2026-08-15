#!/usr/bin/env python3
"""Capture the immutable Stage 2A baseline before HFNU integration changes.

This script is intentionally read-only with respect to raw/config/staging/
normalized/SQLite. It records repository counts, QA state and stable-ID rows so
later Stage 2A tests can prove that pre-existing canonical identifiers did not
move.
"""
from __future__ import annotations

import csv
import hashlib
import json
import os
import re
import sqlite3
import subprocess
from collections import OrderedDict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
REPO_ROOT = ROOT.parent
REPORTS = ROOT / "reports"
LOG_PATH = Path(os.environ.get("STAGE2A_BASELINE_LOG", "/tmp/stage2a-baseline.log"))
BASELINE_JSON = REPORTS / "stage2a_baseline.json"
BASELINE_MD = REPORTS / "stage2a_baseline.md"
STABLE_IDS_JSON = REPORTS / "stage2a_stable_ids_baseline.json"

STABLE_TABLES: OrderedDict[str, str] = OrderedDict(
    [
        ("institutions", "institution_id"),
        ("program_years", "program_year_id"),
        ("program_offerings", "offering_id"),
        ("enrollment_plans", "enrollment_plan_id"),
        ("exam_subjects", "exam_subject_id"),
        ("exam_sessions", "exam_session_id"),
        ("major_eligibility", "eligibility_id"),
        ("eligibility_rule_sets", "eligibility_rule_set_id"),
        ("eligibility_rule_items", "eligibility_rule_item_id"),
        ("admission_scores", "admission_score_id"),
        ("admission_rules", "rule_id"),
    ]
)


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def git(*args: str) -> str:
    process = subprocess.run(
        ["git", *args], cwd=REPO_ROOT, check=True, capture_output=True, text=True
    )
    return process.stdout.strip()


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def list_from_config(payload: Any, preferred_keys: tuple[str, ...]) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        for key in preferred_keys:
            value = payload.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
    return []


def count_files(path: Path, suffix: str | None = None) -> int:
    if not path.exists():
        return 0
    return sum(
        1
        for item in path.rglob("*")
        if item.is_file() and (suffix is None or item.suffix.lower() == suffix)
    )


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def normalized_counts() -> dict[str, int]:
    result: dict[str, int] = {}
    for path in sorted((ROOT / "normalized").glob("*.csv")):
        result[path.stem] = len(read_csv_rows(path))
    return result


def sqlite_counts() -> dict[str, int]:
    db_path = ROOT / "db" / "anhui_zsb.sqlite"
    if not db_path.is_file():
        return {}
    result: dict[str, int] = {}
    connection = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        tables = [
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
            )
        ]
        for table in tables:
            quoted = '"' + table.replace('"', '""') + '"'
            result[table] = int(connection.execute(f"SELECT COUNT(*) FROM {quoted}").fetchone()[0])
    finally:
        connection.close()
    return result


def parse_version() -> dict[str, str]:
    result: dict[str, str] = {}
    for line in (ROOT / "VERSION").read_text(encoding="utf-8").splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            result[key.strip()] = value.strip()
    return result


def parse_gate_log() -> dict[str, Any]:
    text = LOG_PATH.read_text(encoding="utf-8", errors="replace") if LOG_PATH.is_file() else ""
    p0_matches = re.findall(r"P0 errors:\s*(\d+)", text)
    p1_matches = re.findall(r"P1 warnings:\s*(\d+)", text)
    test_matches = re.findall(r"Ran\s+(\d+)\s+tests?", text)
    return {
        "p0": int(p0_matches[-1]) if p0_matches else None,
        "p1": int(p1_matches[-1]) if p1_matches else None,
        "unit_test_count": int(test_matches[-1]) if test_matches else None,
        "stage1_guard_pass": "Evidence tree guard: PASS" in text
        or "Stage 1 evidence tree guard: PASS" in text,
        "stage1_verifier_pass": "Stage 1 evidence verification: PASS" in text,
        "idempotence_pass": "Idempotence: PASS" in text,
        "clean_rebuild_pass": "Clean rebuild: PASS" in text,
        "quality_gate_pass": "Quality gate: PASS" in text,
        "log_sha256": sha256_file(LOG_PATH) if LOG_PATH.is_file() else "",
    }


def missing_counts() -> dict[str, int]:
    rows = read_csv_rows(ROOT / "qa" / "missing_data.csv")
    if not rows:
        return {"total": 0, "open": 0}
    status_key = next(
        (key for key in rows[0] if key.lower() in {"status", "state", "resolution_status"}),
        None,
    )
    if status_key is None:
        return {"total": len(rows), "open": len(rows)}
    closed = {"closed", "resolved", "done", "complete", "completed", "not_applicable"}
    open_count = sum(str(row.get(status_key, "")).strip().lower() not in closed for row in rows)
    return {"total": len(rows), "open": open_count}


def stable_id_snapshot() -> dict[str, Any]:
    tables: dict[str, Any] = {}
    normalized = ROOT / "normalized"
    for table, id_column in STABLE_TABLES.items():
        path = normalized / f"{table}.csv"
        rows = read_csv_rows(path)
        if rows and id_column not in rows[0]:
            raise RuntimeError(f"{path}: missing primary key column {id_column}")
        compact_rows = []
        for row in rows:
            primary_key = row.get(id_column, "")
            if not primary_key:
                raise RuntimeError(f"{path}: blank primary key")
            compact_rows.append(
                {
                    "id": primary_key,
                    "row": {key: value for key, value in row.items()},
                }
            )
        compact_rows.sort(key=lambda item: item["id"])
        tables[table] = {
            "id_column": id_column,
            "row_count": len(compact_rows),
            "rows": compact_rows,
        }
    return {
        "schema_version": "stage2a-stable-id-baseline-v1",
        "generated_at": now(),
        "base_sha": git("merge-base", "HEAD", "origin/main"),
        "tables": tables,
    }


def markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Stage 2A 基线报告",
        "",
        f"> 生成时间：{payload['generated_at']}",
        f"> 实际 main base：`{payload['git']['base_sha']}`",
        f"> 分支基线提交：`{payload['git']['head_sha']}`",
        "",
        "## 版本与门禁",
        "",
        f"- Schema version：`{payload['version'].get('schema_version', '')}`",
        f"- Stage 1 inventory SHA-256：`{payload['stage1_inventory']['sha256']}`",
        f"- P0：{payload['quality']['p0']}",
        f"- P1：{payload['quality']['p1']}",
        f"- Unit tests：{payload['quality']['unit_test_count']}",
        f"- Stage 1 guard：{'PASS' if payload['quality']['stage1_guard_pass'] else 'FAIL'}",
        f"- Stage 1 verifier：{'PASS' if payload['quality']['stage1_verifier_pass'] else 'FAIL'}",
        f"- Idempotence：{'PASS' if payload['quality']['idempotence_pass'] else 'FAIL'}",
        f"- Clean-room rebuild：{'PASS' if payload['quality']['clean_rebuild_pass'] else 'FAIL'}",
        f"- Quality gate：{'PASS' if payload['quality']['quality_gate_pass'] else 'FAIL'}",
        "",
        "## 输入层计数",
        "",
        f"- 正式 source documents：{payload['counts']['source_documents']}",
        f"- 正式 source assets：{payload['counts']['source_assets']}",
        f"- Raw 文件：{payload['counts']['raw_files']}",
        f"- Staging 文件：{payload['counts']['staging_files']}",
        f"- Missing total/open：{payload['missing']['total']} / {payload['missing']['open']}",
        "",
        "## Normalized 记录数",
        "",
        "| 表 | 记录数 |",
        "|---|---:|",
    ]
    for table, count in payload["normalized_counts"].items():
        lines.append(f"| {table} | {count} |")
    lines.extend(["", "## SQLite 记录数", "", "| 表 | 记录数 |", "|---|---:|"])
    for table, count in payload["sqlite_counts"].items():
        lines.append(f"| {table} | {count} |")
    lines.extend(
        [
            "",
            "## Stable ID 快照",
            "",
            f"完整快照：`reports/stage2a_stable_ids_baseline.json`",
            f"SHA-256：`{payload['stable_id_snapshot']['sha256']}`",
            "",
            "本报告生成于任何 HFNU Stage 2A 业务修改之前。",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    REPORTS.mkdir(parents=True, exist_ok=True)
    version = parse_version()
    source_catalog = list_from_config(
        read_json(ROOT / "config" / "source_catalog.json"),
        ("source_documents", "documents", "sources"),
    )
    source_assets = list_from_config(
        read_json(ROOT / "config" / "source_assets.json"),
        ("assets", "source_assets"),
    )
    inventory_path = ROOT / "config" / "phase1_evidence_inventory.json"

    stable = stable_id_snapshot()
    STABLE_IDS_JSON.write_text(
        json.dumps(stable, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    payload = {
        "schema_version": "stage2a-baseline-v1",
        "generated_at": now(),
        "git": {
            "base_sha": git("merge-base", "HEAD", "origin/main"),
            "main_sha_observed": git("rev-parse", "origin/main"),
            "head_sha": git("rev-parse", "HEAD"),
            "branch": os.environ.get("GITHUB_REF_NAME", "data/stage2a-hfnu-evidence-integration"),
        },
        "version": version,
        "stage1_inventory": {
            "path": "config/phase1_evidence_inventory.json",
            "sha256": sha256_file(inventory_path),
        },
        "counts": {
            "source_documents": len(source_catalog),
            "source_assets": len(source_assets),
            "raw_files": count_files(ROOT / "raw"),
            "staging_files": count_files(ROOT / "staging", ".json"),
        },
        "normalized_counts": normalized_counts(),
        "sqlite_counts": sqlite_counts(),
        "missing": missing_counts(),
        "quality": parse_gate_log(),
        "stable_id_snapshot": {
            "path": "reports/stage2a_stable_ids_baseline.json",
            "sha256": sha256_file(STABLE_IDS_JSON),
            "table_count": len(STABLE_TABLES),
            "row_count": sum(item["row_count"] for item in stable["tables"].values()),
        },
    }

    quality = payload["quality"]
    required_true = (
        "stage1_guard_pass",
        "stage1_verifier_pass",
        "idempotence_pass",
        "clean_rebuild_pass",
        "quality_gate_pass",
    )
    if any(not quality.get(key) for key in required_true):
        raise RuntimeError(f"baseline command result missing or failed: {quality}")
    if quality.get("p0") != 0 or quality.get("p1") != 0:
        raise RuntimeError(f"baseline P0/P1 is not zero: {quality}")
    if payload["git"]["base_sha"] != payload["git"]["main_sha_observed"]:
        raise RuntimeError(
            "Stage 2A branch is not based on the latest observed main: "
            f"{payload['git']}"
        )
    if version.get("schema_version") != "0.3.0":
        raise RuntimeError(f"unexpected schema version: {version}")

    BASELINE_JSON.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    BASELINE_MD.write_text(markdown(payload), encoding="utf-8")
    print(
        "Stage 2A baseline: PASS "
        f"(base={payload['git']['base_sha']}, sources={payload['counts']['source_documents']}, "
        f"assets={payload['counts']['source_assets']}, missing_open={payload['missing']['open']})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
