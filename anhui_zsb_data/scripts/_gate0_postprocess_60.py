#!/usr/bin/env python3
"""Complete the audited Gate 0 reconciliation after the one-time reconciler.

The initial reconciler deliberately excluded two AHUA 2025 official blank-form
attachments. Gate 0 review confirmed that they are official, directly linked to
the admission-policy source, byte-verifiable, and contain no populated candidate
records. This helper adds those two assets, updates the reconciliation/collection
reports to the approved 60-asset result, verifies every byte, and deletes itself.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
INVENTORY_PATH = ROOT / "config" / "phase1_evidence_inventory.json"
RECONCILIATION_JSON = ROOT / "reports" / "stage1_pr_reconciliation.json"
RECONCILIATION_MD = ROOT / "reports" / "stage1_pr_reconciliation.md"
COLLECTION_JSON = ROOT / "reports" / "stage1_evidence_collection_report.json"
COLLECTION_MD = ROOT / "reports" / "stage1_evidence_collection_report.md"
README_PATH = ROOT / "evidence" / "README.md"
TARGET_SOURCE_ID = "SRC-AHUA-2025-ZC"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def copy_and_verify(source: Path, destination: Path, size: int, digest: str) -> None:
    if not source.is_file():
        raise FileNotFoundError(source)
    if source.stat().st_size != size or sha256_file(source) != digest:
        raise RuntimeError(f"artifact bytes differ from audit report: {source}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)
    if destination.stat().st_size != size or sha256_file(destination) != digest:
        raise RuntimeError(f"copied bytes failed verification: {destination}")


def find_pr2_attachment_rows(pr2_report: dict[str, Any]) -> list[dict[str, Any]]:
    for source in pr2_report["sources"]:
        if source["source_id"] != TARGET_SOURCE_ID:
            continue
        rows: list[dict[str, Any]] = []
        for record in source.get("assets", []):
            suffix = Path(record["local_path"]).suffix.lower()
            if suffix not in {".doc", ".docx"}:
                continue
            rows.append(
                {
                    "source": source,
                    "record": record,
                    "suffix": suffix,
                }
            )
        if len(rows) != 2:
            raise RuntimeError(f"expected two AHUA 2025 policy attachments, got {len(rows)}")
        return sorted(rows, key=lambda item: item["record"]["local_path"])
    raise RuntimeError(f"PR #2 source not found: {TARGET_SOURCE_ID}")


def build_asset(
    source: dict[str, Any],
    record: dict[str, Any],
    index: int,
    generated_at: str,
    destination: str,
) -> dict[str, Any]:
    suffix = Path(destination).suffix.lower()
    return {
        "asset_id": f"ASSET-AHUA-2025-ZC-ATT-{index:02d}",
        "asset_id_aliases": [],
        "source_id": TARGET_SOURCE_ID,
        "school_id": "AHUA",
        "year": 2025,
        "title": source["title"],
        "categories": [
            "招生章程",
            "招生计划",
            "专业及培养地点",
            "考试科目",
            "报考范围",
            "录取规则",
            "调剂信息",
        ],
        "asset_type": suffix.lstrip("."),
        "source_level": "S",
        "document_url": source["url"],
        "source_url": record["source_url"],
        "retrieval_url": record["final_url"],
        "retrieval_method": "official_direct",
        "local_path": destination,
        "original_file_name": Path(record["local_path"]).name,
        "content_type": record["content_type"],
        "http_status": 200,
        "file_size": record["size_bytes"],
        "sha256": record["sha256"],
        "retrieved_at": generated_at,
        "required": False,
        "status": "collected",
        "error": "",
        "parent_asset_id": "ASSET-AHUA-2025-ZC-HTML",
        "parser_name": "",
        "parser_version": "",
        "generated_at": "",
        "privacy_classification": "blank_official_form",
        "provenance_pr": "PR #2",
        "provenance_path": record["local_path"],
    }


def update_inventory(
    artifact_root: Path,
    pr2_report: dict[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    inventory = json.loads(INVENTORY_PATH.read_text(encoding="utf-8"))
    generated_at = inventory["generated_at"]
    attachments = find_pr2_attachment_rows(pr2_report)
    new_assets: list[dict[str, Any]] = []

    for index, item in enumerate(attachments, start=1):
        record = item["record"]
        suffix = item["suffix"]
        destination = (
            f"evidence/pilot_b/AHUA/2025/"
            f"DOC-AHUA-2025-ZC-ATT-{index:02d}{suffix}"
        )
        copy_and_verify(
            artifact_root / record["local_path"],
            ROOT / destination,
            int(record["size_bytes"]),
            str(record["sha256"]),
        )
        new_assets.append(
            build_asset(item["source"], record, index, generated_at, destination)
        )

    existing_ids = {asset["asset_id"] for asset in inventory["assets"]}
    inventory["assets"] = [
        asset for asset in inventory["assets"] if asset["asset_id"] not in {
            item["asset_id"] for item in new_assets
        }
    ] + new_assets
    inventory["assets"].sort(
        key=lambda row: (row["school_id"], row["year"], row["source_id"], row["asset_id"])
    )
    inventory["excluded_assets"] = [
        item
        for item in inventory.get("excluded_assets", [])
        if item.get("source_id") != TARGET_SOURCE_ID
    ]

    assets = inventory["assets"]
    if len(assets) != 60:
        raise RuntimeError(f"expected 60 assets after reconciliation, got {len(assets)}")
    if len({item["asset_id"] for item in assets}) != 60:
        raise RuntimeError("asset_id is not unique")
    if len({item["local_path"] for item in assets}) != 60:
        raise RuntimeError("local_path is not unique")
    if len({item["sha256"] for item in assets}) != 60:
        raise RuntimeError("SHA-256 is not unique")
    if existing_ids & {item["asset_id"] for item in new_assets}:
        print("Replacing previously staged attachment metadata with audited entries")

    INVENTORY_PATH.write_text(
        json.dumps(inventory, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return inventory, new_assets


def update_reconciliation_json(new_assets: list[dict[str, Any]]) -> dict[str, Any]:
    report = json.loads(RECONCILIATION_JSON.read_text(encoding="utf-8"))
    target_by_sha = {item["sha256"]: item for item in new_assets}

    for item in report.get("only_pr2", []):
        target = target_by_sha.get(item.get("sha256"))
        if not target:
            continue
        item["action"] = "migrate"
        item["destination_path"] = target["local_path"]
        item["reason"] = (
            "官方章程关联的空白申请/承诺表；来源、字节和哈希可验证，"
            "未包含已填写候选人记录，经隐私复核后作为原始附件保留。"
        )

    report["suspected_unrelated_attachments"] = []
    report["migration_decision"] = {
        "migrate_to_pr3": [
            item for item in report.get("only_pr2", []) if item.get("action") == "migrate"
        ],
        "do_not_migrate": [
            item for item in report.get("only_pr2", []) if item.get("action") == "exclude"
        ],
    }
    summary = report["summary"]
    summary["only_pr2_migrated"] = 33
    summary["only_pr2_excluded_unrelated"] = 0
    summary["final_asset_count"] = 60
    summary["final_unique_sha256_count"] = 60

    RECONCILIATION_JSON.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return report


def update_reconciliation_markdown(report: dict[str, Any], new_assets: list[dict[str, Any]]) -> None:
    text = RECONCILIATION_MD.read_text(encoding="utf-8")
    replacements = {
        "从 PR #2 迁移 31 个有效文件；2 个 AHUA 2025 空白申请表不迁移。":
        "从 PR #2 迁移 33 个有效文件；两个 AHUA 2025 官方空白申请/承诺表经隐私复核后作为原始附件保留。",
        "收敛后：22 个 source document、58 个资产、58 个唯一 SHA-256。":
        "收敛后：22 个 source document、60 个资产、60 个唯一 SHA-256。",
        "| 从 PR #2 迁移 | 31 |": "| 从 PR #2 迁移 | 33 |",
        "| PR #2 独有但不迁移 | 2 |": "| PR #2 独有但不迁移 | 0 |",
        "| 最终资产 | 58 |": "| 最终资产 | 60 |",
        "- 不迁移 AHUA 2025 两个空白个人申请表及 28 个站点公共图片。":
        "- 迁移经隐私复核的 AHUA 2025 两个官方空白申请/承诺表；继续排除 28 个站点公共图片。",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)

    sha_to_path = {item["sha256"]: item["local_path"] for item in new_assets}
    lines: list[str] = []
    in_unrelated = False
    for line in text.splitlines():
        if line == "## 疑似无关附件":
            in_unrelated = True
        elif line.startswith("## ") and line != "## 疑似无关附件":
            in_unrelated = False
        if in_unrelated and any(digest in line for digest in sha_to_path):
            continue
        for digest, destination in sha_to_path.items():
            if digest in line and "| exclude |" in line:
                line = line.replace("| exclude | `` |", f"| migrate | `{destination}` |")
        lines.append(line)

    RECONCILIATION_MD.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def rebuild_collection_report(inventory: dict[str, Any]) -> dict[str, Any]:
    report = json.loads(COLLECTION_JSON.read_text(encoding="utf-8"))
    assets = inventory["assets"]
    coverage: dict[str, list[str]] = defaultdict(list)
    for asset in assets:
        if asset["school_id"] == "AHUA" and asset["status"] == "collected":
            for category in asset["categories"]:
                coverage[category].append(asset["asset_id"])

    report["asset_count"] = len(assets)
    report["collected_count"] = sum(item["status"] == "collected" for item in assets)
    report["required_failure_count"] = sum(
        item["required"] and item["status"] != "collected" for item in assets
    )
    report["unique_local_path_count"] = len({item["local_path"] for item in assets})
    report["unique_sha256_count"] = len({item["sha256"] for item in assets})
    report["asset_type_counts"] = dict(
        sorted(Counter(item["asset_type"] for item in assets).items())
    )
    report["school_asset_counts"] = dict(
        sorted(Counter(item["school_id"] for item in assets).items())
    )
    report["pilot_b_category_coverage"] = dict(sorted(coverage.items()))
    report["privacy"] = {
        "personal_candidate_records_archived": 0,
        "blank_official_forms_archived": 2,
        "blank_official_forms_excluded_during_reconciliation": 0,
    }
    COLLECTION_JSON.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return report


def write_collection_markdown(report: dict[str, Any]) -> None:
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
    lines += ["", "## 学校分布", "", "| 学校 | 数量 |", "|---|---:|"]
    for key, value in report["school_asset_counts"].items():
        lines.append(f"| {key} | {value} |")
    lines += ["", "## Pilot B 主题覆盖", "", "| 主题 | 资产数 |", "|---|---:|"]
    for key, value in report["pilot_b_category_coverage"].items():
        lines.append(f"| {key} | {len(value)} |")
    lines += [
        "",
        "## 隐私与边界",
        "",
        "- 未归档个人候选人记录。",
        "- 两个 AHUA 2025 官方空白申请/承诺表已完成隐私复核并作为章程原始附件保留。",
        "- 未修改 Schema、staging、normalized、SQLite 或 canonical raw。",
        "",
    ]
    COLLECTION_MD.write_text("\n".join(lines), encoding="utf-8")


def update_readme() -> None:
    text = README_PATH.read_text(encoding="utf-8")
    text = text.replace("58 个证据资产，58 个唯一 SHA-256", "60 个证据资产，60 个唯一 SHA-256")
    text = text.replace(
        "未迁移公共模板图片和不承载专业级事实的空白个人申请表；",
        "排除公共模板图片；两个官方空白申请/承诺表经隐私复核后作为章程附件保留；",
    )
    README_PATH.write_text(text, encoding="utf-8")


def verify_all_files(inventory: dict[str, Any]) -> None:
    for asset in inventory["assets"]:
        path = ROOT / asset["local_path"]
        if not path.is_file():
            raise FileNotFoundError(path)
        if path.stat().st_size != int(asset["file_size"]):
            raise RuntimeError(f"size mismatch: {asset['asset_id']}")
        if sha256_file(path) != asset["sha256"]:
            raise RuntimeError(f"SHA-256 mismatch: {asset['asset_id']}")


def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit("usage: _gate0_postprocess_60.py <extracted-pr2-artifact-root>")
    artifact_root = Path(sys.argv[1]).resolve()
    pr2_report_path = artifact_root / "reports" / "stage1_evidence_fetch_report.json"
    if not pr2_report_path.is_file():
        raise FileNotFoundError(pr2_report_path)
    pr2_report = json.loads(pr2_report_path.read_text(encoding="utf-8"))

    inventory, new_assets = update_inventory(artifact_root, pr2_report)
    reconciliation = update_reconciliation_json(new_assets)
    update_reconciliation_markdown(reconciliation, new_assets)
    collection = rebuild_collection_report(inventory)
    write_collection_markdown(collection)
    update_readme()
    verify_all_files(inventory)

    self_path = Path(__file__).resolve()
    if self_path.is_file():
        self_path.unlink()
    print(
        "Gate 0 post-processing complete: "
        "sources=22, assets=60, migrated=33, excluded_unrelated=0"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
