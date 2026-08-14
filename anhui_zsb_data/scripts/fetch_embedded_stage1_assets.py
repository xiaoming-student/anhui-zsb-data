#!/usr/bin/env python3
"""Fetch official PDFs embedded inside archived page JavaScript.

Some university CMS pages render a PDF through calls such as
``showVsbpdfIframe('/__local/...pdf', ...)`` rather than an HTML anchor. The
primary fetcher intentionally follows only explicit links and images, so this
second pass scans already archived HTML for same-host embedded PDF literals.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any
from urllib.parse import urldefrag, urljoin, urlparse

from fetch_stage1_evidence import (
    REPORT_JSON,
    REPORT_MD,
    ROOT,
    build_markdown,
    fetch as fetch_url,
    file_record,
    infer_extension,
    make_opener,
    normalize_host,
    write_bytes_if_changed,
    write_text_if_changed,
)

PDF_LITERAL_RE = re.compile(
    r"[\"'](?P<url>(?:https?://[^\"']+|/[^\"']+)\.pdf(?:\?[^\"']*)?)[\"']",
    flags=re.IGNORECASE,
)
ATTACHMENT_INDEX_RE = re.compile(r"-ATT-(\d+)", flags=re.IGNORECASE)


def next_attachment_index(source: dict[str, Any]) -> int:
    indexes: list[int] = []
    for asset in source.get("assets", []):
        match = ATTACHMENT_INDEX_RE.search(str(asset.get("local_path", "")))
        if match:
            indexes.append(int(match.group(1)))
    return max(indexes, default=0) + 1


def source_expected_documents(source: dict[str, Any]) -> int:
    expected = source.get("expected_assets", {})
    return int(expected.get("min_documents", 0) or 0)


def refresh_expected_state(source: dict[str, Any]) -> None:
    expected = source.setdefault("expected_assets", {})
    document_count = sum(
        1 for asset in source.get("assets", []) if asset.get("kind") == "document"
    )
    min_documents = int(expected.get("min_documents", 0) or 0)
    expected["document_count"] = document_count
    expected["met"] = document_count >= min_documents
    if source.get("page") and expected["met"]:
        source["status"] = "complete"
    elif source.get("page"):
        source["status"] = "partial"


def main() -> int:
    if not REPORT_JSON.is_file():
        raise SystemExit(f"Missing fetch report: {REPORT_JSON}")

    report: dict[str, Any] = json.loads(REPORT_JSON.read_text(encoding="utf-8"))
    opener = make_opener()
    discovered = 0
    failed = 0

    for source in report.get("sources", []):
        page = source.get("page")
        if not page:
            continue
        page_path = ROOT / str(page["local_path"])
        if not page_path.is_file():
            continue

        html_text = page_path.read_text(encoding="utf-8", errors="ignore")
        page_url = str(source["url"])
        page_host = normalize_host(urlparse(page_url).hostname)
        existing_urls = {
            str(asset.get("source_url", ""))
            for asset in source.get("assets", [])
        } | {
            str(asset.get("final_url", ""))
            for asset in source.get("assets", [])
        }

        candidates: list[str] = []
        seen: set[str] = set()
        for match in PDF_LITERAL_RE.finditer(html_text):
            absolute, _fragment = urldefrag(urljoin(page_url, match.group("url")))
            parsed = urlparse(absolute)
            if parsed.scheme not in {"http", "https"}:
                continue
            if normalize_host(parsed.hostname) != page_host:
                continue
            if absolute in seen or absolute in existing_urls:
                continue
            seen.add(absolute)
            candidates.append(absolute)

        for embedded_url in candidates:
            try:
                response = fetch_url(opener, embedded_url, referer=page_url)
            except Exception as exc:  # noqa: BLE001 - preserve exact fetch failure
                failed += 1
                source.setdefault("blocked_assets", []).append(
                    {
                        "url": embedded_url,
                        "label": f"{source['title']}（页面内嵌 PDF）",
                        "status": "embedded_pdf_fetch_error",
                        "error": f"{type(exc).__name__}: {exc}",
                    }
                )
                continue

            extension = infer_extension(response, embedded_url)
            if extension != ".pdf" or not response.data.startswith(b"%PDF-"):
                failed += 1
                source.setdefault("blocked_assets", []).append(
                    {
                        "url": embedded_url,
                        "final_url": response.final_url,
                        "label": f"{source['title']}（页面内嵌 PDF）",
                        "status": "embedded_pdf_unexpected_content",
                        "http_status": response.status,
                        "content_type": response.content_type,
                    }
                )
                continue

            output_path = page_path.with_name(
                f"{page_path.stem}-ATT-{next_attachment_index(source):02d}.pdf"
            )
            write_bytes_if_changed(output_path, response.data)
            source.setdefault("assets", []).append(
                file_record(
                    output_path,
                    source_id=str(source["source_id"]),
                    source_url=embedded_url,
                    final_url=response.final_url,
                    content_type=response.content_type,
                    kind="document",
                    label=f"{source['title']}（页面内嵌 PDF）",
                )
            )
            discovered += 1

        refresh_expected_state(source)

    report["embedded_pdf_fetch"] = {
        "discovered_count": discovered,
        "failed_count": failed,
    }
    summary = report.setdefault("summary", {})
    summary["asset_count"] = sum(
        len(source.get("assets", [])) for source in report.get("sources", [])
    )
    summary["embedded_pdf_count"] = discovered

    unmet_required = [
        source["source_id"]
        for source in report.get("sources", [])
        if source_expected_documents(source) > 0
        and not source.get("expected_assets", {}).get("met", False)
    ]
    summary["required_document_failures"] = len(unmet_required)
    report["required_document_failure_source_ids"] = unmet_required

    write_text_if_changed(
        REPORT_JSON,
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    )

    markdown = build_markdown(report)
    lines = [
        "## 页面内嵌 PDF 补抓",
        "",
        f"- 成功发现并归档：{discovered} 个",
        f"- 下载失败或内容异常：{failed} 个",
        f"- 强制文档证据未满足：{len(unmet_required)} 个",
        "",
    ]
    if unmet_required:
        lines.append("未满足来源：" + "、".join(f"`{source_id}`" for source_id in unmet_required))
        lines.append("")
    markdown = markdown.replace("## 边界\n", "\n".join(lines) + "\n## 边界\n", 1)
    write_text_if_changed(REPORT_MD, markdown)

    print(
        "Embedded Stage 1 PDFs: "
        f"discovered={discovered}, failed={failed}, required_unmet={len(unmet_required)}"
    )
    return 1 if unmet_required else 0


if __name__ == "__main__":
    raise SystemExit(main())
