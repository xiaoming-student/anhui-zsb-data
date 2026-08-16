#!/usr/bin/env python3
"""Audit the 42-school raw-evidence tree without altering raw source files."""
from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

VALID_STATUSES = {
    "collected",
    "official_not_published",
    "not_found",
    "not_applicable",
    "removed_or_unavailable",
    "access_restricted",
    "manual_download_required",
    "public_official_record",
    "awaiting_manual_review",
}
COLLECTED_STATUSES = {"collected", "public_official_record"}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def load_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return default


def read_coverage(path: Path, years: list[int], topics: list[str]) -> tuple[dict[tuple[int, str], str], list[str]]:
    expected = {(year, topic) for year in years for topic in topics}
    rows: dict[tuple[int, str], str] = {}
    errors: list[str] = []
    if not path.is_file():
        return rows, ["coverage_missing"]
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            for line_no, row in enumerate(csv.DictReader(handle), start=2):
                try:
                    key = (int(row["year"]), row["topic"])
                    status = row["status"]
                except (KeyError, TypeError, ValueError):
                    errors.append(f"invalid_row:{line_no}")
                    continue
                if key not in expected:
                    errors.append(f"unexpected_cell:{key[0]}:{key[1]}")
                    continue
                if status not in VALID_STATUSES:
                    errors.append(f"invalid_status:{key[0]}:{key[1]}:{status}")
                if key in rows:
                    errors.append(f"duplicate_cell:{key[0]}:{key[1]}")
                rows[key] = status
    except OSError as exc:
        errors.append(f"coverage_read_error:{exc}")
    missing = expected - set(rows)
    for year, topic in sorted(missing):
        errors.append(f"missing_cell:{year}:{topic}")
    return rows, errors


def year_raw_files(school_dir: Path, year: int) -> list[Path]:
    year_dir = school_dir / str(year)
    if not year_dir.is_dir():
        return []
    return sorted(path for path in year_dir.rglob("*") if path.is_file())


def audit_school(repo_root: Path, school: dict[str, Any], years: list[int], topics: list[str]) -> dict[str, Any]:
    evidence_root = repo_root / "anhui_zsb_data" / "evidence" / "full_raw_30_schools"
    school_dir = evidence_root / school["school_id"]
    manifest_path = school_dir / "school_manifest.json"
    coverage_path = school_dir / "school_coverage.csv"
    manifest = load_json(manifest_path, {}) if manifest_path.is_file() else {}
    coverage, coverage_errors = read_coverage(coverage_path, years, topics)
    status_counts = Counter(coverage.values())
    raw_files_by_year = {str(year): year_raw_files(school_dir, year) for year in years}
    all_raw_files = [path for files in raw_files_by_year.values() for path in files]
    raw_bytes = sum(path.stat().st_size for path in all_raw_files)
    collected_by_year = {
        str(year): sum(1 for topic in topics if coverage.get((year, topic)) in COLLECTED_STATUSES)
        for year in years
    }
    explicit_by_year = {
        str(year): sum(1 for topic in topics if coverage.get((year, topic)) in VALID_STATUSES)
        for year in years
    }
    failures = manifest.get("failures") if isinstance(manifest, dict) else []
    sources = manifest.get("sources") if isinstance(manifest, dict) else []
    assets = manifest.get("assets") if isinstance(manifest, dict) else []
    return {
        "school_id": school["school_id"],
        "school_name": school["school_name"],
        "school_type": school["school_type"],
        "official_domain": school["official_domain"],
        "priority": school["priority"],
        "directory_exists": school_dir.is_dir(),
        "manifest_exists": manifest_path.is_file(),
        "coverage_exists": coverage_path.is_file(),
        "coverage_cells": len(coverage),
        "coverage_errors": coverage_errors,
        "status_counts": dict(sorted(status_counts.items())),
        "collected_cells": sum(status_counts.get(status, 0) for status in COLLECTED_STATUSES),
        "explicit_status_cells": sum(1 for status in coverage.values() if status in VALID_STATUSES),
        "collected_by_year": collected_by_year,
        "explicit_by_year": explicit_by_year,
        "raw_file_count": len(all_raw_files),
        "raw_file_count_by_year": {year: len(files) for year, files in raw_files_by_year.items()},
        "raw_bytes": raw_bytes,
        "manifest_source_count": len(sources) if isinstance(sources, list) else 0,
        "manifest_asset_count": len(assets) if isinstance(assets, list) else 0,
        "manifest_failure_count": len(failures) if isinstance(failures, list) else 0,
        "last_attempt_at": manifest.get("last_attempt_at", "") if isinstance(manifest, dict) else "",
    }


def build_audit(repo_root: Path) -> dict[str, Any]:
    config_path = repo_root / "anhui_zsb_data" / "config" / "full_42_school_scope.json"
    config = load_json(config_path, {})
    if not isinstance(config, dict) or len(config.get("schools") or []) != 42:
        raise ValueError(f"invalid or missing 42-school scope config: {config_path}")
    years = [int(value) for value in config["years"]]
    topics = [str(value) for value in config["topics"]]
    schools = [audit_school(repo_root, item, years, topics) for item in config["schools"]]
    global_status = Counter()
    for school in schools:
        global_status.update(school["status_counts"])
    expected_cells = len(schools) * len(years) * len(topics)
    return {
        "schema_version": "full-42-raw-evidence-audit-v1",
        "generated_at": utc_now(),
        "source_sha": config.get("source_sha", ""),
        "school_count": len(schools),
        "years": years,
        "topics": topics,
        "expected_coverage_cells": expected_cells,
        "directory_count": sum(1 for school in schools if school["directory_exists"]),
        "manifest_count": sum(1 for school in schools if school["manifest_exists"]),
        "coverage_file_count": sum(1 for school in schools if school["coverage_exists"]),
        "explicit_status_cells": sum(school["explicit_status_cells"] for school in schools),
        "collected_cells": sum(school["collected_cells"] for school in schools),
        "raw_file_count": sum(school["raw_file_count"] for school in schools),
        "raw_bytes": sum(school["raw_bytes"] for school in schools),
        "global_status_counts": dict(sorted(global_status.items())),
        "schools": schools,
    }


def pct(value: int, denominator: int) -> str:
    return f"{(value / denominator * 100):.2f}%" if denominator else "0.00%"


def render_markdown(audit: dict[str, Any]) -> str:
    years = audit["years"]
    topic_count = len(audit["topics"])
    expected = audit["expected_coverage_cells"]
    lines = [
        "# 安徽专升本 42 校全量原始证据审计",
        "",
        f"- 生成时间：{audit['generated_at']}",
        f"- 审计基准 SHA：`{audit['source_sha']}`",
        f"- 理论覆盖单元：**{expected}**（42 校 × {len(years)} 年 × {topic_count} 主题）",
        f"- 已建学校目录：**{audit['directory_count']} / 42**",
        f"- 已有 coverage 文件：**{audit['coverage_file_count']} / 42**",
        f"- 已有明确状态：**{audit['explicit_status_cells']} / {expected}**（{pct(audit['explicit_status_cells'], expected)}）",
        f"- 已采集覆盖单元：**{audit['collected_cells']} / {expected}**（{pct(audit['collected_cells'], expected)}）",
        f"- 年份目录内原始文件：**{audit['raw_file_count']}**，共 **{audit['raw_bytes']} bytes**",
        "",
        "## 全局状态",
        "",
        "| status | 单元数 |",
        "|---|---:|",
    ]
    for status, count in audit["global_status_counts"].items():
        lines.append(f"| `{status}` | {count} |")
    lines += [
        "",
        "## 逐校审计",
        "",
        "| ID | 学校 | 优先级 | 目录 | 原始文件 | 原始字节 | source | asset | 明确状态 | 已采集 | 2024 | 2025 | 2026 | 错误 |",
        "|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for school in audit["schools"]:
        cells_per_school = len(years) * topic_count
        by_year = school["collected_by_year"]
        lines.append(
            "| {school_id} | {school_name} | {priority} | {directory} | {raw_files} | {raw_bytes} | "
            "{source_count} | {asset_count} | {explicit}/{expected} | {collected}/{expected} | "
            "{y2024}/{topics} | {y2025}/{topics} | {y2026}/{topics} | {errors} |".format(
                school_id=school["school_id"],
                school_name=school["school_name"],
                priority=school["priority"],
                directory="是" if school["directory_exists"] else "否",
                raw_files=school["raw_file_count"],
                raw_bytes=school["raw_bytes"],
                source_count=school["manifest_source_count"],
                asset_count=school["manifest_asset_count"],
                explicit=school["explicit_status_cells"],
                collected=school["collected_cells"],
                expected=cells_per_school,
                y2024=by_year.get("2024", 0),
                y2025=by_year.get("2025", 0),
                y2026=by_year.get("2026", 0),
                topics=topic_count,
                errors=len(school["coverage_errors"]),
            )
        )
    lines += [
        "",
        "## 缺失与受限明细",
        "",
    ]
    for school in audit["schools"]:
        if not school["directory_exists"] or school["coverage_errors"] or school["collected_cells"] < len(years) * topic_count:
            lines.append(f"### {school['school_id']} {school['school_name']}")
            lines.append("")
            lines.append(f"- 状态分布：`{json.dumps(school['status_counts'], ensure_ascii=False, sort_keys=True)}`")
            lines.append(f"- coverage 异常：{len(school['coverage_errors'])}")
            if school["coverage_errors"]:
                lines.append("- 异常样例：" + "；".join(school["coverage_errors"][:10]))
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument(
        "--json-output",
        type=Path,
        default=Path("anhui_zsb_data/reports/full_42_raw_evidence_audit.json"),
    )
    parser.add_argument(
        "--markdown-output",
        type=Path,
        default=Path("anhui_zsb_data/reports/full_42_raw_evidence_audit.md"),
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = args.repo_root.resolve()
    audit = build_audit(repo_root)
    json_path = args.json_output if args.json_output.is_absolute() else repo_root / args.json_output
    md_path = args.markdown_output if args.markdown_output.is_absolute() else repo_root / args.markdown_output
    json_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    md_path.write_text(render_markdown(audit), encoding="utf-8")
    print(json.dumps({
        "schools": audit["school_count"],
        "expected_cells": audit["expected_coverage_cells"],
        "explicit_status_cells": audit["explicit_status_cells"],
        "collected_cells": audit["collected_cells"],
        "raw_file_count": audit["raw_file_count"],
        "raw_bytes": audit["raw_bytes"],
        "json": str(json_path),
        "markdown": str(md_path),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
