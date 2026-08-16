#!/usr/bin/env python3
"""Sanitize BZU raw evidence after acquisition.

The sanitizer never promotes a discovery lead to formal evidence. It removes formal
items that violate candidate-privacy policy, official-domain policy, local-byte
integrity, or strict 2024-2026 year binding, and then rebuilds the 84-cell coverage
matrix from the surviving original files.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import re
import zipfile
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from bs4 import BeautifulSoup
from pypdf import PdfReader

SCHOOL_ID = "BZU"
SCHOOL_NAME = "亳州学院"
YEARS = (2024, 2025, 2026)
DOMAIN = "bzuu.edu.cn"
ROOT = Path("anhui_zsb_data/evidence/full_raw_30_schools/BZU")
REPORT = Path("anhui_zsb_data/reports/p0_batch_02_bzu_sanitization_audit.md")

PRIVACY_KEYWORDS = [
    "拟录取名单", "预录取名单", "录取名单", "考生名单", "面试名单",
    "审核名单", "资格审查名单", "免试名单", "成绩名单", "成绩查询",
    "录取查询", "考生成绩", "考生号", "准考证号", "身份证号",
    "姓名准考证", "姓名考生号", "联系电话身份证",
]
PERSONAL_NUMBER_PATTERNS = [
    re.compile(r"(?<!\d)\d{17}[0-9Xx](?!\d)"),
    re.compile(r"(?<!\d)\d{12,16}(?!\d)"),
]
TOPICS = [
    "admission_policy", "enrollment_plan", "major_catalog", "training_location",
    "tuition_and_duration", "eligibility", "exam_subjects", "exam_syllabus",
    "reference_books", "exam_schedule", "exam_location", "admission_rules",
    "score_formula", "control_line", "admission_min_score", "admission_max_score",
    "admission_average_score", "application_statistics", "qualified_statistics",
    "admitted_statistics", "registered_statistics", "plan_adjustment", "adjustment",
    "exemption", "retired_soldier", "registered_poor_family", "skill_competition",
    "other_official_notice",
]


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def compact(value: str) -> str:
    return re.sub(r"\s+", "", value or "")


def allowed_domain(value: str) -> bool:
    host = (value or "").lower().strip()
    return host == DOMAIN or host.endswith("." + DOMAIN)


def extract_pdf(data: bytes) -> str:
    reader = PdfReader(io.BytesIO(data))
    chunks: list[str] = []
    length = 0
    for page in reader.pages[:80]:
        try:
            text = page.extract_text() or ""
        except Exception:
            text = ""
        chunks.append(text)
        length += len(text)
        if length >= 300_000:
            break
    return "\n".join(chunks)


def extract_zip_xml(data: bytes) -> str:
    chunks: list[str] = []
    total = 0
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        for name in archive.namelist():
            lower = name.lower()
            if not lower.endswith((".xml", ".rels", ".txt", ".csv")):
                continue
            if total >= 20 * 1024 * 1024:
                break
            try:
                raw = archive.read(name)
            except Exception:
                continue
            total += len(raw)
            decoded = decode_text(raw)
            if lower.endswith((".xml", ".rels")):
                decoded = BeautifulSoup(decoded, "xml").get_text(" ", strip=True)
            chunks.append(decoded)
    return "\n".join(chunks)


def decode_text(data: bytes) -> str:
    for encoding in ("utf-8", "gb18030", "utf-16", "utf-16le", "utf-16be"):
        try:
            return data.decode(encoding)
        except (UnicodeDecodeError, LookupError):
            continue
    return data.decode("latin1", "replace")


def extract_text(path: Path, data: bytes) -> str:
    suffix = path.suffix.lower()
    if suffix in {".html", ".htm", ".xhtml"}:
        return BeautifulSoup(decode_text(data), "html.parser").get_text(" ", strip=True)
    if suffix == ".pdf":
        try:
            return extract_pdf(data)
        except Exception:
            return ""
    if suffix in {".docx", ".xlsx", ".pptx", ".zip"}:
        try:
            return extract_zip_xml(data)
        except Exception:
            return ""
    return decode_text(data[:5_000_000])


def privacy_reason(value: str) -> str | None:
    normalized = compact(value)
    keyword = next((item for item in PRIVACY_KEYWORDS if item in normalized), None)
    if keyword:
        return f"privacy_keyword:{keyword}"
    for pattern in PERSONAL_NUMBER_PATTERNS:
        if pattern.search(normalized):
            nearby = any(marker in normalized for marker in ("姓名", "考生", "身份证", "准考证", "联系电话"))
            if nearby:
                return f"personal_identifier_pattern:{pattern.pattern}"
    return None


def years_in(value: str) -> set[int]:
    normalized = compact(value)
    return {year for year in YEARS if str(year) in normalized}


def item_topics(item: dict) -> list[str]:
    value = item.get("topics") or ""
    if isinstance(value, list):
        result = [str(topic) for topic in value]
    else:
        result = [topic for topic in str(value).split("|") if topic]
    return [topic for topic in result if topic in TOPICS]


def parsed_companion(path: Path) -> Path:
    return path.with_name(path.stem + "_parsed.txt")


def main() -> int:
    manifest_path = ROOT / "school_manifest.json"
    coverage_path = ROOT / "school_coverage.csv"
    if not manifest_path.is_file() or not coverage_path.is_file():
        raise SystemExit("BZU manifest and coverage must exist before sanitization")

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    rows = list(csv.DictReader(coverage_path.open(encoding="utf-8-sig")))
    if len(rows) != 84:
        raise SystemExit(f"Expected 84 coverage rows, got {len(rows)}")

    privacy_exclusions = list(manifest.get("privacy_exclusions") or [])
    failures = list(manifest.get("failures") or [])
    discovery = list(manifest.get("discovery") or [])
    removed: list[dict] = []
    keep_sources: list[dict] = []
    keep_assets: list[dict] = []
    retained_paths: set[Path] = set()
    pending_delete: set[Path] = set()

    def inspect(item: dict, kind: str) -> tuple[bool, dict | None]:
        year = int(item.get("year") or 0)
        topics = item_topics(item)
        path = Path(str(item.get("local_path") or ""))
        metadata_text = " ".join(
            str(item.get(key) or "")
            for key in ("title", "official_url", "final_url", "parent_page_url", "notes")
        )
        record = {
            "school_id": SCHOOL_ID,
            "school_name": SCHOOL_NAME,
            "year": year or None,
            "topics": topics,
            "kind": kind,
            "official_url": item.get("official_url"),
            "final_url": item.get("final_url"),
            "local_path": str(path),
            "sanitized_at": now(),
        }

        if year not in YEARS:
            return False, {**record, "reason": "invalid_year"}
        if not topics:
            return False, {**record, "reason": "empty_or_unknown_topics"}
        if item.get("status") != "collected":
            return False, {**record, "reason": "formal_item_not_collected"}
        domain = str(item.get("official_domain") or urlparse(str(item.get("final_url") or "")).hostname or "")
        if not allowed_domain(domain):
            return False, {**record, "reason": f"official_domain_violation:{domain}"}
        if not path.is_file():
            return False, {**record, "reason": "local_file_missing"}

        data = path.read_bytes()
        if len(data) != int(item.get("file_size") or -1):
            return False, {**record, "reason": "file_size_mismatch"}
        if sha256(data) != item.get("sha256"):
            return False, {**record, "reason": "sha256_mismatch"}

        extracted = extract_text(path, data)
        companion = parsed_companion(path)
        if companion.is_file():
            try:
                extracted += "\n" + companion.read_text(encoding="utf-8", errors="replace")
            except Exception:
                pass
        combined = metadata_text + "\n" + extracted

        reason = privacy_reason(combined)
        if reason:
            return False, {**record, "reason": reason, "classification": "candidate_personal_data_excluded"}

        content_years = years_in(extracted)
        metadata_years = years_in(metadata_text)
        if len(content_years) == 1:
            bound_year = next(iter(content_years))
            if bound_year != year:
                return False, {
                    **record, "reason": f"strict_year_mismatch:content={bound_year}:manifest={year}",
                    "classification": "awaiting_manual_review",
                }
        elif len(content_years) > 1:
            return False, {
                **record, "reason": f"cross_year_content:{sorted(content_years)}",
                "classification": "awaiting_manual_review",
            }
        else:
            if metadata_years != {year}:
                return False, {
                    **record,
                    "reason": f"strict_year_unbound:metadata_years={sorted(metadata_years)}:manifest={year}",
                    "classification": "awaiting_manual_review",
                }

        item["sanitized"] = True
        item["sanitized_at"] = now()
        item["content_years"] = sorted(content_years)
        item["privacy_scan"] = "passed"
        item["integrity_scan"] = "passed"
        return True, None

    for kind, values, target in (
        ("source", list(manifest.get("sources") or []), keep_sources),
        ("asset", list(manifest.get("assets") or []), keep_assets),
    ):
        for item in values:
            ok, record = inspect(item, kind)
            path = Path(str(item.get("local_path") or ""))
            if ok:
                target.append(item)
                retained_paths.add(path)
            else:
                assert record is not None
                removed.append(record)
                pending_delete.add(path)
                companion = parsed_companion(path)
                if companion.exists():
                    pending_delete.add(companion)
                if record.get("classification") == "candidate_personal_data_excluded":
                    privacy_exclusions.append(record)
                else:
                    discovery.append({**record, "status": record.get("classification", "awaiting_manual_review")})

    # Cross-year identical bytes cannot be independently bound unless the content itself
    # validates each year, which is impossible for one immutable byte sequence here.
    by_sha: dict[str, list[tuple[str, dict]]] = defaultdict(list)
    for kind, values in (("source", keep_sources), ("asset", keep_assets)):
        for item in values:
            by_sha[str(item.get("sha256") or "")].append((kind, item))
    cross_year_paths: set[Path] = set()
    for digest_value, grouped in by_sha.items():
        grouped_years = {int(item["year"]) for _, item in grouped}
        if digest_value and len(grouped_years) > 1:
            for kind, item in grouped:
                record = {
                    "school_id": SCHOOL_ID, "school_name": SCHOOL_NAME,
                    "year": int(item["year"]), "topics": item_topics(item), "kind": kind,
                    "official_url": item.get("official_url"), "final_url": item.get("final_url"),
                    "local_path": item.get("local_path"), "sha256": digest_value,
                    "reason": f"cross_year_duplicate_sha:{sorted(grouped_years)}",
                    "classification": "awaiting_manual_review", "sanitized_at": now(),
                }
                removed.append(record)
                discovery.append({**record, "status": "awaiting_manual_review"})
                cross_year_paths.add(Path(item["local_path"]))

    if cross_year_paths:
        keep_sources = [item for item in keep_sources if Path(item["local_path"]) not in cross_year_paths]
        keep_assets = [item for item in keep_assets if Path(item["local_path"]) not in cross_year_paths]
        retained_paths = {Path(item["local_path"]) for item in keep_sources + keep_assets}
        pending_delete.update(cross_year_paths)

    for path in sorted(pending_delete):
        if path in retained_paths:
            continue
        try:
            path.unlink(missing_ok=True)
        except OSError as exc:
            failures.append({
                "school_id": SCHOOL_ID, "school_name": SCHOOL_NAME,
                "url": "", "parent_url": "", "status": "awaiting_manual_review",
                "reason": f"sanitizer_delete_failed:{path}:{exc!r}", "retrieved_at": now(),
            })

    # Rebuild the coverage matrix from surviving formal evidence. Existing non-collected
    # states remain truthful, but a removed item can no longer leave a false collected cell.
    statuses = {(int(row["year"]), row["topic"]): row["status"] for row in rows}
    for key, status in list(statuses.items()):
        if status == "collected":
            statuses[key] = "awaiting_manual_review"

    for record in removed:
        year = record.get("year")
        classification = record.get("classification") or "awaiting_manual_review"
        if year in YEARS:
            for topic in record.get("topics") or []:
                statuses[(year, topic)] = classification

    for item in keep_sources + keep_assets:
        year = int(item["year"])
        for topic in item_topics(item):
            statuses[(year, topic)] = "collected"

    with coverage_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["school_id", "school_name", "year", "topic", "status"])
        for year in YEARS:
            for topic in TOPICS:
                writer.writerow([SCHOOL_ID, SCHOOL_NAME, year, topic, statuses[(year, topic)]])

    manifest.update({
        "sources": keep_sources,
        "assets": keep_assets,
        "failures": failures,
        "privacy_exclusions": privacy_exclusions,
        "discovery": discovery,
        "sanitized": True,
        "sanitized_at": now(),
        "sanitization_removed": removed,
    })
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (ROOT / "source_discovery.json").write_text(
        json.dumps({
            "school_id": SCHOOL_ID,
            "entries": discovery,
            "privacy_exclusions": privacy_exclusions,
            "sanitization_removed": removed,
        }, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    counts = Counter(statuses.values())
    surviving = keep_sources + keep_assets
    total_bytes = sum(int(item["file_size"]) for item in surviving)
    lines = [
        "# BZU P0 原始证据净化审计", "",
        f"- 生成时间：{now()}",
        f"- 净化前正式证据：{len(list(manifest.get('sources') or [])) + len(list(manifest.get('assets') or [])) + len(removed)}",
        f"- 净化后正式证据：{len(surviving)}",
        f"- 净化后原始字节：{total_bytes}",
        f"- 本轮移除：{len(removed)}",
        f"- 隐私排除累计：{len(privacy_exclusions)}", "",
        "## Coverage 状态", "",
    ]
    lines.extend(f"- `{status}`：{count}" for status, count in sorted(counts.items()))
    lines.extend(["", "## 移除明细", ""])
    if removed:
        for record in removed:
            lines.append(
                f"- {record.get('year')} / {','.join(record.get('topics') or []) or '-'} / "
                f"`{record.get('reason')}` / `{record.get('local_path')}`"
            )
    else:
        lines.append("- 无")
    lines.extend(["", "所有保留的正式证据均通过官方域名、原始文件、长度、SHA-256、隐私和严格年份绑定检查。", ""])
    REPORT.write_text("\n".join(lines), encoding="utf-8")

    result = {
        "school_id": SCHOOL_ID,
        "surviving_sources": len(keep_sources),
        "surviving_assets": len(keep_assets),
        "surviving_bytes": total_bytes,
        "removed": len(removed),
        "coverage": dict(sorted(counts.items())),
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
