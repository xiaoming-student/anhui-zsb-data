#!/usr/bin/env python3
"""Canonical-safe wrapper for the Stage 1 official evidence collector.

The first collector version stored newly archived material under ``raw/``. The
canonical builder intentionally rejects unmanaged files in that directory. This
wrapper remaps Stage 1 assets into an isolated ``evidence/`` namespace, removes
only files tracked by the previous Stage 1 inventory, de-duplicates attachment
URLs, detects office file formats by magic bytes, and verifies the downloaded
HFNU syllabus PDFs contain reference-book sections.
"""
from __future__ import annotations

import hashlib
import io
import json
import subprocess
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

import collect_stage1_evidence as base

ROOT = Path(__file__).resolve().parent.parent
INVENTORY = ROOT / "config" / "phase1_evidence_inventory.json"
REPORT_JSON = ROOT / "reports" / "stage1_evidence_collection_report.json"
REPORT_MD = ROOT / "reports" / "stage1_evidence_collection_report.md"
REFERENCE_JSON = ROOT / "reports" / "hfnu_reference_books_check.json"
REFERENCE_MD = ROOT / "reports" / "hfnu_reference_books_check.md"


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def cleanup_previous_assets() -> None:
    """Remove only files listed by the prior Stage 1 inventory.

    Existing canonical raw assets are not present in this inventory, so this
    cannot delete the three pre-existing HFNU canonical assets.
    """
    if not INVENTORY.is_file():
        return
    try:
        payload = json.loads(INVENTORY.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return
    for asset in payload.get("assets", []):
        relative = str(asset.get("local_path", "")).strip()
        if not relative or not relative.startswith(("raw/", "evidence/")):
            continue
        path = ROOT / relative
        if path.is_file():
            path.unlink()


def remap_paths() -> None:
    for source in base.SOURCES:
        pilot = "pilot_a" if source["school"] == "HFNU" else "pilot_b"
        filename = Path(source["path"]).name
        source["path"] = f"evidence/{pilot}/{source['school']}/{source['year']}/{filename}"
        for attachment in source.get("attachments", []):
            attachment_name = Path(attachment["path"]).name
            attachment["path"] = (
                f"evidence/{pilot}/{source['school']}/{source['year']}/{attachment_name}"
            )


def canonical_url(url: str) -> str:
    parsed = urlparse(url)
    query = urlencode(sorted(parse_qsl(parsed.query, keep_blank_values=True)))
    return urlunparse((parsed.scheme.lower(), parsed.netloc.lower(), parsed.path, "", query, ""))


def office_extension(data: bytes, current: str) -> str:
    if data.startswith(b"%PDF-"):
        return ".pdf"
    if data.startswith(b"\xd0\xcf\x11\xe0"):
        return ".doc"
    if data.startswith(b"PK\x03\x04"):
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                names = archive.namelist()
            if any(name.startswith("word/") for name in names):
                return ".docx"
            if any(name.startswith("xl/") for name in names):
                return ".xlsx"
            if any(name.startswith("ppt/") for name in names):
                return ".pptx"
        except zipfile.BadZipFile:
            pass
        return ".zip"
    return current if current in base.EXTS else ".bin"


def discovered_without_duplicates(source, data, headers):
    parser = base.Links()
    parser.feed(base.text(data, headers))
    records = []
    seen_urls = set()
    seen_hashes = set()
    explicit = {canonical_url(item["url"]) for item in source.get("attachments", [])}

    for href in parser.items:
        url = base.urljoin(source["url"], href)
        normalized = canonical_url(url)
        current_ext = Path(urlparse(url).path).suffix.lower()
        looks_like = (
            current_ext in base.EXTS
            or "download.jsp" in url
            or "/_upload/article/files/" in url
        )
        if not looks_like or normalized in explicit or normalized in seen_urls or not base.allowed(url):
            continue
        seen_urls.add(normalized)
        try:
            payload, response_headers, final, status = base.fetch(url, source["url"])
            if base.captcha(payload, response_headers):
                raise RuntimeError("blocked_by_captcha")
            digest = sha256(payload)
            if digest in seen_hashes:
                continue
            seen_hashes.add(digest)
            ext = office_extension(payload, current_ext)
            index = len(records) + 1
            destination = str(Path(source["path"]).with_suffix("")) + f"-ATT-{index:02d}{ext}"
            base.save(destination, payload)
            records.append(
                base.record(
                    source,
                    f"{source['id']}-ATT-{index:02d}",
                    ext.lstrip("."),
                    url,
                    destination,
                    payload,
                    response_headers,
                    final,
                    status,
                    "official_discovered_attachment",
                    False,
                )
            )
        except Exception as exc:  # noqa: BLE001 - preserve optional failure in inventory.
            index = len(records) + 1
            records.append(
                base.record(
                    source,
                    f"{source['id']}-ATT-{index:02d}",
                    "attachment",
                    url,
                    "",
                    required=False,
                    error=f"{type(exc).__name__}:{exc}",
                )
            )
    return records


def extract_pdf_text(pdf_path: Path) -> tuple[bool, str, str]:
    process = subprocess.run(
        ["pdftotext", "-layout", str(pdf_path), "-"],
        check=False,
        capture_output=True,
    )
    if process.returncode != 0:
        return False, "", process.stderr.decode("utf-8", errors="replace").strip()
    text = process.stdout.decode("utf-8", errors="replace")
    return True, text, ""


def verify_reference_books() -> bool:
    inventory = json.loads(INVENTORY.read_text(encoding="utf-8"))
    results = []
    all_ok = True
    new_assets = []

    for year in (2024, 2025, 2026):
        candidates = [
            asset
            for asset in inventory.get("assets", [])
            if asset.get("school_id") == "HFNU"
            and asset.get("year") == year
            and asset.get("asset_type") == "pdf"
            and asset.get("status") == "collected"
            and "DG-PDF" in str(asset.get("asset_id", ""))
        ]
        if not candidates:
            results.append({"year": year, "ok": False, "error": "syllabus PDF missing"})
            all_ok = False
            continue

        asset = candidates[0]
        pdf_path = ROOT / asset["local_path"]
        ok, extracted, error = extract_pdf_text(pdf_path)
        markers = [marker for marker in ("参考书目", "参考教材", "参考书") if marker in extracted]
        text_path = pdf_path.with_suffix(".txt")
        if ok:
            text_path.write_text(extracted, encoding="utf-8")
            text_bytes = text_path.read_bytes()
            text_asset = {
                "asset_id": f"{asset['asset_id']}-PARSED-TXT",
                "source_id": asset["source_id"],
                "school_id": "HFNU",
                "year": year,
                "title": asset["title"],
                "categories": ["考试大纲", "参考教材"],
                "asset_type": "parsed_text",
                "source_level": "S",
                "source_url": asset["source_url"],
                "retrieval_url": asset["retrieval_url"],
                "retrieval_method": "pdftotext_from_collected_official_pdf",
                "local_path": text_path.relative_to(ROOT).as_posix(),
                "original_file_name": text_path.name,
                "content_type": "text/plain",
                "http_status": asset.get("http_status"),
                "file_size": len(text_bytes),
                "sha256": sha256(text_bytes),
                "retrieved_at": now(),
                "required": True,
                "status": "collected",
                "error": "",
                "parent_asset_id": asset["asset_id"],
            }
            new_assets.append(text_asset)

        result_ok = ok and bool(markers)
        results.append(
            {
                "year": year,
                "ok": result_ok,
                "pdf_asset_id": asset["asset_id"],
                "pdf_path": asset["local_path"],
                "parsed_text_path": text_path.relative_to(ROOT).as_posix() if ok else "",
                "reference_markers": markers,
                "error": error if not ok else ("" if markers else "no reference-book marker found"),
            }
        )
        all_ok = all_ok and result_ok

    inventory["assets"] = inventory.get("assets", []) + new_assets
    inventory["generated_at"] = now()
    INVENTORY.write_text(json.dumps(inventory, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    payload = {"ok": all_ok, "generated_at": now(), "results": results}
    REFERENCE_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    lines = [
        "# 合肥师范学院考试大纲与参考书目核验",
        "",
        f"> 结果：{'PASS' if all_ok else 'FAIL'}",
        f"> 生成时间：{payload['generated_at']}",
        "",
        "| 年份 | 大纲 PDF | 解析文本 | 参考书目标记 | 结果 |",
        "|---:|---|---|---|---:|",
    ]
    for item in results:
        lines.append(
            f"| {item['year']} | `{item.get('pdf_path', '')}` | "
            f"`{item.get('parsed_text_path', '')}` | "
            f"{', '.join(item.get('reference_markers', [])) or item.get('error', '')} | "
            f"{'PASS' if item['ok'] else 'FAIL'} |"
        )
    REFERENCE_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")

    report = json.loads(REPORT_JSON.read_text(encoding="utf-8"))
    report["reference_books_check"] = payload
    report["asset_count"] = len(inventory["assets"])
    report["collected_count"] = sum(item.get("status") == "collected" for item in inventory["assets"])
    report["ok"] = bool(report.get("ok")) and all_ok
    REPORT_JSON.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    with REPORT_MD.open("a", encoding="utf-8") as handle:
        handle.write("\n## HFNU 参考书目核验\n\n")
        for item in results:
            handle.write(f"- {item['year']}：{'PASS' if item['ok'] else 'FAIL'}，标记：{', '.join(item.get('reference_markers', [])) or item.get('error', '')}\n")
    return all_ok


def main() -> int:
    cleanup_previous_assets()
    remap_paths()
    base.discovered = discovered_without_duplicates
    collection_status = base.main()
    reference_ok = verify_reference_books() if INVENTORY.is_file() else False
    return 0 if collection_status == 0 and reference_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
