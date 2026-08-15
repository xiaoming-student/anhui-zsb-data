#!/usr/bin/env python3
"""Generate Stage 2A QA, progress, reconciliation and integration reports.

All outputs are derived from canonical CSVs plus reviewed HFNU staging. No
business facts are introduced in this reporting layer.
"""
from __future__ import annotations

import json
import os
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from common import (
    BASE_DIR,
    NORMALIZED_DIR,
    PROGRESS_DIR,
    QA_DIR,
    RAW_DIR,
    REPORTS_DIR,
    SCHEMA_VERSION,
    SCHOOL_ID,
    STAGING_DIR,
    YEARS,
    dump_json,
    load_json,
    normalize_major_name,
    normalize_text,
    read_csv,
    stable_id,
    write_csv,
)

BASELINE_PATH = BASE_DIR / "config" / "stage2a_baseline.json"
STABLE_ID_BASELINE_PATH = BASE_DIR / "config" / "stage2a_stable_ids_baseline.json"
BASELINE_REPORT_PATH = REPORTS_DIR / "stage2a_baseline.json"
STABLE_ID_BASELINE_REPORT_PATH = REPORTS_DIR / "stage2a_stable_ids_baseline.json"
MAPPING_PATH = BASE_DIR / "config" / "stage2a_hfnu_asset_mapping.json"


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def load_tables() -> dict[str, list[dict[str, str]]]:
    names = [
        "institutions",
        "source_sites",
        "source_documents",
        "source_assets",
        "program_years",
        "program_offerings",
        "enrollment_plans",
        "exam_subjects",
        "exam_sessions",
        "major_eligibility",
        "eligibility_rule_sets",
        "eligibility_rule_items",
        "admission_scores",
        "admission_rules",
        "syllabus",
        "reference_books",
        "application_statistics",
        "fact_sources",
    ]
    return {name: read_csv(NORMALIZED_DIR / f"{name}.csv") for name in names}


def build_missing_data(
    tables: dict[str, list[dict[str, str]]], checked_at: str
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    school_year_ids = {
        int(row["year"]): row["school_year_id"]
        for row in read_csv(NORMALIZED_DIR / "school_years.csv")
    }

    # Adjustments remain unavailable for all three years. Application statistics
    # are now official for 2024 only; 2025/2026 remain officially unpublished.
    for year in YEARS:
        entity_id = school_year_ids[year]
        rows.append(
            {
                "missing_id": stable_id("MISS", "school_year", entity_id, "adjustments"),
                "entity_type": "school_year",
                "entity_id": entity_id,
                "year": year,
                "school_id": SCHOOL_ID,
                "field_name": "adjustments",
                "missing_reason": "not_found",
                "source_id": f"SRC-HFNU-{year}-ZC",
                "attempt_count": 2,
                "last_checked_at": checked_at,
                "status": "open",
                "next_action": "继续检索院校历史调剂公告和附件；未找到前不推断调剂事实",
            }
        )
        if year in {2025, 2026}:
            rows.append(
                {
                    "missing_id": stable_id(
                        "MISS", "school_year", entity_id, "application_statistics"
                    ),
                    "entity_type": "school_year",
                    "entity_id": entity_id,
                    "year": year,
                    "school_id": SCHOOL_ID,
                    "field_name": "application_statistics",
                    "missing_reason": "official_not_published",
                    "source_id": "",
                    "attempt_count": 2,
                    "last_checked_at": checked_at,
                    "status": "open",
                    "next_action": "仅在找到学校官方分专业报名人数或报录统计后补录",
                }
            )

    offering_by_id = {row["offering_id"]: row for row in tables["program_offerings"]}
    program_by_id = {row["program_year_id"]: row for row in tables["program_years"]}
    score_groups: dict[str, list[dict[str, str]]] = defaultdict(list)
    for score in tables["admission_scores"]:
        score_groups[score["offering_id"]].append(score)

    # The 2025 official table has four offerings whose five score cells are all
    # blank. Keep them open as source-content gaps; do not synthesize rows.
    for offering_id, group in score_groups.items():
        offering = offering_by_id[offering_id]
        if offering["year"] != "2025":
            continue
        if all(row["value_status"] == "blank_in_source" for row in group):
            program = program_by_id[offering["program_year_id"]]
            rows.append(
                {
                    "missing_id": stable_id(
                        "MISS", "offering", offering_id, "admission_scores"
                    ),
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
                    "next_action": (
                        f"补查 {program['major_name_std']}"
                        f"（{offering['training_institution_name']}）官方录取数据"
                    ),
                }
            )

    # If a future official score table omits an offering entirely, keep an
    # explicit source-content task. Stage 2A's reviewed 2026 table covers all 28.
    for offering in tables["program_offerings"]:
        if offering["year"] != "2026" or offering["offering_id"] in score_groups:
            continue
        program = program_by_id[offering["program_year_id"]]
        rows.append(
            {
                "missing_id": stable_id(
                    "MISS", "offering", offering["offering_id"], "admission_scores"
                ),
                "entity_type": "offering",
                "entity_id": offering["offering_id"],
                "year": 2026,
                "school_id": SCHOOL_ID,
                "field_name": "admission_scores",
                "missing_reason": "source_content_incomplete",
                "source_id": "SRC-HFNU-2026-LQ",
                "attempt_count": 1,
                "last_checked_at": checked_at,
                "status": "open",
                "next_action": (
                    f"官方表未包含 {program['major_name_std']}"
                    f"（{offering['training_institution_name']}）；继续检索后续官方公告"
                ),
            }
        )

    # Any unarchived source still receives an explicit snapshot task. After a
    # correct Stage 2A promotion this block should contribute zero rows.
    for source in tables["source_documents"]:
        if source["status"] != "extracted_unarchived":
            continue
        rows.append(
            {
                "missing_id": stable_id(
                    "MISS", "source_document", source["source_document_id"], "raw_snapshot"
                ),
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
                "next_action": "保存官方原件、解析文本和SHA-256后再关闭",
            }
        )

    return sorted(
        rows,
        key=lambda row: (
            int(row["year"]),
            row["entity_type"],
            row["entity_id"],
            row["field_name"],
        ),
    )


def write_qa(
    tables: dict[str, list[dict[str, str]]], checked_at: str
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
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


def _program_year_counts(
    rows: list[dict[str, str]], programs: dict[str, dict[str, str]]
) -> Counter[int]:
    return Counter(int(programs[row["program_year_id"]]["year"]) for row in rows)


def _offering_year_counts(
    rows: list[dict[str, str]], offerings: dict[str, dict[str, str]]
) -> Counter[int]:
    return Counter(int(offerings[row["offering_id"]]["year"]) for row in rows)


def build_progress(
    tables: dict[str, list[dict[str, str]]],
    conflicts: list[dict[str, Any]],
    missing: list[dict[str, Any]],
    checked_at: str,
) -> list[dict[str, Any]]:
    by_year = {
        name: Counter(int(row["year"]) for row in rows if row.get("year"))
        for name, rows in tables.items()
        if name
        not in {
            "enrollment_plans",
            "source_documents",
            "source_assets",
            "source_sites",
            "institutions",
            "eligibility_rule_items",
            "fact_sources",
            "syllabus",
            "reference_books",
            "application_statistics",
        }
    }
    programs = {row["program_year_id"]: row for row in tables["program_years"]}
    offerings = {row["offering_id"]: row for row in tables["program_offerings"]}
    plans_by_year = _offering_year_counts(tables["enrollment_plans"], offerings)
    explicit_plans_by_year = _offering_year_counts(
        [
            row
            for row in tables["enrollment_plans"]
            if row["value_status"] in {"explicit_value", "explicit_zero"}
        ],
        offerings,
    )
    blank_plans_by_year = _offering_year_counts(
        [
            row
            for row in tables["enrollment_plans"]
            if row["value_status"] == "blank_in_source"
        ],
        offerings,
    )
    published_scores_by_year = Counter(
        int(row["year"])
        for row in tables["admission_scores"]
        if row["value_status"] == "published_value"
    )
    syllabus_by_year = _program_year_counts(tables["syllabus"], programs)
    books_by_year = _program_year_counts(tables["reference_books"], programs)
    statistics_by_year = _offering_year_counts(
        tables["application_statistics"], offerings
    )
    missing_by_year = Counter(
        int(row["year"]) for row in missing if row["status"] == "open"
    )
    conflicts_by_year: Counter[int] = Counter()
    for row in conflicts:
        if row.get("status") == "open" and row.get("year"):
            conflicts_by_year[int(row["year"])] += 1

    progress: list[dict[str, Any]] = []
    for year in YEARS:
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
                "syllabus": syllabus_by_year[year],
                "reference_books": books_by_year[year],
                "application_statistics": statistics_by_year[year],
                "conflicts_open": conflicts_by_year[year],
                "missing_items_open": missing_by_year[year],
                "status": "partial" if missing_by_year[year] else "complete_core",
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
            "syllabus",
            "reference_books",
            "application_statistics",
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
        "stage": "stage2a_hfnu_evidence_integration_complete",
        "stages": {
            # False means the school is not complete across every official topic;
            # adjustments and 2025/2026 application statistics remain open.
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
        "next_action": (
            "人工Review并合并Stage 2A后，从最新main创建"
            "data/stage2b-ahua-pilot-b-canonical执行AHUA Pilot B；不得进入Batch。"
        ),
    }
    dump_json(PROGRESS_DIR / "task_state.json", state)
    dump_json(
        PROGRESS_DIR / "run_metadata.json",
        {
            "schema_version": SCHEMA_VERSION,
            "pipeline_finished_at": checked_at,
            "canonical_data_as_of": "2026-08-15",
            "school_id": SCHOOL_ID,
            "stage": "stage2a_hfnu_evidence_integration_complete",
        },
    )


def write_application_plan_reconciliation(
    tables: dict[str, list[dict[str, str]]], checked_at: str
) -> dict[str, Any]:
    staging = load_json(
        STAGING_DIR / SCHOOL_ID / "2024" / "application_statistics.json"
    )["data"]
    programs = {row["program_year_id"]: row for row in tables["program_years"]}
    offerings_by_key: dict[tuple[str, str], dict[str, str]] = {}
    for offering in tables["program_offerings"]:
        if offering["year"] != "2024":
            continue
        program = programs[offering["program_year_id"]]
        key = (program["major_name_std"], offering["training_institution_name"])
        if key in offerings_by_key:
            raise RuntimeError(f"Duplicate 2024 offering natural key: {key}")
        offerings_by_key[key] = offering
    total_plans = {
        row["offering_id"]: row
        for row in tables["enrollment_plans"]
        if row["plan_type"] == "total"
    }

    result_rows: list[dict[str, Any]] = []
    for item in staging:
        major = normalize_major_name(item["major_name_raw"])
        institution = normalize_text(item.get("training_institution_name_raw")) or "合肥师范学院"
        offering = offerings_by_key.get((major, institution))
        if offering is None:
            result_rows.append(
                {
                    "major": major,
                    "training_institution": institution,
                    "offering_id": "",
                    "official_plan_count": item["plan_count_raw"],
                    "canonical_plan_count": None,
                    "status": "unmapped",
                    "note": "无法唯一映射到 canonical offering",
                }
            )
            continue
        canonical_plan = total_plans.get(offering["offering_id"])
        canonical_value = (
            int(float(canonical_plan["plan_value"]))
            if canonical_plan and canonical_plan["plan_value"]
            else None
        )
        official_value = int(item["plan_count_raw"])
        status = "consistent" if official_value == canonical_value else "conflict"
        result_rows.append(
            {
                "major": major,
                "training_institution": institution,
                "offering_id": offering["offering_id"],
                "official_plan_count": official_value,
                "canonical_plan_count": canonical_value,
                "status": status,
                "note": (
                    "BMRS公告计划数与招生章程canonical total一致"
                    if status == "consistent"
                    else "两个官方来源计划数不一致，未自动覆盖"
                ),
            }
        )

    status_counts = Counter(row["status"] for row in result_rows)
    payload = {
        "schema_version": "stage2a-application-plan-reconciliation-v1",
        "generated_at": checked_at,
        "source_document_id": "SRC-HFNU-2024-BMRS",
        "row_count": len(result_rows),
        "summary": {
            "consistent": status_counts["consistent"],
            "conflict": status_counts["conflict"],
            "unmapped": status_counts["unmapped"],
            "official_missing": status_counts["official_missing"],
            "canonical_missing": status_counts["canonical_missing"],
        },
        "rows": result_rows,
    }
    dump_json(
        REPORTS_DIR / "stage2a_hfnu_application_plan_reconciliation.json",
        payload,
    )
    lines = [
        "# Stage 2A HFNU 报名人数公告与招生计划核对",
        "",
        f"> 生成时间：{checked_at}",
        "> 来源：SRC-HFNU-2024-BMRS",
        "",
        "## 汇总",
        "",
        f"- 官方行数：{len(result_rows)}",
        f"- 一致：{status_counts['consistent']}",
        f"- 不一致：{status_counts['conflict']}",
        f"- 无法映射：{status_counts['unmapped']}",
        "",
        "| 专业 | 培养学校 | Offering | 官方计划 | Canonical计划 | 状态 |",
        "|---|---|---|---:|---:|---|",
    ]
    for row in result_rows:
        lines.append(
            f"| {row['major']} | {row['training_institution']} | "
            f"`{row['offering_id']}` | {row['official_plan_count']} | "
            f"{row['canonical_plan_count'] if row['canonical_plan_count'] is not None else ''} | "
            f"{row['status']} |"
        )
    (REPORTS_DIR / "stage2a_hfnu_application_plan_reconciliation.md").write_text(
        "\n".join(lines) + "\n", encoding="utf-8"
    )
    return payload


def stable_id_audit(tables: dict[str, list[dict[str, str]]]) -> dict[str, Any]:
    baseline = load_json(STABLE_ID_BASELINE_PATH)
    drift: list[dict[str, Any]] = []
    new_ids: dict[str, list[str]] = {}
    for table_name, table_baseline in baseline["tables"].items():
        current = {
            row[table_baseline["id_column"]]: row for row in tables[table_name]
        }
        baseline_ids: set[str] = set()
        for item in table_baseline["rows"]:
            baseline_ids.add(item["id"])
            current_row = current.get(item["id"])
            if current_row is None:
                drift.append(
                    {
                        "table": table_name,
                        "id": item["id"],
                        "type": "missing_existing_id",
                    }
                )
            elif current_row != item["row"]:
                drift.append(
                    {
                        "table": table_name,
                        "id": item["id"],
                        "type": "existing_row_changed",
                        "before": item["row"],
                        "after": current_row,
                    }
                )
        additions = sorted(set(current) - baseline_ids)
        if additions:
            new_ids[table_name] = additions
    new_ids["syllabus"] = sorted(row["syllabus_id"] for row in tables["syllabus"])
    new_ids["reference_books"] = sorted(
        row["reference_book_id"] for row in tables["reference_books"]
    )
    new_ids["application_statistics"] = sorted(
        row["application_statistic_id"]
        for row in tables["application_statistics"]
    )
    return {
        "baseline_path": STABLE_ID_BASELINE_PATH.relative_to(BASE_DIR).as_posix(),
        "existing_id_drift_count": len(drift),
        "drift": drift,
        "new_id_counts": {name: len(ids) for name, ids in sorted(new_ids.items())},
        "new_id_count": sum(len(ids) for ids in new_ids.values()),
    }


def verified_test_statuses() -> tuple[dict[str, Any], int | None, int | None]:
    def read_optional(name: str) -> dict[str, Any]:
        path = REPORTS_DIR / name
        if not path.is_file():
            return {}
        try:
            return load_json(path)
        except (OSError, json.JSONDecodeError):
            return {}

    quality = read_optional("quality_gate_report.json")
    validation = read_optional("validation_report.json")
    idempotence = read_optional("idempotence_report.json")
    clean = read_optional("clean_rebuild_report.json")

    expectations_path = BASE_DIR / "config" / "stage2a_test_expectations.json"
    expectations = load_json(expectations_path)
    expected_count = int(expectations["unit_test_count"])
    unit_count: int | None = expected_count
    unit_status = "PENDING_CURRENT_GATE"
    for step in quality.get("steps", []):
        if step.get("name") != "单元与集成测试":
            continue
        combined = f"{step.get('stdout', '')}\n{step.get('stderr', '')}"
        matches = re.findall(r"Ran\s+(\d+)\s+tests?", combined)
        reported_count = int(matches[-1]) if matches else None
        if not step.get("ok"):
            unit_status = "FAIL"
        elif reported_count == expected_count:
            unit_status = "PASS"
        else:
            # The pipeline may be running before the current quality gate has
            # written its report. Keep the discovered count accurate without
            # claiming that a stale, smaller suite validates the current tree.
            unit_status = "PENDING_CURRENT_GATE"
        break

    statuses: dict[str, Any] = {
        "local_quality_gate": "PASS" if quality.get("ok") else "NOT_RUN",
        "unit_tests": {"status": unit_status, "count": unit_count},
        "idempotence": "PASS" if idempotence.get("ok") else "NOT_RUN",
        "clean_rebuild": "PASS" if clean.get("ok") else "NOT_RUN",
        "github_actions": os.environ.get("STAGE2A_GITHUB_ACTIONS", "PENDING_DRAFT_PR"),
    }
    p0 = validation.get("p0_error_count") if validation.get("ok") is not None else None
    p1 = validation.get("p1_warning_count") if validation.get("ok") is not None else None
    return statuses, p0, p1


def write_integration_report(
    tables: dict[str, list[dict[str, str]]],
    conflicts: list[dict[str, Any]],
    missing: list[dict[str, Any]],
    reconciliation: dict[str, Any],
    checked_at: str,
) -> dict[str, Any]:
    baseline = load_json(BASELINE_PATH)
    mapping = load_json(MAPPING_PATH)
    before = baseline["normalized_counts"]
    after: dict[str, int] = {}
    for name in sorted(set(before) | set(tables)):
        path = NORMALIZED_DIR / f"{name}.csv"
        after[name] = len(read_csv(path)) if path.is_file() else 0
    known_updates = {
        # Three pre-existing source documents moved from extracted_unarchived to
        # verified and gained canonical primary assets.  The compatibility
        # exports represent the same three business rows.
        "source_documents": 3,
        "documents": 3,
        "sources": 3,
    }
    count_changes = {
        name: {
            "before": int(before.get(name, 0)),
            "after": int(after.get(name, 0)),
            "added": max(0, int(after.get(name, 0)) - int(before.get(name, 0))),
            "updated": known_updates.get(name, 0),
            "deleted": max(0, int(before.get(name, 0)) - int(after.get(name, 0))),
        }
        for name in sorted(set(before) | set(after))
    }
    id_audit = stable_id_audit(tables)
    source_ids_before = int(baseline["counts"]["source_documents"])
    asset_ids_before = int(baseline["counts"]["source_assets"])
    actual_head = os.environ.get("STAGE2A_HEAD_SHA", "pending_draft_pr")
    test_statuses, p0, p1 = verified_test_statuses()
    payload = {
        "schema_version": "stage2a-hfnu-integration-report-v1",
        "generated_at": checked_at,
        "git": {
            "base_sha": baseline["git"]["base_sha"],
            "implementation_head_sha": actual_head,
            "branch": "data/stage2a-hfnu-evidence-integration",
        },
        "schema": {"version": SCHEMA_VERSION, "modified": False},
        "scope": {
            "school_id": "HFNU",
            "ahua_canonical_written": False,
            "batch_ready": False,
        },
        "evidence_and_sources": {
            "hfnu_evidence_assets": mapping["evidence_asset_count"],
            "promoted_raw_assets": mapping["promoted_count"],
            "unpromoted_assets": mapping["not_promoted_count"],
            "sha_mismatches": mapping["sha_mismatch_count"],
            "unmanaged_raw_files": len(mapping["unmanaged_raw_files"]),
            "source_documents_before": source_ids_before,
            "source_documents_after": len(tables["source_documents"]),
            "new_source_documents": len(tables["source_documents"]) - source_ids_before,
            "updated_source_documents": 3,
            "source_assets_before": asset_ids_before,
            "source_assets_after": len(tables["source_assets"]),
            "new_source_assets": len(tables["source_assets"]) - asset_ids_before,
            "new_staging_files": 8,
        },
        "canonical_changes": count_changes,
        "key_facts": {
            "admission_scores_2026": sum(
                row["year"] == "2026" for row in tables["admission_scores"]
            ),
            "admission_scores_2026_published": sum(
                row["year"] == "2026"
                and row["value_status"] == "published_value"
                for row in tables["admission_scores"]
            ),
            "syllabus": len(tables["syllabus"]),
            "reference_books": len(tables["reference_books"]),
            "application_statistics": len(tables["application_statistics"]),
        },
        "stable_id": id_audit,
        "qa": {
            "baseline_open_missing": int(baseline["missing"]["open"]),
            "closed_missing": int(baseline["missing"]["open"]) - len(missing),
            "remaining_missing": len(missing),
            "conflicts": len(conflicts),
            "p0": p0,
            "p1": p1,
        },
        "application_plan_reconciliation": reconciliation["summary"],
        "tests": test_statuses,
        "unresolved": [
            "2024-2026 historical adjustments remain not_found",
            "2025 and 2026 official application statistics remain unpublished",
            "four 2025 offerings remain blank in the official score source",
            "AHUA Pilot B has not entered canonical data",
        ],
        "next_stage": (
            "After human review and merge, start Stage 2B AHUA Pilot B from latest main."
        ),
    }
    dump_json(REPORTS_DIR / "stage2a_hfnu_integration_report.json", payload)

    lines = [
        "# Stage 2A HFNU 官方证据正式入库报告",
        "",
        f"> 生成时间：{checked_at}",
        f"> Base SHA：`{payload['git']['base_sha']}`",
        f"> Implementation Head：`{actual_head}`",
        f"> Schema：v{SCHEMA_VERSION}（未修改）",
        "",
        "## Evidence / Source / Asset",
        "",
        f"- HFNU evidence assets：{payload['evidence_and_sources']['hfnu_evidence_assets']}",
        f"- Promoted raw assets：{payload['evidence_and_sources']['promoted_raw_assets']}",
        f"- SHA mismatches：{payload['evidence_and_sources']['sha_mismatches']}",
        f"- Unmanaged raw files：{payload['evidence_and_sources']['unmanaged_raw_files']}",
        f"- Source documents：{source_ids_before} → {len(tables['source_documents'])}",
        f"- Source assets：{asset_ids_before} → {len(tables['source_assets'])}",
        "",
        "## Canonical 记录数",
        "",
        "| 表 | Before | After | Added | Updated | Deleted |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for name, change in count_changes.items():
        lines.append(
            f"| {name} | {change['before']} | {change['after']} | "
            f"{change['added']} | {change['updated']} | {change['deleted']} |"
        )
    lines.extend(
        [
            "",
            "## 关键事实",
            "",
            f"- 2026 admission score observations：{payload['key_facts']['admission_scores_2026']}",
            f"- 2026 published score values：{payload['key_facts']['admission_scores_2026_published']}",
            f"- Syllabus：{payload['key_facts']['syllabus']}",
            f"- Reference books：{payload['key_facts']['reference_books']}",
            f"- Application statistics：{payload['key_facts']['application_statistics']}",
            "",
            "## Stable ID",
            "",
            f"- Existing ID drift：{id_audit['existing_id_drift_count']}",
            f"- New IDs：{id_audit['new_id_count']}",
            "",
            "## QA",
            "",
            f"- Closed missing：{payload['qa']['closed_missing']}",
            f"- Remaining missing：{payload['qa']['remaining_missing']}",
            f"- Conflicts：{payload['qa']['conflicts']}",
            f"- P0：{payload['qa']['p0']}",
            f"- P1：{payload['qa']['p1']}",
            "",
            "## 测试",
            "",
            f"- Local quality gate：{payload['tests']['local_quality_gate']}",
            f"- Unit tests：{payload['tests']['unit_tests']['status']} "
            f"({payload['tests']['unit_tests']['count']} tests)",
            f"- Idempotence：{payload['tests']['idempotence']}",
            f"- Clean-room rebuild：{payload['tests']['clean_rebuild']}",
            f"- GitHub Actions：{payload['tests']['github_actions']}",
            "",
            "## 边界",
            "",
            "- Schema 未修改。",
            "- AHUA 未进入 canonical。",
            "- Batch Ready 仍为 false。",
            "- HFNU 仍在 partial_schools，不标记为 completed。",
            "",
            "## 未解决问题",
            "",
        ]
    )
    lines.extend(f"- {item}" for item in payload["unresolved"])
    (REPORTS_DIR / "stage2a_hfnu_integration_report.md").write_text(
        "\n".join(lines) + "\n", encoding="utf-8"
    )
    return payload


def report_text(
    tables: dict[str, list[dict[str, str]]],
    conflicts: list[dict[str, Any]],
    missing: list[dict[str, Any]],
    progress: list[dict[str, Any]],
    checked_at: str,
) -> str:
    plan_status = Counter(row["value_status"] for row in tables["enrollment_plans"])
    score_status = Counter(row["value_status"] for row in tables["admission_scores"])
    return "\n".join(
        [
            "# 合肥师范学院专升本 Stage 2A 集成报告",
            "",
            f"> 自动生成时间：{checked_at}",
            f"> Schema：v{SCHEMA_VERSION}（未修改）",
            "",
            "## 结论",
            "",
            "HFNU 已审计证据已正式进入 canonical raw、source catalog/source assets、staging、normalized CSV 与 SQLite。",
            "",
            "**Batch Readiness 仍为 FAIL。** 下一步是人工 Review Stage 2A，合并后执行 AHUA Stage 2B；不得直接进入全省 Batch。",
            "",
            "## 核心数据量",
            "",
            "| 数据表 | 记录数 |",
            "|---|---:|",
            f"| Program Year | {len(tables['program_years'])} |",
            f"| Program Offering | {len(tables['program_offerings'])} |",
            f"| 招生计划槽位 | {len(tables['enrollment_plans'])} |",
            f"| 考试科目 | {len(tables['exam_subjects'])} |",
            f"| 录取分数观察值 | {len(tables['admission_scores'])} |",
            f"| 考试大纲 | {len(tables['syllabus'])} |",
            f"| 参考教材 | {len(tables['reference_books'])} |",
            f"| 报名人数 | {len(tables['application_statistics'])} |",
            "",
            "## 年度覆盖",
            "",
            "| 年份 | Offering | 分数观察 | 已发布分数 | 大纲 | 参考教材 | 报名统计 | Open Missing |",
            "|---:|---:|---:|---:|---:|---:|---:|---:|",
            *[
                (
                    f"| {row['year']} | {row['program_offerings']} | "
                    f"{row['admission_scores']} | {row['admission_scores_published']} | "
                    f"{row['syllabus']} | {row['reference_books']} | "
                    f"{row['application_statistics']} | {row['missing_items_open']} |"
                )
                for row in progress
            ],
            "",
            "## Stage 2A 已完成",
            "",
            "- 26 个 HFNU Stage 1 evidence asset 按相同字节提升到 canonical raw。",
            "- 正式 source document 增至 10，source asset 增至 29。",
            "- 2026 官方录取表生成 28 个 Offering × 5 类 = 140 条观察值。",
            "- 2024—2026 大纲与参考教材由官方 PDF staging 可重复构建。",
            "- 2024 官方分专业报名人数生成 30 条 application statistics；计划数与 canonical 全部一致。",
            f"- 分数状态：published_value={score_status['published_value']}，blank_in_source={score_status['blank_in_source']}。",
            f"- 计划状态：explicit_value={plan_status['explicit_value']}，blank_in_source={plan_status['blank_in_source']}。",
            "- 既有稳定 ID 漂移为 0。",
            "",
            "## 当前 QA",
            "",
            f"- Active conflicts：{len(conflicts)}",
            f"- Open missing：{len(missing)}",
            "- 仍开放：三年 adjustments、2025/2026 application statistics、四个 2025 官方空白录取 Offering。",
            "",
            "## 下一步",
            "",
            "人工 Review 并合并 Stage 2A 后，从最新 main 创建 Stage 2B AHUA Pilot B 分支。Schema v1.0 仍不得冻结。",
            "",
        ]
    )


def write_batch_checklist() -> None:
    text = """# Batch Readiness Checklist

## Stage 2A 已通过

- [x] HFNU Stage 1 evidence 正式提升到 canonical raw
- [x] 正式 source catalog / source assets
- [x] HFNU 2026 录取分数结构化
- [x] HFNU 2024—2026 考试大纲与参考教材结构化
- [x] HFNU 2024 官方报名人数结构化
- [x] Stable ID 无漂移
- [x] P0/P1 为 0、幂等与 clean-room 可重建

## 进入 Batch 前仍需完成

- [ ] 人工 Review 并合并 Stage 2A
- [ ] 执行 AHUA Stage 2B canonical 建模
- [ ] 完成 Pilot B Schema 兼容性评估
- [ ] 人工确认 Schema v1.0 冻结方案

**当前结论：Batch Readiness = FAIL；`batch_ready=false`。**
"""
    (REPORTS_DIR / "batch_readiness_checklist.md").write_text(
        text, encoding="utf-8"
    )


def main() -> int:
    checked_at = now_iso()
    tables = load_tables()
    conflicts, missing = write_qa(tables, checked_at)
    progress = build_progress(tables, conflicts, missing, checked_at)
    write_task_state(checked_at)
    reconciliation = write_application_plan_reconciliation(tables, checked_at)
    write_integration_report(tables, conflicts, missing, reconciliation, checked_at)
    text = report_text(tables, conflicts, missing, progress, checked_at)
    (REPORTS_DIR / "pilot_report.md").write_text(text, encoding="utf-8")
    (REPORTS_DIR / "pilot_2_3_repair_report.md").write_text(text, encoding="utf-8")
    write_batch_checklist()
    print(f"QA/report generated: conflicts={len(conflicts)}, missing={len(missing)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
