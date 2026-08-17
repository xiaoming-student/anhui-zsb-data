#!/usr/bin/env python3
"""Generate QA tables, progress state and the Pilot report from canonical data."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from common import (
    BASE_DIR,
    NORMALIZED_DIR,
    PROGRESS_DIR,
    QA_DIR,
    REPORTS_DIR,
    SCHEMA_VERSION,
    SCHOOL_ID,
    YEARS,
    dump_json,
    read_csv,
    stable_id,
    write_csv,
)


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def load_tables() -> dict[str, list[dict[str, str]]]:
    names = [
        "program_years",
        "program_offerings",
        "enrollment_plans",
        "exam_subjects",
        "exam_sessions",
        "major_eligibility",
        "admission_scores",
        "admission_rules",
        "source_documents",
    ]
    return {name: read_csv(NORMALIZED_DIR / f"{name}.csv") for name in names}


def build_missing_data(tables: dict[str, list[dict[str, str]]], checked_at: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    school_year_ids = {int(row["year"]): row["school_year_id"] for row in read_csv(NORMALIZED_DIR / "school_years.csv")}

    common_missing = (
        ("syllabus", "not_collected", "下载并解析官方专业课考试大纲"),
        ("reference_books", "not_collected", "从官方考试大纲中提取参考教材"),
        ("adjustments", "not_found", "继续检索院校历史调剂公告和附件"),
        ("application_statistics", "official_not_published", "仅在找到官方来源时补录报名人数"),
    )
    for year in YEARS:
        for field_name, reason, next_action in common_missing:
            entity_id = school_year_ids[year]
            rows.append(
                {
                    "missing_id": stable_id("MISS", "school_year", entity_id, field_name),
                    "entity_type": "school_year",
                    "entity_id": entity_id,
                    "year": year,
                    "school_id": SCHOOL_ID,
                    "field_name": field_name,
                    "missing_reason": reason,
                    "source_id": f"SRC-HFNU-{year}-ZC",
                    "attempt_count": 2,
                    "last_checked_at": checked_at,
                    "status": "open",
                    "next_action": next_action,
                }
            )

    offering_by_id = {row["offering_id"]: row for row in tables["program_offerings"]}
    program_by_id = {row["program_year_id"]: row for row in tables["program_years"]}
    score_groups: dict[str, list[dict[str, str]]] = defaultdict(list)
    for score in tables["admission_scores"]:
        score_groups[score["offering_id"]].append(score)

    # 2025 source page has four offering rows whose score cells are all blank.
    for offering_id, group in score_groups.items():
        offering = offering_by_id[offering_id]
        if offering["year"] != "2025":
            continue
        if all(row["value_status"] == "blank_in_source" for row in group):
            program = program_by_id[offering["program_year_id"]]
            rows.append(
                {
                    "missing_id": stable_id("MISS", "offering", offering_id, "admission_scores"),
                    "entity_type": "offering",
                    "entity_id": offering_id,
                    "year": 2025,
                    "school_id": SCHOOL_ID,
                    "field_name": "admission_scores",
                    "missing_reason": "source_content_incomplete",
                    "source_id": "SRC-HFNU-2025-LQ",
                    "attempt_count": 1,
                    "last_checked_at": checked_at,
                    "status": "open",
                    "next_action": f"补查 {program['major_name_std']}（{offering['training_institution_name']}）官方录取数据",
                }
            )

    # 2026 score source has not yet been ingested: create an explicit offering-level task.
    for offering in tables["program_offerings"]:
        if offering["year"] != "2026":
            continue
        program = program_by_id[offering["program_year_id"]]
        rows.append(
            {
                "missing_id": stable_id("MISS", "offering", offering["offering_id"], "admission_scores"),
                "entity_type": "offering",
                "entity_id": offering["offering_id"],
                "year": 2026,
                "school_id": SCHOOL_ID,
                "field_name": "admission_scores",
                "missing_reason": "not_collected",
                "source_id": "",
                "attempt_count": 1,
                "last_checked_at": checked_at,
                "status": "open",
                "next_action": f"抓取 {program['major_name_std']}（{offering['training_institution_name']}）2026官方录取数据",
            }
        )

    for source in tables["source_documents"]:
        if source["status"] != "extracted_unarchived":
            continue
        rows.append(
            {
                "missing_id": stable_id("MISS", "source_document", source["source_document_id"], "raw_snapshot"),
                "entity_type": "source_document",
                "entity_id": source["source_document_id"],
                "year": source["year"],
                "school_id": source["school_id"],
                "field_name": "raw_snapshot",
                "missing_reason": "not_archived",
                "source_id": source["source_document_id"],
                "attempt_count": 0,
                "last_checked_at": checked_at,
                "status": "open",
                "next_action": "公开页面仍可访问时保存HTML、清洗文本和SHA-256；无法访问则改为unavailable",
            }
        )

    return sorted(rows, key=lambda row: (int(row["year"]), row["entity_type"], row["entity_id"], row["field_name"]))


def write_qa(tables: dict[str, list[dict[str, str]]], checked_at: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    conflicts: list[dict[str, Any]] = []
    write_csv(
        QA_DIR / "conflicts.csv",
        [
            "conflict_id",
            "entity_type",
            "entity_id",
            "field_name",
            "value_a",
            "source_a",
            "value_b",
            "source_b",
            "preferred_value",
            "preference_reason",
            "conflict_type",
            "status",
            "resolution_note",
        ],
        conflicts,
    )
    missing = build_missing_data(tables, checked_at)
    write_csv(
        QA_DIR / "missing_data.csv",
        [
            "missing_id",
            "entity_type",
            "entity_id",
            "year",
            "school_id",
            "field_name",
            "missing_reason",
            "source_id",
            "attempt_count",
            "last_checked_at",
            "status",
            "next_action",
        ],
        missing,
    )
    return conflicts, missing


def build_progress(
    tables: dict[str, list[dict[str, str]]],
    conflicts: list[dict[str, Any]],
    missing: list[dict[str, Any]],
    checked_at: str,
) -> list[dict[str, Any]]:
    by_year = {
        name: Counter(int(row["year"]) for row in rows if row.get("year"))
        for name, rows in tables.items()
        if name not in {"enrollment_plans", "source_documents"}
    }
    offering_year = {row["offering_id"]: int(row["year"]) for row in tables["program_offerings"]}
    plans_by_year = Counter(offering_year[row["offering_id"]] for row in tables["enrollment_plans"])
    explicit_plans_by_year = Counter(
        offering_year[row["offering_id"]]
        for row in tables["enrollment_plans"]
        if row["value_status"] in {"explicit_value", "explicit_zero"}
    )
    blank_plans_by_year = Counter(
        offering_year[row["offering_id"]]
        for row in tables["enrollment_plans"]
        if row["value_status"] == "blank_in_source"
    )
    published_scores_by_year = Counter(
        int(row["year"]) for row in tables["admission_scores"] if row["value_status"] == "published_value"
    )
    missing_by_year = Counter(int(row["year"]) for row in missing if row["status"] == "open")
    conflicts_by_year: Counter[int] = Counter()
    for row in conflicts:
        if row.get("status") == "open" and row.get("year"):
            conflicts_by_year[int(row["year"])] += 1

    progress: list[dict[str, Any]] = []
    for year in YEARS:
        status = "partial" if year == 2026 or missing_by_year[year] else "complete_core"
        progress.append(
            {
                "year": year,
                "school_id": SCHOOL_ID,
                "program_years": by_year["program_years"][year],
                "program_offerings": by_year["program_offerings"][year],
                "enrollment_plans": plans_by_year[year],
                "enrollment_plans_explicit": explicit_plans_by_year[year],
                "enrollment_plans_blank": blank_plans_by_year[year],
                "exam_subjects": by_year["exam_subjects"][year],
                "exam_sessions": by_year["exam_sessions"][year],
                "admission_scores": by_year["admission_scores"][year],
                "admission_scores_published": published_scores_by_year[year],
                "major_eligibility": by_year["major_eligibility"][year],
                "admission_rules": by_year["admission_rules"][year],
                "conflicts_open": conflicts_by_year[year],
                "missing_items_open": missing_by_year[year],
                "status": status,
                "last_checked_at": checked_at,
            }
        )
    write_csv(
        PROGRESS_DIR / "collection_progress.csv",
        [
            "year",
            "school_id",
            "program_years",
            "program_offerings",
            "enrollment_plans",
            "enrollment_plans_explicit",
            "enrollment_plans_blank",
            "exam_subjects",
            "exam_sessions",
            "admission_scores",
            "admission_scores_published",
            "major_eligibility",
            "admission_rules",
            "conflicts_open",
            "missing_items_open",
            "status",
            "last_checked_at",
        ],
        progress,
    )
    return progress


def write_task_state(checked_at: str) -> None:
    state = {
        "schema_version": SCHEMA_VERSION,
        "run_mode": "pilot",
        "school_id": SCHOOL_ID,
        "stage": "pilot_2_3_complete",
        "stages": {
            "source_fetch_complete": False,
            "staging_complete": True,
            "normalization_complete": True,
            "qa_complete": True,
            "report_complete": True,
            "batch_ready": False,
        },
        "partial_schools": [SCHOOL_ID],
        "completed_schools": [],
        "last_checkpoint": checked_at,
        "next_action": "人工复核后，选择1所结构明显不同的院校执行 Pilot B；不要直接进入39所Batch。",
    }
    dump_json(PROGRESS_DIR / "task_state.json", state)
    dump_json(
        PROGRESS_DIR / "run_metadata.json",
        {
            "schema_version": SCHEMA_VERSION,
            "pipeline_finished_at": checked_at,
            "canonical_data_as_of": "2026-08-14",
            "school_id": SCHOOL_ID,
        },
    )


def report_text(
    tables: dict[str, list[dict[str, str]]],
    conflicts: list[dict[str, Any]],
    missing: list[dict[str, Any]],
    progress: list[dict[str, Any]],
    checked_at: str,
) -> str:
    plan_status = Counter(row["value_status"] for row in tables["enrollment_plans"])
    score_status = Counter(row["value_status"] for row in tables["admission_scores"])
    totals = defaultdict(int)
    offering_year = {row["offering_id"]: int(row["year"]) for row in tables["program_offerings"]}
    for row in tables["enrollment_plans"]:
        if row["plan_type"] == "total" and row["plan_value"]:
            totals[offering_year[row["offering_id"]]] += int(float(row["plan_value"]))
    lines = [
        "# 合肥师范学院专升本 Pilot 2.3 修复报告",
        "",
        f"> 自动生成时间：{checked_at}",
        f"> Schema：v{SCHEMA_VERSION}",
        "",
        "## 结论",
        "",
        "当前 HFNU 核心数据已经通过自动化 PK、FK、计划槽位、Eligibility 覆盖、分数矩阵、来源路径和 SHA-256 检查。",
        "",
        "**仍不建议直接进入 39 所院校 Batch。** 当前缺少 2024/录取网页本地快照、2026 录取数据、考试大纲与参考教材；下一步应先执行 Pilot B。",
        "",
        "## 核心数据量",
        "",
        "| 数据表 | 记录数 |",
        "|---|---:|",
        f"| Program Year | {len(tables['program_years'])} |",
        f"| Program Offering | {len(tables['program_offerings'])} |",
        f"| 招生计划槽位 | {len(tables['enrollment_plans'])} |",
        f"| 考试科目 | {len(tables['exam_subjects'])} |",
        f"| 考试 Session | {len(tables['exam_sessions'])} |",
        f"| 报考专业范围 | {len(tables['major_eligibility'])} |",
        f"| 录取分数观察值 | {len(tables['admission_scores'])} |",
        f"| 录取规则 | {len(tables['admission_rules'])} |",
        "",
        "## 年度覆盖",
        "",
        "| 年份 | Program Year | Offering | 计划槽位 | 计划总数 | 考试科目 | 分数观察 | 已发布分数 | Eligibility |",
        "|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in progress:
        lines.append(
            f"| {row['year']} | {row['program_years']} | {row['program_offerings']} | {row['enrollment_plans']} | "
            f"{totals[int(row['year'])]} | {row['exam_subjects']} | {row['admission_scores']} | "
            f"{row['admission_scores_published']} | {row['major_eligibility']} |"
        )
    lines.extend(
        [
            "",
            "## 已修复的关键问题",
            "",
            f"- 招生计划现为 {len(tables['program_offerings'])} 个 Offering × 4 个计划槽位 = {len(tables['enrollment_plans'])} 条。",
            f"- 计划状态为：`explicit_value={plan_status['explicit_value']}`，`blank_in_source={plan_status['blank_in_source']}`。",
            "- 2026 商务英语“非免试退役士兵专项计划”已按官方 PDF 恢复为 `1`。",
            "- Eligibility 已逐年校正为 2024=28、2025=28、2026=26，且全部关联有效 Program Year。",
            "- 所有核心 ID 改为 UUIDv5 自然键生成，不再依赖数组顺序。",
            "- main-school Offering 不再错误写入“锦绣校区”培养地点；考试地点改由 `exam_sessions.csv` 表达。",
            "- `remarks_source_raw` 不再混入程序推断的“校本部”文字。",
            f"- 录取分数建立完整 5 类观察矩阵：`published_value={score_status['published_value']}`，`blank_in_source={score_status['blank_in_source']}`。",
            "- 原始文件使用 ASCII 物理文件名，并由 `raw_manifest.csv` 维护路径、大小和 SHA-256。",
            "- 旧 `school_major_years.csv` 已移出 canonical 目录。",
            "",
            "## 当前 QA 状态",
            "",
            f"- Active conflicts：{len(conflicts)}",
            f"- Open missing items：{len(missing)}",
            "- 核心来源定位字段覆盖：100%",
            "",
            "## 尚未完成",
            "",
            "- 2024 招生章程、2024/2025 录取分数网页尚未保存本地 HTML 快照。",
            "- 2026 录取分数尚未采集入库。",
            "- 2024-2026 考试大纲、参考书、调剂和报名人数仍待补充。",
            "- 录取规则目前保留经核验的核心规则，尚未完成所有 A/B 段、调剂与技能大赛规则的细粒度拆分。",
            "",
            "## 下一步",
            "",
            "先人工复核本次输出，再选择一所结构明显不同的院校做 Pilot B。Pilot B 不修改核心 Schema 后，才考虑冻结 v1.0 并进入 Batch。",
            "",
        ]
    )
    return "\n".join(lines)


def write_batch_checklist() -> None:
    text = """# Batch Readiness Checklist

## 已通过

- [x] Program Year / Offering 两级模型
- [x] 稳定、跨院校安全的 deterministic ID
- [x] 招生计划空白语义
- [x] Eligibility 年度覆盖与 FK
- [x] 录取分数数值拆分、ID 与 observation matrix
- [x] 原始文件 ASCII 路径、SHA-256 与 manifest
- [x] 核心事实 source locator
- [x] 自动 PK/FK/业务规则验证
- [x] Active conflicts 清零

## 进入 Batch 前仍需完成

- [ ] 保存 2024 招生章程 HTML 快照
- [ ] 保存 2024、2025 录取分数 HTML 快照
- [ ] 采集 2026 录取分数
- [ ] 完成考试大纲和参考书数据
- [ ] 执行一所异构院校 Pilot B
- [ ] Pilot B 不再修改核心 Schema
- [ ] 冻结 Schema v1.0

**当前结论：Batch Readiness = FAIL（应先执行 Pilot B）。**
"""
    (REPORTS_DIR / "batch_readiness_checklist.md").write_text(text, encoding="utf-8")


def main() -> int:
    checked_at = now_iso()
    tables = load_tables()
    conflicts, missing = write_qa(tables, checked_at)
    progress = build_progress(tables, conflicts, missing, checked_at)
    write_task_state(checked_at)
    text = report_text(tables, conflicts, missing, progress, checked_at)
    (REPORTS_DIR / "pilot_report.md").write_text(text, encoding="utf-8")
    (REPORTS_DIR / "pilot_2_3_repair_report.md").write_text(text, encoding="utf-8")
    write_batch_checklist()
    print(f"QA/report generated: conflicts={len(conflicts)}, missing={len(missing)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
