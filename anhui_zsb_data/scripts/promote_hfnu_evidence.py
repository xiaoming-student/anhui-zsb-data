#!/usr/bin/env python3
"""Promote audited HFNU Stage 1 evidence into canonical ``raw/`` and source config.

The Stage 1 ``evidence/`` tree is immutable. This tool copies identical bytes to
``raw/<year>/HFNU/``, registers every copied file in ``config/source_assets.json``,
and adds/updates the corresponding HFNU source documents. It never processes
AHUA, never accesses the network, never deletes raw files, and refuses to
overwrite a different byte stream.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
INVENTORY_PATH = ROOT / "config" / "phase1_evidence_inventory.json"
CATALOG_PATH = ROOT / "config" / "source_catalog.json"
ASSETS_PATH = ROOT / "config" / "source_assets.json"
REPORT_JSON = ROOT / "reports" / "stage2a_hfnu_asset_mapping.json"
CONFIG_MAPPING_JSON = ROOT / "config" / "stage2a_hfnu_asset_mapping.json"
REPORT_MD = ROOT / "reports" / "stage2a_hfnu_asset_mapping.md"
RAW_ROOT = ROOT / "raw"
EVIDENCE_PREFIX = Path("evidence/pilot_a/HFNU")

PUBLISH_DATES = {
    "SRC-HFNU-2024-BMRS": "2024-04-03",
    "SRC-HFNU-2024-DG": "2024-03-14",
    "SRC-HFNU-2024-LQ": "2024-05-24",
    "SRC-HFNU-2024-ZC": "2024-03-21",
    "SRC-HFNU-2025-DG": "2024-11-06",
    "SRC-HFNU-2025-LQ": "2025-05-26",
    "SRC-HFNU-2026-DG": "2025-12-31",
    "SRC-HFNU-2026-LQ": "2026-05-21",
}


class PromotionError(RuntimeError):
    """Raised when evidence cannot be promoted without ambiguity."""


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def dump_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def safe_relative(value: str) -> Path:
    path = Path(value)
    if path.is_absolute() or ".." in path.parts:
        raise PromotionError(f"unsafe path: {value}")
    return path


def canonical_path(asset: dict[str, Any]) -> str:
    evidence_path = safe_relative(str(asset["local_path"]))
    prefix = EVIDENCE_PREFIX.parts
    if evidence_path.parts[: len(prefix)] != prefix:
        raise PromotionError(
            f"HFNU promotion received asset outside {EVIDENCE_PREFIX.as_posix()}: "
            f"{asset['asset_id']} -> {asset['local_path']}"
        )
    if str(asset.get("school_id")) != "HFNU":
        raise PromotionError(f"non-HFNU asset rejected: {asset.get('asset_id')}")
    year = int(asset["year"])
    if evidence_path.parts[len(prefix)] != str(year):
        raise PromotionError(f"asset year/path mismatch: {asset['asset_id']}")
    return (Path("raw") / str(year) / "HFNU" / evidence_path.name).as_posix()


def canonical_asset_type(asset_type: str) -> str:
    if asset_type == "parsed_text":
        return "parsed_text"
    if asset_type == "html_snapshot":
        return "html_snapshot"
    if asset_type in {"pdf", "doc", "docx"}:
        return "raw_document"
    raise PromotionError(f"unsupported HFNU asset type: {asset_type}")


def source_note(source: dict[str, Any], source_assets: list[dict[str, Any]]) -> str:
    types = Counter(item["asset_type"] for item in source_assets)
    details: list[str] = []
    if types["html_snapshot"]:
        details.append(f"HTML快照{types['html_snapshot']}个")
    raw_documents = sum(types[key] for key in ("pdf", "doc", "docx"))
    if raw_documents:
        details.append(f"官方附件/原始文档{raw_documents}个")
    if types["parsed_text"]:
        details.append(f"确定性解析文本{types['parsed_text']}个")
    relationship = "、".join(details)
    return (
        f"Stage 2A 从已审计 Stage 1 evidence 复制相同字节进入 canonical raw；"
        f"{relationship}。原始 evidence 保持不变，资产父子关系见 source_assets。"
    )


def primary_asset_id(source_id: str, assets: list[dict[str, Any]]) -> str:
    """Choose the authoritative primary representation for a source document."""
    by_id = {str(item["asset_id"]): item for item in assets}
    if source_id.endswith("-DG"):
        candidate = f"ASSET-{source_id[4:]}-PDF"
    elif source_id == "SRC-HFNU-2026-LQ":
        candidate = "ASSET-HFNU-2026-LQ-EMBEDDED-PDF"
    else:
        candidate = f"ASSET-{source_id[4:]}-HTML"
    if candidate not in by_id:
        raise PromotionError(
            f"reviewed primary asset does not exist for {source_id}: {candidate}"
        )
    return candidate


def build_expected() -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
    inventory = load_json(INVENTORY_PATH)
    catalog = load_json(CATALOG_PATH)
    asset_config = load_json(ASSETS_PATH)
    if inventory.get("schema_version") != "stage1-evidence-v2":
        raise PromotionError("unsupported Stage 1 inventory version")
    if catalog.get("schema_version") != "0.3.0" or asset_config.get("schema_version") != "0.3.0":
        raise PromotionError("canonical config schema_version must remain 0.3.0")

    hfnu_sources = [item for item in inventory.get("sources", []) if item.get("school_id") == "HFNU"]
    hfnu_assets = [item for item in inventory.get("assets", []) if item.get("school_id") == "HFNU"]
    if len(hfnu_sources) != 8 or len(hfnu_assets) != 26:
        raise PromotionError(
            f"unexpected HFNU inventory size: sources={len(hfnu_sources)}, assets={len(hfnu_assets)}"
        )
    if any(item.get("school_id") != "HFNU" for item in hfnu_sources + hfnu_assets):
        raise PromotionError("AHUA asset/source reached HFNU promotion")

    source_assets_by_id: dict[str, list[dict[str, Any]]] = {}
    for asset in hfnu_assets:
        source_assets_by_id.setdefault(str(asset["source_id"]), []).append(asset)

    existing_docs = {item["source_document_id"]: dict(item) for item in catalog["documents"]}
    for source in hfnu_sources:
        source_id = str(source["source_id"])
        if source_id not in PUBLISH_DATES:
            raise PromotionError(f"publish date not reviewed: {source_id}")
        assets = source_assets_by_id.get(source_id, [])
        html_assets = [item for item in assets if item["asset_type"] == "html_snapshot"]
        if len(html_assets) != 1:
            raise PromotionError(f"source must have exactly one HTML snapshot: {source_id}")
        retrieved_values = sorted(str(item.get("retrieved_at", "")) for item in assets if item.get("retrieved_at"))
        retrieved_at = retrieved_values[0] if retrieved_values else ""
        existing = existing_docs.get(source_id, {})
        existing_docs[source_id] = {
            "source_document_id": source_id,
            "source_site_id": "SITE-HFNU-ZSB",
            "year": int(source["year"]),
            "school_id": "HFNU",
            "document_type": str(source["document_type"]),
            "title": str(source["title"]),
            "url": str(source["document_url"]),
            "publish_date": PUBLISH_DATES[source_id],
            "retrieved_at": retrieved_at or str(existing.get("retrieved_at", "")),
            "source_level": "S",
            "status": "verified",
            "primary_asset_id": primary_asset_id(source_id, assets),
            "notes": source_note(source, assets),
        }

    expected_catalog = {
        "schema_version": "0.3.0",
        "sites": catalog["sites"],
        "documents": sorted(
            existing_docs.values(),
            key=lambda row: (int(row["year"]), str(row["source_document_id"])),
        ),
    }

    existing_assets = {item["asset_id"]: dict(item) for item in asset_config["assets"]}
    mapping: list[dict[str, Any]] = []
    for asset in hfnu_assets:
        asset_id = str(asset["asset_id"])
        # Re-running after a successful promotion must be idempotent.  A Stage 1
        # asset ID may already be present in canonical config, but it is always
        # rebuilt below from the immutable inventory; any divergent current
        # value will be detected by ``--check`` when the full config is compared.
        evidence_path = safe_relative(str(asset["local_path"]))
        raw_path = canonical_path(asset)
        source_path = ROOT / evidence_path
        if not source_path.is_file():
            raise PromotionError(f"evidence file missing: {evidence_path.as_posix()}")
        actual_size = source_path.stat().st_size
        actual_sha = sha256_file(source_path)
        if actual_size != int(asset["file_size"]) or actual_sha != str(asset["sha256"]):
            raise PromotionError(f"Stage 1 evidence bytes do not match inventory: {asset_id}")

        canonical = {
            "asset_id": asset_id,
            "source_document_id": str(asset["source_id"]),
            "local_path": raw_path,
            "original_file_name": str(asset.get("original_file_name") or evidence_path.name),
            "asset_type": canonical_asset_type(str(asset["asset_type"])),
            "retrieved_at": str(asset.get("retrieved_at", "")),
            "parent_asset_id": str(asset.get("parent_asset_id", "")),
            "parser_name": str(asset.get("parser_name", "")),
            "parser_version": str(asset.get("parser_version", "")),
            "generated_at": str(asset.get("generated_at", "")),
        }
        existing_assets[asset_id] = canonical
        target = ROOT / raw_path
        canonical_sha = sha256_file(target) if target.is_file() else ""
        mapping.append(
            {
                "temporary_evidence_asset_id": asset_id,
                "canonical_asset_id": asset_id,
                "source_document_id": str(asset["source_id"]),
                "evidence_path": evidence_path.as_posix(),
                "canonical_raw_path": raw_path,
                "asset_type": str(asset["asset_type"]),
                "parent_asset_id": str(asset.get("parent_asset_id", "")),
                "file_size": actual_size,
                "evidence_sha256": actual_sha,
                "canonical_sha256": canonical_sha,
                "promotion_status": "promoted" if canonical_sha == actual_sha else "pending",
                "promotion_note": "copied unchanged from audited evidence",
            }
        )

    expected_assets = {
        "schema_version": "0.3.0",
        "assets": sorted(existing_assets.values(), key=lambda row: row["asset_id"]),
    }
    return expected_catalog, expected_assets, sorted(mapping, key=lambda row: row["canonical_asset_id"])


def unmanaged_raw(expected_assets: dict[str, Any]) -> list[str]:
    declared = {str(item["local_path"]) for item in expected_assets["assets"]}
    return [
        path.relative_to(ROOT).as_posix()
        for path in sorted(RAW_ROOT.rglob("*"))
        if path.is_file() and path.relative_to(ROOT).as_posix() not in declared
    ]


def report_payload(mapping: list[dict[str, Any]], expected_assets: dict[str, Any]) -> dict[str, Any]:
    mismatches = [item for item in mapping if item["canonical_sha256"] != item["evidence_sha256"]]
    pending = [item for item in mapping if item["promotion_status"] != "promoted"]
    duplicate_groups: dict[str, list[str]] = {}
    by_sha: dict[str, list[str]] = {}
    for item in mapping:
        by_sha.setdefault(item["evidence_sha256"], []).append(item["canonical_asset_id"])
    duplicate_groups = {sha: ids for sha, ids in by_sha.items() if len(ids) > 1}
    return {
        "schema_version": "stage2a-hfnu-asset-mapping-v1",
        "school_id": "HFNU",
        "evidence_asset_count": len(mapping),
        "promoted_count": len(mapping) - len(pending),
        "not_promoted_count": len(pending),
        "sha_mismatch_count": len(mismatches),
        "duplicate_group_count": len(duplicate_groups),
        "unmanaged_raw_files": unmanaged_raw(expected_assets),
        "mapping": mapping,
    }


def report_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Stage 2A HFNU Evidence → Canonical Raw 映射报告",
        "",
        f"- HFNU evidence assets：{report['evidence_asset_count']}",
        f"- 已提升：{report['promoted_count']}",
        f"- 未提升：{report['not_promoted_count']}",
        f"- SHA 不一致：{report['sha_mismatch_count']}",
        f"- 重复哈希组：{report['duplicate_group_count']}",
        f"- 未登记 raw 文件：{len(report['unmanaged_raw_files'])}",
        "",
        "| Evidence Asset | Source | 类型 | Evidence 路径 | Canonical Raw | 大小 | SHA-256 | 状态 |",
        "|---|---|---|---|---|---:|---|---|",
    ]
    for item in report["mapping"]:
        lines.append(
            f"| `{item['temporary_evidence_asset_id']}` | `{item['source_document_id']}` | "
            f"{item['asset_type']} | `{item['evidence_path']}` | `{item['canonical_raw_path']}` | "
            f"{item['file_size']} | `{item['evidence_sha256']}` | {item['promotion_status']} |"
        )
    if report["unmanaged_raw_files"]:
        lines += ["", "## 未登记 Raw", ""]
        lines.extend(f"- `{item}`" for item in report["unmanaged_raw_files"])
    lines += [
        "",
        "Stage 1 evidence 文件未移动、未删除、未修改；canonical raw 为相同字节副本。",
        "",
    ]
    return "\n".join(lines)


def apply() -> int:
    expected_catalog, expected_assets, mapping = build_expected()
    for item in mapping:
        source = ROOT / item["evidence_path"]
        destination = ROOT / item["canonical_raw_path"]
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists():
            if destination.stat().st_size != item["file_size"] or sha256_file(destination) != item["evidence_sha256"]:
                raise PromotionError(f"refusing to overwrite different raw file: {item['canonical_raw_path']}")
        else:
            shutil.copyfile(source, destination)
        if destination.stat().st_size != item["file_size"] or sha256_file(destination) != item["evidence_sha256"]:
            raise PromotionError(f"copy verification failed: {item['canonical_asset_id']}")
        item["canonical_sha256"] = item["evidence_sha256"]
        item["promotion_status"] = "promoted"

    dump_json(CATALOG_PATH, expected_catalog)
    dump_json(ASSETS_PATH, expected_assets)
    report = report_payload(mapping, expected_assets)
    dump_json(CONFIG_MAPPING_JSON, report)
    dump_json(REPORT_JSON, report)
    REPORT_MD.write_text(report_markdown(report), encoding="utf-8")
    if report["sha_mismatch_count"] or report["not_promoted_count"] or report["unmanaged_raw_files"]:
        raise PromotionError(f"promotion report is not clean: {report}")
    print(
        "HFNU evidence promotion: PASS "
        f"({report['promoted_count']} assets, 0 SHA mismatches, 0 unmanaged raw files)"
    )
    return 0


def check() -> int:
    expected_catalog, expected_assets, mapping = build_expected()
    errors: list[str] = []
    current_catalog = load_json(CATALOG_PATH)
    current_assets = load_json(ASSETS_PATH)
    if current_catalog != expected_catalog:
        errors.append("config/source_catalog.json differs from deterministic Stage 2A expectation")
    if current_assets != expected_assets:
        errors.append("config/source_assets.json differs from deterministic Stage 2A expectation")
    for item in mapping:
        target = ROOT / item["canonical_raw_path"]
        if not target.is_file():
            errors.append(f"canonical raw file missing: {item['canonical_raw_path']}")
            continue
        item["canonical_sha256"] = sha256_file(target)
        item["promotion_status"] = (
            "promoted"
            if target.stat().st_size == item["file_size"] and item["canonical_sha256"] == item["evidence_sha256"]
            else "mismatch"
        )
        if item["promotion_status"] != "promoted":
            errors.append(f"canonical raw mismatch: {item['canonical_asset_id']}")
    unmanaged = unmanaged_raw(expected_assets)
    if unmanaged:
        errors.append("unmanaged raw files: " + ", ".join(unmanaged))
    report = report_payload(mapping, expected_assets)
    for path, label in (
        (CONFIG_MAPPING_JSON, "config/stage2a_hfnu_asset_mapping.json"),
        (REPORT_JSON, "reports/stage2a_hfnu_asset_mapping.json"),
    ):
        if not path.is_file() or load_json(path) != report:
            errors.append(f"{label} differs from deterministic Stage 2A mapping")
    if errors:
        print("HFNU evidence promotion check: FAIL")
        for error in errors:
            print(f"- {error}")
        return 1
    print(
        "HFNU evidence promotion check: PASS "
        f"({len(mapping)} assets, 0 SHA mismatches, 0 unmanaged raw files)"
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--check", action="store_true")
    group.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    try:
        return check() if args.check else apply()
    except (PromotionError, OSError, json.JSONDecodeError) as exc:
        print(f"HFNU evidence promotion: FAIL\n- {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
