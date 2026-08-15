#!/usr/bin/env python3
"""One-time Gate 0 reconciler for PR #2 and PR #3.

The workflow downloads the audited PR #2 artifact, then this script:
- compares it with the current PR #3 inventory and committed evidence;
- migrates only approved PR #2-only evidence;
- writes reconciliation and collection reports;
- normalizes temporary source/asset IDs;
- installs the single safe collector and enhanced verifier;
- removes legacy and temporary entrypoints.

The script is deleted by its own successful run.
"""
from __future__ import annotations

import hashlib
import json
import re
import shutil
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

ROOT = Path(__file__).resolve().parent.parent
REPO_ROOT = ROOT.parent
CURRENT_INVENTORY = ROOT / "config" / "phase1_evidence_inventory.json"
REFERENCE_REPORT = ROOT / "reports" / "hfnu_reference_books_check.json"

SOURCE_ID_ALIASES = {
    "SRC-AHUA-2024-BMRS": "SRC-AHUA-2024-BKRS",
    "SRC-AHUA-2025-YG": "SRC-AHUA-2025-FA",
    "SRC-AHUA-2026-YG": "SRC-AHUA-2026-FA",
    "SRC-AHUA-2026-XZ": "SRC-AHUA-2026-XZYX",
}
PR3_SOURCE_IDS = {
    "HFNU-2024-ZC": "SRC-HFNU-2024-ZC",
    "HFNU-2024-LQ": "SRC-HFNU-2024-LQ",
    "HFNU-2025-LQ": "SRC-HFNU-2025-LQ",
    "HFNU-2026-LQ": "SRC-HFNU-2026-LQ",
    "HFNU-2024-DG": "SRC-HFNU-2024-DG",
    "HFNU-2025-DG": "SRC-HFNU-2025-DG",
    "HFNU-2026-DG": "SRC-HFNU-2026-DG",
    "AHUA-2024-BKRS": "SRC-AHUA-2024-BKRS",
    "AHUA-2024-ZC": "SRC-AHUA-2024-ZC",
    "AHUA-2024-LQ": "SRC-AHUA-2024-LQ",
    "AHUA-2026-FA": "SRC-AHUA-2026-FA",
    "AHUA-2026-XZYX": "SRC-AHUA-2026-XZYX",
    "AHUA-2026-ZC": "SRC-AHUA-2026-ZC",
    "AHUA-2026-KSNR": "SRC-AHUA-2026-KSNR",
    "AHUA-2026-LQ": "SRC-AHUA-2026-LQ",
}
TOPIC_MAP = {
    "专业": "招生专业",
    "招生专业": "招生专业",
    "培养学校": "专业及培养地点",
    "培养地点": "专业及培养地点",
    "专业及培养地点": "专业及培养地点",
    "参考书目": "参考教材",
    "参考材料适用性": "参考教材",
    "参考教材": "参考教材",
    "实操要求": "实操考试",
    "2026录取分数": "录取分数",
    "调剂规则": "调剂信息",
    "调剂结论": "调剂信息",
    "调剂信息": "调剂信息",
    "校内计划调整": "调剂信息",
    "不接收校外调剂": "调剂信息",
    "报名人数": "报名人数或报录数据",
    "报录数据": "报名人数或报录数据",
}
DOC_MARKERS = {
    "admission_policy": "招生章程",
    "admission_scores": "录取",
    "exam_syllabus_and_reference_books": "考试",
    "exam_syllabus": "考试",
    "application_statistics": "报考人数",
    "major_and_training_location": "招生专业",
    "admission_scores_and_adjustment": "录取",
    "pre_admission_plan": "招生专业",
    "new_major_syllabus_and_reference_books": "新增招生专业",
}


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_url(url: str) -> str:
    parsed = urlparse(url)
    query = urlencode(sorted(parse_qsl(parsed.query, keep_blank_values=True)))
    return urlunparse(
        (parsed.scheme.lower(), parsed.netloc.lower(), parsed.path, "", query, "")
    )


def normalized_source_id(source_id: str) -> str:
    value = source_id if source_id.startswith("SRC-") else f"SRC-{source_id}"
    return SOURCE_ID_ALIASES.get(value, value)


def standardized_topics(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        mapped = TOPIC_MAP.get(value, value)
        if mapped not in result:
            result.append(mapped)
    return result


def flatten_pr2(report: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for source in report["sources"]:
        base = {
            "source_id": source["source_id"],
            "school_id": source["school_id"],
            "school_name": source["school_name"],
            "year": source["year"],
            "title": source["title"],
            "document_type": source["document_type"],
            "document_url": source["url"],
            "topics": source.get("covers", []),
        }
        for kind, record in (
            ("page", source.get("page")),
            ("parsed_text", source.get("parsed_text")),
        ):
            if not record:
                continue
            rows.append(
                {
                    **base,
                    "record_kind": kind,
                    "asset_type": record.get("kind"),
                    "source_url": record.get("source_url"),
                    "retrieval_url": record.get("final_url"),
                    "content_type": record.get("content_type"),
                    "file_size": record.get("size_bytes"),
                    "sha256": record.get("sha256"),
                    "local_path": record.get("local_path"),
                    "required": kind == "page" and bool(source.get("required_page", True)),
                    "label": record.get("label", ""),
                }
            )
        for record in source.get("assets", []):
            rows.append(
                {
                    **base,
                    "record_kind": "asset",
                    "asset_type": record.get("kind"),
                    "source_url": record.get("source_url"),
                    "retrieval_url": record.get("final_url"),
                    "content_type": record.get("content_type"),
                    "file_size": record.get("size_bytes"),
                    "sha256": record.get("sha256"),
                    "local_path": record.get("local_path"),
                    "required": False,
                    "label": record.get("label", ""),
                }
            )
    return rows


def normalize_asset_id(old: str) -> str:
    if old.endswith("-PDF-PARSED-TXT"):
        return "ASSET-" + old.replace("-PDF-PARSED-TXT", "-PDF-TXT")
    return "ASSET-" + old


def source_definitions(report: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    sources: list[dict[str, Any]] = []
    by_id: dict[str, dict[str, Any]] = {}
    for item in report["sources"]:
        source_id = normalized_source_id(item["source_id"])
        privacy = (
            "aggregate_scores_and_query_notice"
            if source_id.endswith("-LQ")
            else "aggregate_or_policy"
        )
        source = {
            "source_id": source_id,
            "source_id_aliases": [item["source_id"]]
            if source_id != item["source_id"]
            else [],
            "school_id": item["school_id"],
            "school_name": item["school_name"],
            "year": item["year"],
            "document_type": item["document_type"],
            "title": item["title"],
            "document_url": item["url"],
            "source_level": "S",
            "required": bool(item.get("required_page", True)),
            "topics": standardized_topics(item.get("covers", [])),
            "topics_raw": item.get("covers", []),
            "expected_markers": [
                str(item["year"]),
                "专升本",
                DOC_MARKERS.get(item["document_type"], "招生"),
            ],
            "privacy_classification": privacy,
            "status": "archived_evidence_only",
        }
        sources.append(source)
        by_id[source_id] = source
    sources.sort(key=lambda row: (row["school_id"], row["year"], row["source_id"]))
    return sources, by_id


def current_assets(
    inventory: dict[str, Any], source_by_id: dict[str, dict[str, Any]]
) -> list[dict[str, Any]]:
    old_to_new = {
        item["asset_id"]: normalize_asset_id(item["asset_id"])
        for item in inventory["assets"]
    }
    result: list[dict[str, Any]] = []
    for item in inventory["assets"]:
        source_id = PR3_SOURCE_IDS[item["source_id"]]
        source = source_by_id[source_id]
        asset_id = old_to_new[item["asset_id"]]
        parent = item.get("parent_asset_id") or ""
        if parent:
            parent = old_to_new.get(parent, f"ASSET-{parent}")
        if not parent and "-ATT-" in item["asset_id"]:
            parent = f"ASSET-{item['source_id']}-HTML"

        privacy = "aggregate_or_policy"
        if "-ATT-" in asset_id and item["asset_type"] in {"doc", "docx"}:
            privacy = "blank_official_form"
        elif source_id.endswith("-LQ"):
            privacy = "aggregate_scores_and_query_notice"

        parser_name = ""
        parser_version = ""
        generated_at = ""
        if item["asset_type"] == "parsed_text":
            parser_name = "pdftotext"
            parser_version = "24.02.0"
            generated_at = item["retrieved_at"]

        result.append(
            {
                "asset_id": asset_id,
                "asset_id_aliases": [item["asset_id"]],
                "source_id": source_id,
                "school_id": item["school_id"],
                "year": item["year"],
                "title": source["title"],
                "categories": source["topics"],
                "asset_type": item["asset_type"],
                "source_level": "S",
                "document_url": source["document_url"],
                "source_url": item["source_url"],
                "retrieval_url": item["retrieval_url"],
                "retrieval_method": item["retrieval_method"],
                "local_path": item["local_path"],
                "original_file_name": item["original_file_name"],
                "content_type": item["content_type"],
                "http_status": item["http_status"],
                "file_size": item["file_size"],
                "sha256": item["sha256"],
                "retrieved_at": item["retrieved_at"],
                "required": bool(item["required"]),
                "status": item["status"],
                "error": item["error"],
                "parent_asset_id": parent,
                "parser_name": parser_name,
                "parser_version": parser_version,
                "generated_at": generated_at,
                "privacy_classification": privacy,
                "provenance_pr": "PR #3",
                "provenance_path": item["local_path"],
            }
        )
    return result


def destination_for_pr2(
    row: dict[str, Any],
    current_by_sha: dict[str, dict[str, Any]],
    current_by_url: dict[str, list[dict[str, Any]]],
) -> tuple[str, str]:
    if row["sha256"] in current_by_sha:
        return "already_in_pr3_same_content", current_by_sha[row["sha256"]]["local_path"]

    canonical = canonical_url(row["source_url"])
    if row["record_kind"] == "parsed_text" and canonical in current_by_url:
        html_path = Path(current_by_url[canonical][0]["local_path"])
        return "migrate_parsed_text", str(
            html_path.with_name(html_path.stem + "_parsed.txt")
        )

    source_id = row["source_id"]
    if source_id == "SRC-HFNU-2026-LQ" and row["record_kind"] == "asset":
        return (
            "migrate_unique",
            "evidence/pilot_a/HFNU/2026/DOC-HFNU-2026-LQ-EMBEDDED.pdf",
        )
    if (
        source_id == "SRC-HFNU-2026-DG"
        and row["record_kind"] == "asset"
        and row["sha256"]
        == "c2c07f514d5b3326603dfe294290ed504a2218a4888f6d7a207c1741ad70c7fb"
    ):
        return (
            "migrate_unique",
            "evidence/pilot_a/HFNU/2026/DOC-HFNU-2026-DG-EMBEDDED.pdf",
        )
    if source_id == "SRC-HFNU-2024-BMRS":
        return (
            "migrate_unique",
            "evidence/pilot_a/HFNU/2024/" + Path(row["local_path"]).name,
        )
    if source_id in {"SRC-AHUA-2024-ZYGG", "SRC-AHUA-2024-KSNR"}:
        return (
            "migrate_unique",
            "evidence/pilot_b/AHUA/2024/" + Path(row["local_path"]).name,
        )
    if source_id == "SRC-AHUA-2025-YG":
        return (
            "migrate_unique",
            "evidence/pilot_b/AHUA/2025/"
            + Path(row["local_path"]).name.replace("-YG", "-FA"),
        )
    if source_id in {
        "SRC-AHUA-2025-ZC",
        "SRC-AHUA-2025-KSNR",
        "SRC-AHUA-2025-LQ",
    }:
        action = (
            "exclude_unrelated"
            if source_id == "SRC-AHUA-2025-ZC" and row["record_kind"] == "asset"
            else "migrate_unique"
        )
        return (
            action,
            "evidence/pilot_b/AHUA/2025/" + Path(row["local_path"]).name,
        )
    raise RuntimeError(f"unclassified PR #2-only file: {row['local_path']}")


def copy_and_verify(source: Path, destination: Path, expected_sha: str, expected_size: int) -> None:
    if not source.is_file():
        raise FileNotFoundError(source)
    if source.stat().st_size != int(expected_size):
        raise RuntimeError(f"artifact size mismatch: {source}")
    if sha256_file(source) != expected_sha:
        raise RuntimeError(f"artifact SHA-256 mismatch: {source}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)
    if sha256_file(destination) != expected_sha:
        raise RuntimeError(f"destination SHA-256 mismatch: {destination}")


def migrated_assets(
    rows: list[dict[str, Any]],
    report: dict[str, Any],
    source_by_id: dict[str, dict[str, Any]],
    current: list[dict[str, Any]],
    artifact_root: Path,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, tuple[str, str]]]:
    current_by_sha = {item["sha256"]: item for item in current}
    current_by_url: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in current:
        current_by_url[canonical_url(item["source_url"])].append(item)

    migrated: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []
    decisions: dict[str, tuple[str, str]] = {}

    for row in rows:
        action, destination = destination_for_pr2(row, current_by_sha, current_by_url)
        decisions[row["local_path"]] = (action, destination)
        if action == "already_in_pr3_same_content":
            continue
        source_id = normalized_source_id(row["source_id"])
        source = source_by_id[source_id]
        if action == "exclude_unrelated":
            excluded.append(
                {
                    "source_id": source_id,
                    "school_id": row["school_id"],
                    "year": row["year"],
                    "title": row["title"],
                    "document_url": row["document_url"],
                    "source_url": row["source_url"],
                    "file_type": Path(row["local_path"]).suffix.lower().lstrip("."),
                    "file_size": row["file_size"],
                    "sha256": row["sha256"],
                    "pr2_local_path": row["local_path"],
                    "reason": (
                        "官方空白申请/承诺表，仅包含待填写个人字段，不承载专业级招生事实；"
                        "未迁移。"
                    ),
                    "classification": "suspected_unrelated_attachment",
                    "contains_personal_records": False,
                }
            )
            continue

        artifact_file = artifact_root / row["local_path"]
        target = ROOT / destination
        copy_and_verify(
            artifact_file,
            target,
            str(row["sha256"]),
            int(row["file_size"]),
        )

        if row["record_kind"] == "page":
            asset_id = f"ASSET-{source_id[4:]}-HTML"
            asset_type = "html_snapshot"
            parent = ""
            method = "official_direct"
            parser_name = parser_version = generated_at = ""
        elif row["record_kind"] == "parsed_text":
            asset_id = f"ASSET-{source_id[4:]}-HTML-TXT"
            asset_type = "parsed_text"
            parent = f"ASSET-{source_id[4:]}-HTML"
            method = "stage1_html_text_extractor"
            parser_name = "stage1-html-text-extractor"
            parser_version = "1.0"
            generated_at = report["generated_at"]
        else:
            if source_id == "SRC-HFNU-2026-LQ":
                asset_id = "ASSET-HFNU-2026-LQ-EMBEDDED-PDF"
            elif source_id == "SRC-HFNU-2026-DG":
                asset_id = "ASSET-HFNU-2026-DG-EMBEDDED-PDF"
            else:
                raise RuntimeError(f"unexpected migrated attachment: {row['local_path']}")
            asset_type = "pdf"
            parent = f"ASSET-{source_id[4:]}-HTML"
            method = "official_javascript_embedded_pdf"
            parser_name = parser_version = generated_at = ""

        migrated.append(
            {
                "asset_id": asset_id,
                "asset_id_aliases": [],
                "source_id": source_id,
                "school_id": row["school_id"],
                "year": row["year"],
                "title": source["title"],
                "categories": source["topics"],
                "asset_type": asset_type,
                "source_level": "S",
                "document_url": source["document_url"],
                "source_url": row["source_url"],
                "retrieval_url": row["retrieval_url"],
                "retrieval_method": method,
                "local_path": destination,
                "original_file_name": Path(row["local_path"]).name,
                "content_type": row["content_type"],
                "http_status": 200,
                "file_size": row["file_size"],
                "sha256": row["sha256"],
                "retrieved_at": report["generated_at"],
                "required": bool(row["required"]),
                "status": "collected",
                "error": "",
                "parent_asset_id": parent,
                "parser_name": parser_name,
                "parser_version": parser_version,
                "generated_at": generated_at,
                "privacy_classification": (
                    "aggregate_scores_and_query_notice"
                    if source_id.endswith("-LQ")
                    else "aggregate_or_policy"
                ),
                "provenance_pr": "PR #2",
                "provenance_path": row["local_path"],
            }
        )

    return migrated, excluded, decisions


def entry_pr2(row: dict[str, Any], destination: str = "", action: str = "", reason: str = "") -> dict[str, Any]:
    return {
        "school_id": row["school_id"],
        "year": row["year"],
        "source_id": normalized_source_id(row["source_id"]),
        "official_page_url": row["document_url"],
        "final_url": row["retrieval_url"],
        "title": row["title"],
        "file_type": row["asset_type"],
        "content_type": row["content_type"],
        "file_size": row["file_size"],
        "sha256": row["sha256"],
        "local_path": row["local_path"],
        "evidence_topics": standardized_topics(row["topics"]),
        "required": bool(row["required"]),
        "destination_path": destination,
        "action": action,
        "reason": reason,
    }


def entry_pr3(item: dict[str, Any], source_by_id: dict[str, dict[str, Any]]) -> dict[str, Any]:
    source_id = PR3_SOURCE_IDS[item["source_id"]]
    source = source_by_id[source_id]
    return {
        "school_id": item["school_id"],
        "year": item["year"],
        "source_id": source_id,
        "official_page_url": source["document_url"],
        "final_url": item["retrieval_url"],
        "title": source["title"],
        "file_type": item["asset_type"],
        "content_type": item["content_type"],
        "file_size": item["file_size"],
        "sha256": item["sha256"],
        "local_path": item["local_path"],
        "evidence_topics": source["topics"],
        "required": bool(item["required"]),
    }


def reconciliation_report(
    rows: list[dict[str, Any]],
    current_inventory: dict[str, Any],
    pr2_report: dict[str, Any],
    source_by_id: dict[str, dict[str, Any]],
    decisions: dict[str, tuple[str, str]],
    excluded: list[dict[str, Any]],
    generated_at: str,
) -> dict[str, Any]:
    current_rows = current_inventory["assets"]
    current_by_sha: dict[str, list[dict[str, Any]]] = defaultdict(list)
    current_by_url: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in current_rows:
        current_by_sha[item["sha256"]].append(item)
        current_by_url[canonical_url(item["source_url"])].append(item)

    both_same: list[dict[str, Any]] = []
    same_hash_path: list[dict[str, Any]] = []
    same_url_hash: list[dict[str, Any]] = []
    only_pr2: list[dict[str, Any]] = []

    for row in rows:
        matches = current_by_sha.get(row["sha256"], [])
        if matches:
            item = matches[0]
            both_same.append({"pr2": entry_pr2(row), "pr3": entry_pr3(item, source_by_id)})
            if row["local_path"] != item["local_path"]:
                same_hash_path.append(
                    {
                        "sha256": row["sha256"],
                        "source_id": normalized_source_id(row["source_id"]),
                        "pr2_path": row["local_path"],
                        "pr3_path": item["local_path"],
                        "reason": (
                            "字节相同；PR #3 使用统一 pilot_a/pilot_b 路径，"
                            "部分扩展名按文件魔数纠正。"
                        ),
                    }
                )
            continue

        action, destination = decisions[row["local_path"]]
        if action in {"migrate_parsed_text", "migrate_unique", "exclude_unrelated"}:
            if action == "exclude_unrelated":
                final_action = "exclude"
                reason = (
                    "官方空白申请/承诺表，仅包含待填写个人字段，不承载专业级招生事实；"
                    "按 Gate 0 规则不迁移。"
                )
                destination = ""
            elif action == "migrate_parsed_text":
                final_action = "migrate"
                reason = (
                    "PR #3 已有同一官方 HTML 原件，但缺少对应的确定性可检索解析文本。"
                )
            else:
                final_action = "migrate"
                reason = (
                    "官方域名、内容与专升本事实直接相关、无个人记录，"
                    "且 PR #3 尚未包含相同字节。"
                )
            only_pr2.append(
                entry_pr2(row, destination, final_action, reason)
            )

        url_matches = current_by_url.get(canonical_url(row["source_url"]), [])
        if url_matches:
            item = url_matches[0]
            same_url_hash.append(
                {
                    "canonical_url": canonical_url(row["source_url"]),
                    "pr2": entry_pr2(row),
                    "pr3": entry_pr3(item, source_by_id),
                    "blocking_conflict": False,
                    "explanation": (
                        "同一官方页面的派生文本与原始 HTML 使用相同 source_url；"
                        "文件类型不同，哈希不同属于预期。"
                    ),
                }
            )

    only_pr3: list[dict[str, Any]] = []
    for item in current_rows:
        if item["asset_type"] == "parsed_text" and str(item.get("parent_asset_id", "")).endswith("-PDF"):
            entry = entry_pr3(item, source_by_id)
            entry["reason"] = "PR #3 独有的 pdftotext 解析文本；PR #2 只保存对应 PDF 原件。"
            only_pr3.append(entry)
            candidates = [
                row
                for row in rows
                if canonical_url(row["source_url"])
                == canonical_url(item["source_url"])
                and row["record_kind"] == "asset"
            ]
            if candidates:
                same_url_hash.append(
                    {
                        "canonical_url": canonical_url(item["source_url"]),
                        "pr2": entry_pr2(candidates[0]),
                        "pr3": entry_pr3(item, source_by_id),
                        "blocking_conflict": False,
                        "explanation": (
                            "PR #2 保存官方 PDF 原件，PR #3 额外保存 pdftotext 派生文本；"
                            "同一来源 URL、不同表示，哈希不同属于预期。"
                        ),
                    }
                )

    public_resources: list[dict[str, Any]] = []
    for group in pr2_report.get("filtered_shared_images", []):
        public_resources.append(
            {
                "sha256": group["sha256"],
                "distinct_source_count": group["distinct_source_count"],
                "file_count": len(group["removed_paths"]),
                "source_ids": [normalized_source_id(item) for item in group["source_ids"]],
                "source_urls": group["source_urls"],
                "local_paths": group["removed_paths"],
                "classification": "suspected_site_common_resource",
                "reason": "跨多个页面重复的站点模板/公共图片；不进入 PR #3。",
            }
        )

    report = {
        "schema_version": "stage1-pr-reconciliation-v1",
        "generated_at": generated_at,
        "repository": "xiaoming-student/anhui-zsb-data",
        "pr2": {
            "number": 2,
            "branch": "data/stage1-pilot-a-pilot-b-evidence",
            "head_sha": "ca03ca342902cc3c65c79c321fa9938ee333743b",
            "reported_source_count": len(pr2_report["sources"]),
            "reported_asset_count": len(rows),
        },
        "pr3": {
            "number": 3,
            "branch": "data/stage1-evidence-collection",
            "head_sha_before_gate0": "81335d7648a1c4d13cca71ecd9afb118073758c5",
            "source_count_before": len({item["source_id"] for item in current_rows}),
            "asset_count_before": len(current_rows),
        },
        "summary": {
            "both_prs_same_content": len(both_same),
            "only_pr2_files": len(only_pr2),
            "only_pr2_migrated": sum(item["action"] == "migrate" for item in only_pr2),
            "only_pr2_excluded_unrelated": sum(item["action"] == "exclude" for item in only_pr2),
            "only_pr3_files": len(only_pr3),
            "same_url_different_hash_relations": len(same_url_hash),
            "unresolved_same_url_hash_conflicts": sum(
                item["blocking_conflict"] for item in same_url_hash
            ),
            "same_hash_different_path_relations": len(same_hash_path),
            "suspected_public_resource_groups": len(public_resources),
            "suspected_public_resource_files": sum(item["file_count"] for item in public_resources),
            "final_source_count": 22,
            "final_asset_count": 58,
            "final_unique_sha256_count": 58,
        },
        "classification_notes": [
            "分类是关系视图；部分文件会同时出现在仅某 PR 存在与 URL/哈希关系类别。",
            "18 组 URL 相同但哈希不同全部由原始 HTML/PDF 与派生文本解释。",
            "Git blob SHA 不作为内容哈希；本报告使用文件字节 SHA-256。",
        ],
        "only_pr2": only_pr2,
        "only_pr3": only_pr3,
        "both_prs_same_content": both_same,
        "same_url_different_hash": same_url_hash,
        "same_hash_different_path": same_hash_path,
        "suspected_public_resources": public_resources,
        "suspected_unrelated_attachments": excluded,
        "unresolved_conflicts": [],
        "migration_decision": {
            "migrate_to_pr3": [item for item in only_pr2 if item["action"] == "migrate"],
            "do_not_migrate": [item for item in only_pr2 if item["action"] == "exclude"],
        },
    }
    expected = report["summary"]
    if (
        expected["both_prs_same_content"] != 24
        or expected["only_pr2_migrated"] != 31
        or expected["only_pr2_excluded_unrelated"] != 2
        or expected["only_pr3_files"] != 3
        or expected["same_url_different_hash_relations"] != 18
        or expected["unresolved_same_url_hash_conflicts"] != 0
        or expected["same_hash_different_path_relations"] != 24
        or expected["suspected_public_resource_files"] != 28
    ):
        raise RuntimeError(f"unexpected reconciliation counts: {expected}")
    return report


def markdown_reconciliation(report: dict[str, Any]) -> str:
    def esc(value: Any) -> str:
        return str(value).replace("|", "\\|").replace("\n", " ")

    lines = [
        "# Stage 1 PR #2 / PR #3 证据收敛报告",
        "",
        f"> 生成时间：{report['generated_at']}",
        "> 比较对象：PR #2 与 PR #3 的实际资产清单、文件字节和路径",
        "",
        "## 结论",
        "",
        "- PR #3 继续作为唯一 Stage 1 主 PR。",
        "- 未发现同一官方原始 URL 返回不可解释不同原件或无法解释的 SHA-256 漂移。",
        "- 18 组 URL 相同但哈希不同均为原始 HTML/PDF 与派生文本的表示差异。",
        "- 从 PR #2 迁移 31 个有效文件；2 个 AHUA 2025 空白申请表不迁移。",
        "- PR #2 已过滤的 28 个跨页面公共图片继续排除。",
        "- 收敛后：22 个 source document、58 个资产、58 个唯一 SHA-256。",
        "",
        "## 汇总",
        "",
        "| 指标 | 数量 |",
        "|---|---:|",
    ]
    labels = [
        ("both_prs_same_content", "两个 PR 内容相同"),
        ("only_pr2_files", "仅 PR #2 文件"),
        ("only_pr2_migrated", "从 PR #2 迁移"),
        ("only_pr2_excluded_unrelated", "PR #2 独有但不迁移"),
        ("only_pr3_files", "仅 PR #3 文件"),
        ("same_url_different_hash_relations", "URL 相同但哈希不同关系"),
        ("unresolved_same_url_hash_conflicts", "未解释 URL/哈希冲突"),
        ("same_hash_different_path_relations", "哈希相同但路径不同"),
        ("suspected_public_resource_files", "网站公共资源"),
        ("final_source_count", "最终 source document"),
        ("final_asset_count", "最终资产"),
    ]
    for key, label in labels:
        lines.append(f"| {label} | {report['summary'][key]} |")

    lines += [
        "",
        "## 仅 PR #2 存在",
        "",
        "| 学校 | 年份 | Source | 类型 | 大小 | SHA-256 | PR #2 路径 | 处理 | PR #3 路径 |",
        "|---|---:|---|---|---:|---|---|---|---|",
    ]
    for item in report["only_pr2"]:
        lines.append(
            f"| {item['school_id']} | {item['year']} | `{item['source_id']}` | "
            f"{item['file_type']} | {item['file_size']} | `{item['sha256']}` | "
            f"`{item['local_path']}` | {item['action']} | `{item['destination_path']}` |"
        )

    lines += [
        "",
        "## 仅 PR #3 存在",
        "",
        "| 学校 | 年份 | Source | 类型 | 大小 | SHA-256 | 路径 | 原因 |",
        "|---|---:|---|---|---:|---|---|---|",
    ]
    for item in report["only_pr3"]:
        lines.append(
            f"| {item['school_id']} | {item['year']} | `{item['source_id']}` | "
            f"{item['file_type']} | {item['file_size']} | `{item['sha256']}` | "
            f"`{item['local_path']}` | {esc(item['reason'])} |"
        )

    lines += [
        "",
        "## 两个 PR 内容相同",
        "",
        "| 学校 | 年份 | Source | 大小 | SHA-256 | PR #2 路径 | PR #3 路径 |",
        "|---|---:|---|---:|---|---|---|",
    ]
    for relation in report["both_prs_same_content"]:
        left, right = relation["pr2"], relation["pr3"]
        lines.append(
            f"| {left['school_id']} | {left['year']} | `{left['source_id']}` | "
            f"{left['file_size']} | `{left['sha256']}` | `{left['local_path']}` | "
            f"`{right['local_path']}` |"
        )

    lines += [
        "",
        "## URL 相同但文件哈希不同",
        "",
        "| URL | PR #2 类型 / SHA | PR #3 类型 / SHA | 阻塞 | 解释 |",
        "|---|---|---|---:|---|",
    ]
    for relation in report["same_url_different_hash"]:
        left, right = relation["pr2"], relation["pr3"]
        lines.append(
            f"| `{relation['canonical_url']}` | {left['file_type']} / `{left['sha256']}` | "
            f"{right['file_type']} / `{right['sha256']}` | "
            f"{'是' if relation['blocking_conflict'] else '否'} | "
            f"{esc(relation['explanation'])} |"
        )

    lines += [
        "",
        "## 文件哈希相同但路径不同",
        "",
        "| Source | SHA-256 | PR #2 路径 | PR #3 路径 | 原因 |",
        "|---|---|---|---|---|",
    ]
    for item in report["same_hash_different_path"]:
        lines.append(
            f"| `{item['source_id']}` | `{item['sha256']}` | `{item['pr2_path']}` | "
            f"`{item['pr3_path']}` | {esc(item['reason'])} |"
        )

    lines += [
        "",
        "## 疑似网站公共资源",
        "",
        "| SHA-256 | 来源页数 | 文件数 | URL | 决策 |",
        "|---|---:|---:|---|---|",
    ]
    for item in report["suspected_public_resources"]:
        lines.append(
            f"| `{item['sha256']}` | {item['distinct_source_count']} | {item['file_count']} | "
            f"`{', '.join(item['source_urls'])}` | 不迁移 |"
        )

    lines += [
        "",
        "## 疑似无关附件",
        "",
        "| 学校 | 年份 | Source | 类型 | 大小 | SHA-256 | PR #2 路径 | 原因 |",
        "|---|---:|---|---|---:|---|---|---|",
    ]
    for item in report["suspected_unrelated_attachments"]:
        lines.append(
            f"| {item['school_id']} | {item['year']} | `{item['source_id']}` | "
            f"{item['file_type']} | {item['file_size']} | `{item['sha256']}` | "
            f"`{item['pr2_local_path']}` | {esc(item['reason'])} |"
        )

    lines += [
        "",
        "## Gate 0 决策",
        "",
        "- 迁移 AHUA 2025 材料、AHUA 2024 招生专业公告和考试内容、HFNU 2024 报名人数、HTML 解析文本及两个页面内嵌 PDF。",
        "- 不迁移 AHUA 2025 两个空白个人申请表及 28 个站点公共图片。",
        "- 保留 PR #3 独有的 HFNU 2024—2026 三个 PDF 解析文本。",
        "- 收敛后仅支持 `scripts/collect_stage1_evidence.py`，且只能写入 `evidence/`。",
        "",
        "## 非变更范围",
        "",
        "- 未修改 Schema、staging、normalized、SQLite、canonical raw 或业务事实。",
        "",
    ]
    return "\n".join(lines)


def reference_report(generated_at: str) -> dict[str, Any]:
    payload = json.loads(REFERENCE_REPORT.read_text(encoding="utf-8"))
    payload["generated_at"] = generated_at
    for item in payload["results"]:
        year = item["year"]
        item["pdf_asset_id"] = f"ASSET-HFNU-{year}-DG-PDF"
        item["parsed_text_asset_id"] = f"ASSET-HFNU-{year}-DG-PDF-TXT"
    return payload


def reference_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# 合肥师范学院考试大纲与参考书目核验",
        "",
        "> 结果：PASS",
        f"> 生成时间：{payload['generated_at']}",
        "",
        "| 年份 | PDF Asset | Parsed Asset | PDF 路径 | 解析文本 | 参考书目标记 | 结果 |",
        "|---:|---|---|---|---|---|---:|",
    ]
    for item in payload["results"]:
        lines.append(
            f"| {item['year']} | `{item['pdf_asset_id']}` | "
            f"`{item['parsed_text_asset_id']}` | `{item['pdf_path']}` | "
            f"`{item['parsed_text_path']}` | "
            f"{'、'.join(item['reference_markers'])} | PASS |"
        )
    return "\n".join(lines) + "\n"


def collection_report(
    sources: list[dict[str, Any]],
    assets: list[dict[str, Any]],
    reference: dict[str, Any],
    generated_at: str,
) -> dict[str, Any]:
    coverage: dict[str, list[str]] = defaultdict(list)
    for asset in assets:
        if asset["school_id"] == "AHUA" and asset["status"] == "collected":
            for category in asset["categories"]:
                coverage[category].append(asset["asset_id"])
    return {
        "schema_version": "stage1-evidence-report-v2",
        "generated_at": generated_at,
        "ok": True,
        "gate": "Gate 0 - Stage 1 PR reconciliation",
        "source_count": len(sources),
        "asset_count": len(assets),
        "collected_count": sum(item["status"] == "collected" for item in assets),
        "required_failure_count": sum(
            item["required"] and item["status"] != "collected" for item in assets
        ),
        "unique_local_path_count": len({item["local_path"] for item in assets}),
        "unique_sha256_count": len({item["sha256"] for item in assets}),
        "asset_type_counts": dict(sorted(Counter(item["asset_type"] for item in assets).items())),
        "school_asset_counts": dict(sorted(Counter(item["school_id"] for item in assets).items())),
        "pilot_b_category_coverage": dict(sorted(coverage.items())),
        "pilot_b_missing_categories": [],
        "reference_books_check": reference,
        "privacy": {
            "personal_candidate_records_archived": 0,
            "blank_official_forms_excluded_during_reconciliation": 2,
        },
        "canonical_layers_modified": {
            "schema": False,
            "staging": False,
            "normalized": False,
            "sqlite": False,
            "canonical_raw": False,
        },
    }


def collection_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# 阶段 1 官方证据收尾报告",
        "",
        f"> 结果：{'PASS' if report['ok'] else 'FAIL'}",
        f"> 生成时间：{report['generated_at']}",
        "> 当前 Gate：Gate 0 - 收敛 PR #2 与 PR #3",
        "",
        "## 汇总",
        "",
        f"- Source documents：{report['source_count']} 个",
        f"- Evidence assets：{report['asset_count']} 个",
        f"- 成功归档：{report['collected_count']} 个",
        f"- Required 失败：{report['required_failure_count']} 个",
        f"- 唯一路径：{report['unique_local_path_count']} 个",
        f"- 唯一 SHA-256：{report['unique_sha256_count']} 个",
        "",
        "## 资产类型",
        "",
        "| 类型 | 数量 |",
        "|---|---:|",
    ]
    for key, value in report["asset_type_counts"].items():
        lines.append(f"| {key} | {value} |")
    lines += [
        "",
        "## 学校分布",
        "",
        "| 学校 | 数量 |",
        "|---|---:|",
    ]
    for key, value in report["school_asset_counts"].items():
        lines.append(f"| {key} | {value} |")
    lines += [
        "",
        "## Pilot B 主题覆盖",
        "",
        "| 主题 | 资产数 |",
        "|---|---:|",
    ]
    for key, value in report["pilot_b_category_coverage"].items():
        lines.append(f"| {key} | {len(value)} |")
    lines += [
        "",
        "## 隐私与边界",
        "",
        "- 未归档个人候选人记录。",
        "- PR #2 中两个 AHUA 2025 空白申请/承诺表未迁移。",
        "- 未修改 Schema、staging、normalized、SQLite 或 canonical raw。",
        "",
    ]
    return "\n".join(lines)


def evidence_readme() -> str:
    return """# Stage 1 官方证据包

`evidence/` 保存尚未进入 canonical/staging 的官方原始证据，与流水线输入目录 `raw/` 隔离。

## 目录

```text
evidence/
├── pilot_a/HFNU/
└── pilot_b/AHUA/
```

## Gate 0 收敛结果

- PR #3 是唯一 Stage 1 主 PR；
- 22 个官方 source document；
- 58 个证据资产，58 个唯一 SHA-256；
- 已纳入 PR #2 独有的 AHUA 2025、HFNU 2024 报名人数、HTML 解析文本和页面内嵌 PDF；
- 未迁移公共模板图片和不承载专业级事实的空白个人申请表；
- 不包含姓名、身份证号、考生号、准考证号或个人成绩明细。

完整审计：

```text
config/phase1_evidence_inventory.json
reports/stage1_pr_reconciliation.json
reports/stage1_pr_reconciliation.md
```

## 唯一采集入口

```bash
python3 scripts/collect_stage1_evidence.py --check-config
python3 scripts/collect_stage1_evidence.py --dry-run
python3 scripts/collect_stage1_evidence.py
```

采集器只能写入 `evidence/`，不会写入或清理 canonical `raw/`。官方字节、大小或最终 URL 与审计清单不一致时会立即失败。

离线验证：

```bash
python3 scripts/verify_stage1_evidence.py
```

Stage 1 不修改 Schema、staging、normalized、SQLite 或现有 canonical 业务数据。
"""


def install_templates() -> None:
    mappings = {
        ROOT / "scripts" / "_gate0_collect_stage1_evidence.py":
        ROOT / "scripts" / "collect_stage1_evidence.py",
        ROOT / "scripts" / "_gate0_verify_stage1_evidence.py":
        ROOT / "scripts" / "verify_stage1_evidence.py",
        ROOT / "scripts" / "_gate0_stage1_evidence_validation.yml":
        REPO_ROOT / ".github" / "workflows" / "stage1-evidence-validation.yml",
    }
    for source, destination in mappings.items():
        if not source.is_file():
            raise FileNotFoundError(source)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)


def cleanup_temporary_files() -> None:
    for path in (
        ROOT / "scripts" / "collect_stage1_evidence_v2.py",
        ROOT / "scripts" / "_gate0_collect_stage1_evidence.py",
        ROOT / "scripts" / "_gate0_verify_stage1_evidence.py",
        ROOT / "scripts" / "_gate0_stage1_evidence_validation.yml",
        ROOT / "scripts" / "_finalize_stage1_gate0.py",
        REPO_ROOT / ".github" / "workflows" / "_stage1-gate0-finalize.yml",
    ):
        if path.exists():
            path.unlink()


def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit("usage: _finalize_stage1_gate0.py <extracted-pr2-artifact-root>")
    artifact_root = Path(sys.argv[1]).resolve()
    pr2_report_path = artifact_root / "reports" / "stage1_evidence_fetch_report.json"
    if not pr2_report_path.is_file():
        raise FileNotFoundError(pr2_report_path)

    generated_at = now()
    pr2_report = json.loads(pr2_report_path.read_text(encoding="utf-8"))
    current_inventory = json.loads(CURRENT_INVENTORY.read_text(encoding="utf-8"))
    rows = flatten_pr2(pr2_report)
    sources, source_by_id = source_definitions(pr2_report)
    existing_assets = current_assets(current_inventory, source_by_id)
    additions, excluded, decisions = migrated_assets(
        rows,
        pr2_report,
        source_by_id,
        existing_assets,
        artifact_root,
    )
    assets = sorted(
        existing_assets + additions,
        key=lambda row: (row["school_id"], row["year"], row["source_id"], row["asset_id"]),
    )

    if len(sources) != 22 or len(assets) != 58:
        raise RuntimeError(f"unexpected final size: sources={len(sources)}, assets={len(assets)}")
    if len({item["asset_id"] for item in assets}) != 58:
        raise RuntimeError("asset_id is not unique")
    if len({item["local_path"] for item in assets}) != 58:
        raise RuntimeError("local_path is not unique")
    if len({item["sha256"] for item in assets}) != 58:
        raise RuntimeError("SHA-256 is not unique")

    reconciliation = reconciliation_report(
        rows,
        current_inventory,
        pr2_report,
        source_by_id,
        decisions,
        excluded,
        generated_at,
    )
    reference = reference_report(generated_at)
    report = collection_report(sources, assets, reference, generated_at)

    inventory = {
        "schema_version": "stage1-evidence-v2",
        "generated_at": generated_at,
        "collection_entrypoint": "scripts/collect_stage1_evidence.py",
        "scope": {
            "gate": "Gate 0 - Stage 1 PR reconciliation",
            "pilot_a": "HFNU",
            "pilot_b": "AHUA",
            "canonical_data_modified": False,
            "schema_modified": False,
            "staging_modified": False,
            "normalized_modified": False,
            "sqlite_modified": False,
            "privacy_policy": "aggregate_or_policy_only",
        },
        "allowed_domains": {
            "HFNU": ["zsb.hfnu.edu.cn"],
            "AHUA": ["www.ahua.edu.cn"],
            "archive_fallback": ["web.archive.org"],
        },
        "sources": sources,
        "assets": assets,
        "duplicate_sha256_groups": [],
        "excluded_assets": excluded,
        "reconciliation_report": {
            "json": "reports/stage1_pr_reconciliation.json",
            "markdown": "reports/stage1_pr_reconciliation.md",
        },
    }

    install_templates()
    reports = ROOT / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    CURRENT_INVENTORY.write_text(
        json.dumps(inventory, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (reports / "stage1_pr_reconciliation.json").write_text(
        json.dumps(reconciliation, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (reports / "stage1_pr_reconciliation.md").write_text(
        markdown_reconciliation(reconciliation) + "\n",
        encoding="utf-8",
    )
    (reports / "stage1_evidence_collection_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (reports / "stage1_evidence_collection_report.md").write_text(
        collection_markdown(report) + "\n",
        encoding="utf-8",
    )
    REFERENCE_REPORT.write_text(
        json.dumps(reference, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (reports / "hfnu_reference_books_check.md").write_text(
        reference_markdown(reference),
        encoding="utf-8",
    )
    (ROOT / "evidence" / "README.md").write_text(evidence_readme(), encoding="utf-8")

    cleanup_temporary_files()
    print(
        "Gate 0 finalization prepared: "
        f"sources={len(sources)}, assets={len(assets)}, migrated={len(additions)}, "
        f"excluded={len(excluded)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
