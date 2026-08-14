#!/usr/bin/env python3
"""Remove repeated site-chrome images from the Stage 1 evidence archive.

Official university article templates sometimes embed the same QR-code or
branding images in every page. Those bytes are not source-specific evidence.
An image is treated as shared site chrome only when the same SHA-256 appears in
at least three distinct configured source pages. Documents are never removed.
"""
from __future__ import annotations

import json
from collections import defaultdict
from typing import Any

from fetch_stage1_evidence import (
    REPORT_JSON,
    REPORT_MD,
    ROOT,
    build_markdown,
    write_text_if_changed,
)

MIN_DISTINCT_SOURCES = 3


def embedded_pdf_section(report: dict[str, Any]) -> str:
    embedded = report.get("embedded_pdf_fetch")
    if not isinstance(embedded, dict):
        return ""
    unmet = report.get("required_document_failure_source_ids", [])
    lines = [
        "## 页面内嵌 PDF 补抓",
        "",
        f"- 成功发现并归档：{int(embedded.get('discovered_count', 0))} 个",
        f"- 下载失败或内容异常：{int(embedded.get('failed_count', 0))} 个",
        f"- 强制文档证据未满足：{len(unmet)} 个",
        "",
    ]
    if unmet:
        lines.append("未满足来源：" + "、".join(f"`{source_id}`" for source_id in unmet))
        lines.append("")
    return "\n".join(lines) + "\n"


def main() -> int:
    if not REPORT_JSON.is_file():
        raise SystemExit(f"Missing fetch report: {REPORT_JSON}")

    report: dict[str, Any] = json.loads(REPORT_JSON.read_text(encoding="utf-8"))
    groups: dict[str, list[tuple[dict[str, Any], dict[str, Any]]]] = defaultdict(list)

    for source in report.get("sources", []):
        for asset in source.get("assets", []):
            if asset.get("kind") == "image" and asset.get("sha256"):
                groups[str(asset["sha256"])].append((source, asset))

    removed: list[dict[str, Any]] = []
    filtered_groups: list[dict[str, Any]] = []
    for sha256, entries in sorted(groups.items()):
        source_ids = sorted({str(source["source_id"]) for source, _asset in entries})
        if len(source_ids) < MIN_DISTINCT_SOURCES:
            continue

        group_paths: list[str] = []
        source_urls = sorted({str(asset.get("source_url", "")) for _source, asset in entries})
        for source, asset in entries:
            local_path = str(asset["local_path"])
            path = ROOT / local_path
            if path.is_file():
                path.unlink()
            source["assets"] = [
                existing
                for existing in source.get("assets", [])
                if existing.get("local_path") != local_path
            ]
            source["skipped_asset_count"] = int(source.get("skipped_asset_count", 0)) + 1
            group_paths.append(local_path)
            removed.append(
                {
                    "source_id": source["source_id"],
                    "local_path": local_path,
                    "sha256": sha256,
                }
            )

        filtered_groups.append(
            {
                "sha256": sha256,
                "distinct_source_count": len(source_ids),
                "source_ids": source_ids,
                "source_urls": source_urls,
                "removed_paths": sorted(group_paths),
                "reason": "identical image reused across multiple official pages; classified as site chrome",
            }
        )

    report["filtered_shared_images"] = filtered_groups
    summary = report.setdefault("summary", {})
    summary["asset_count"] = sum(
        len(source.get("assets", [])) for source in report.get("sources", [])
    )
    summary["filtered_shared_image_count"] = len(removed)
    summary["filtered_shared_image_group_count"] = len(filtered_groups)

    write_text_if_changed(
        REPORT_JSON,
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    )

    markdown = build_markdown(report)
    sections: list[str] = []
    embedded = embedded_pdf_section(report)
    if embedded:
        sections.append(embedded)
    if filtered_groups:
        lines = [
            "## 自动排除的跨页面共享图片",
            "",
            f"- 排除文件：{len(removed)} 个",
            f"- 重复内容组：{len(filtered_groups)} 组",
            "- 判定条件：同一图片 SHA-256 至少出现在 3 个不同来源页面；文档附件永不按此规则删除。",
            "",
        ]
        for group in filtered_groups:
            lines.append(
                f"- `{group['sha256']}`：出现在 {group['distinct_source_count']} 个来源页面，"
                f"删除 {len(group['removed_paths'])} 份重复副本。"
            )
        sections.append("\n".join(lines) + "\n")
    if sections:
        markdown = markdown.replace("## 边界\n", "\n".join(sections) + "\n## 边界\n", 1)
    write_text_if_changed(REPORT_MD, markdown)

    print(
        "Stage 1 evidence cleanup: "
        f"removed={len(removed)}, groups={len(filtered_groups)}, "
        f"remaining_assets={summary['asset_count']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
