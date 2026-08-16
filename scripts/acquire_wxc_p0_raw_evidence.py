#!/usr/bin/env python3
"""Targeted raw-evidence acquisition for WXC (皖西学院), 2024-2026.

The script archives only publicly accessible official pages/files from the school or
Anhui Provincial Education Admissions Examination Authority. Search-engine and
third-party pages are recorded as discovery clues only; their bytes are not stored.
Official public documents are preserved byte-for-byte, including publicly released
candidate-level records when encountered. No authentication or access control is
bypassed.
"""
from __future__ import annotations

import csv
import hashlib
import json
import os
import re
import subprocess
import tempfile
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urljoin, urlparse

from bs4 import BeautifulSoup

SCHOOL_ID = "WXC"
SCHOOL_NAME = "皖西学院"
YEARS = (2024, 2025, 2026)
ROOT = Path("anhui_zsb_data/evidence/full_raw_30_schools/WXC")
REPORT_PATH = Path("anhui_zsb_data/reports/wxc_p0_raw_evidence_batch_01.md")
ROOT.mkdir(parents=True, exist_ok=True)
REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)

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

TOPIC_KW = {
    "admission_policy": ["招生章程", "招生简章", "实施办法"],
    "enrollment_plan": ["招生计划", "拟招生方案", "招生方案"],
    "major_catalog": ["招生专业", "专业范围", "报考专业范围", "专业对照"],
    "training_location": ["联合培养", "培养地点", "培养校区"],
    "tuition_and_duration": ["学费", "学制", "住宿费"],
    "eligibility": ["报名条件", "报考条件", "资格审核", "报名资格"],
    "exam_subjects": ["考试科目", "专业课", "公共课"],
    "exam_syllabus": ["考试大纲", "测试大纲", "考查大纲"],
    "reference_books": ["参考书目", "参考教材"],
    "exam_schedule": ["考试时间", "考试安排", "面试时间", "考查时间"],
    "exam_location": ["考试地点", "考点", "考场"],
    "admission_rules": ["录取规则", "录取细则", "同分排序", "择优录取"],
    "score_formula": ["成绩计算", "综合成绩", "总成绩", "计分公式"],
    "control_line": ["合格线", "控制线", "专业课合格"],
    "admission_min_score": ["最低录取分", "最低投档分", "录取分数线", "预录取分数线"],
    "admission_max_score": ["最高录取分", "录取最高分"],
    "admission_average_score": ["平均录取分", "录取平均分"],
    "application_statistics": ["报名人数", "报考人数", "志愿人数"],
    "qualified_statistics": ["资格审核通过人数", "资格通过人数", "合格人数"],
    "admitted_statistics": ["录取人数", "录取统计"],
    "registered_statistics": ["报到人数", "注册人数"],
    "plan_adjustment": ["计划调整", "调整计划", "扩招", "缩招"],
    "adjustment": ["调剂", "征集志愿", "补录", "缺额计划"],
    "exemption": ["免试", "免文化课"],
    "retired_soldier": ["退役大学生士兵", "退役士兵"],
    "registered_poor_family": ["建档立卡"],
    "skill_competition": ["技能大赛", "职业技能大赛"],
    "other_official_notice": ["专升本"],
}

CANDIDATE_TERMS = [
    "拟录取名单", "预录取名单", "录取名单", "考生名单", "面试名单",
    "成绩名单", "考生号", "准考证号", "身份证号", "姓名", "成绩",
]

OFFICIAL_DOMAINS = ("wxc.edu.cn", "ahzsks.cn")
ATTACHMENT_EXTS = {".pdf", ".doc", ".docx", ".xls", ".xlsx", ".csv", ".zip", ".jpg", ".jpeg", ".png", ".tif", ".tiff"}
HTML_EXTS = {"", ".htm", ".html", ".shtml", ".asp", ".aspx", ".php"}
MAX_CRAWL_PAGES = int(os.environ.get("WXC_MAX_CRAWL_PAGES", "90"))
MAX_DEPTH = int(os.environ.get("WXC_MAX_CRAWL_DEPTH", "3"))
MAX_BYTES = 100 * 1024 * 1024
USER_AGENT = "Mozilla/5.0 (compatible; AnhuiZSBDataResearch/2.0; official-public-archive)"

# Exact official URLs located through discovery research. Third-party discovery pages
# are listed only in metadata notes and are never downloaded into the evidence archive.
KNOWN_DOCUMENTS: list[dict[str, Any]] = [
    {
        "year": 2024,
        "url": "https://zsb.wxc.edu.cn/2024/0312/c270a183191/page.htm",
        "title": "2024年皖西学院普通专升本拟招生专业考试科目、考试大纲及参考书目的通知",
        "topics": ["major_catalog", "exam_subjects", "exam_syllabus", "reference_books", "other_official_notice"],
        "discovery_url": "https://www.hlsok.com/ah/news/64788.html",
    },
    {
        "year": 2025,
        "url": "https://www.ahzsks.cn/zyyx/8108.htm",
        "title": "皖西学院2025年普通高校专升本招生章程",
        "topics": None,
        "discovery_url": "https://zsb.xdf.cn/202512/15059491.html",
    },
    {
        "year": 2025,
        "url": "https://zsb.wxc.edu.cn/_upload/article/files/61/dc/c7c861c34e73a0b4a234a93c7f94/3b31146a-9b4a-4995-ba14-ab7eadc8c7c1.pdf",
        "title": "皖西学院2025年专升本考试大纲（专业课）",
        "topics": ["exam_subjects", "exam_syllabus", "reference_books"],
        "discovery_url": "https://www.hlsok.com/ah/news/68751.html",
    },
    {
        "year": 2025,
        "url": "https://zsb.wxc.edu.cn/_upload/article/files/61/dc/c7c861c34e73a0b4a234a93c7f94/e4b3b43c-f1b7-4124-ba75-502aca08422d.pdf",
        "title": "2025年皖西学院专升本招生专业考试科目及参考书目",
        "topics": ["major_catalog", "training_location", "exam_subjects", "reference_books"],
        "discovery_url": "https://www.hlsok.com/ah/news/68751.html",
    },
    {
        "year": 2026,
        "url": "https://zsb.wxc.edu.cn/_upload/article/files/8b/4f/53caeb5d4bb18157fd3e1db9625d/40a7ba02-ea56-4257-b910-508297c2d7f6.pdf",
        "title": "皖西学院2026年专升本考试大纲（专业课）",
        "topics": ["exam_subjects", "exam_syllabus", "reference_books"],
        "discovery_url": "https://www.hlsok.com/news/75297.html",
    },
    {
        "year": 2026,
        "url": "https://zsb.wxc.edu.cn/_upload/article/files/8b/4f/53caeb5d4bb18157fd3e1db9625d/aaee6026-93bb-4c9c-b085-0ea8486d84e4.pdf",
        "title": "2026年皖西学院专升本招生专业考试科目及参考书目",
        "topics": ["major_catalog", "training_location", "exam_subjects", "reference_books"],
        "discovery_url": "https://www.hlsok.com/news/75297.html",
    },
]

CRAWL_SEEDS = [
    "https://zsb.wxc.edu.cn/",
    "http://zsb.wxc.edu.cn/",
    "https://zsb.wxc.edu.cn/270/list.htm",
    "https://zsb.wxc.edu.cn/zsxx/list.htm",
    "https://www.wxc.edu.cn/",
    "https://www.ahzsks.cn/zyyx/",
]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def short_id(value: str) -> str:
    return hashlib.sha1(value.encode("utf-8", "replace")).hexdigest()[:10]


def compact(text: str) -> str:
    return re.sub(r"\s+", "", text or "")


def allowed(url: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    return any(host == d or host.endswith("." + d) for d in OFFICIAL_DOMAINS)


def source_level(url: str) -> str:
    host = (urlparse(url).hostname or "").lower()
    return "province_official" if host == "ahzsks.cn" or host.endswith(".ahzsks.cn") else "school_official"


def infer_year(text: str) -> int | None:
    found = {y for y in YEARS if str(y) in text}
    return next(iter(found)) if len(found) == 1 else None


def infer_topics(text: str) -> list[str]:
    norm = compact(text)
    result = [topic for topic, keywords in TOPIC_KW.items() if any(k in norm for k in keywords)]
    if "专升本" in norm and "other_official_notice" not in result:
        result.append("other_official_notice")
    return [t for t in TOPICS if t in result]


def primary_topic(topics: list[str]) -> str:
    for topic in TOPICS:
        if topic in topics and topic != "other_official_notice":
            return topic
    return "other_official_notice"


def topic_dir(topic: str) -> str:
    if topic == "admission_policy":
        return "admission_policy"
    if topic in {"enrollment_plan", "major_catalog", "training_location", "tuition_and_duration", "eligibility"}:
        return "enrollment_plan"
    if topic in {"exam_subjects", "exam_syllabus", "reference_books", "exam_schedule", "exam_location"}:
        return "exam_syllabus"
    if topic in {"admission_rules", "score_formula", "control_line", "admission_min_score", "admission_max_score", "admission_average_score"}:
        return "admission_scores"
    if topic in {"application_statistics", "qualified_statistics", "admitted_statistics", "registered_statistics"}:
        return "statistics"
    if topic in {"plan_adjustment", "adjustment"}:
        return "adjustments"
    return "other"


def parse_headers(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    text = path.read_text("latin-1", errors="replace")
    blocks = re.split(r"\r?\n\r?\n", text.strip())
    block = blocks[-1] if blocks else text
    headers: dict[str, str] = {}
    for line in block.splitlines()[1:]:
        if ":" in line:
            key, value = line.split(":", 1)
            headers[key.strip().lower()] = value.strip()
    return headers


def fetch(url: str) -> tuple[bytes | None, dict[str, Any]]:
    """Download public bytes with curl; never supplies credentials or bypasses controls."""
    attempts = [(["-4"], True), ([], True), (["-4", "--insecure"], False), (["--insecure"], False)]
    last: dict[str, Any] = {"url": url, "error": "not attempted"}
    with tempfile.TemporaryDirectory(prefix="wxc-fetch-") as temp:
        tmp = Path(temp)
        for extra, tls_verified in attempts:
            body = tmp / "body.bin"
            headers_path = tmp / "headers.txt"
            body.unlink(missing_ok=True)
            headers_path.unlink(missing_ok=True)
            cmd = [
                "curl", "--silent", "--show-error", "--location", "--compressed",
                "--retry", "3", "--retry-delay", "1", "--retry-all-errors",
                "--connect-timeout", "20", "--max-time", "150",
                "--user-agent", USER_AGENT,
                "--header", "Accept: text/html,application/xhtml+xml,application/pdf,application/octet-stream,*/*;q=0.8",
                "--header", "Accept-Language: zh-CN,zh;q=0.9,en;q=0.5",
                "--referer", "https://zsb.wxc.edu.cn/",
                "--dump-header", str(headers_path), "--output", str(body),
                "--write-out", "%{http_code}\n%{url_effective}\n%{content_type}\n",
                *extra, url,
            ]
            proc = subprocess.run(cmd, text=True, capture_output=True, check=False)
            lines = proc.stdout.strip().splitlines()
            code = int(lines[-3]) if len(lines) >= 3 and lines[-3].isdigit() else 0
            effective = lines[-2] if len(lines) >= 2 else url
            content_type = lines[-1] if lines else ""
            headers = parse_headers(headers_path)
            size = body.stat().st_size if body.exists() else 0
            last = {
                "url": url, "http_status": code or "error", "final_url": effective,
                "content_type": content_type or headers.get("content-type", ""),
                "content_disposition": headers.get("content-disposition", ""),
                "tls_verified": tls_verified, "curl_returncode": proc.returncode,
                "stderr": proc.stderr.strip(), "file_size": size,
            }
            if code in range(200, 400) and body.exists() and 0 < size <= MAX_BYTES:
                data = body.read_bytes()
                last["sha256"] = digest(data)
                return data, last
            if size > MAX_BYTES:
                last["error"] = f"file exceeds {MAX_BYTES} bytes"
                return None, last
    return None, last


def extension_for(url: str, content_type: str, data: bytes) -> str:
    ext = Path(unquote(urlparse(url).path)).suffix.lower()
    ctype = (content_type or "").lower()
    if data.startswith(b"%PDF-"):
        return ".pdf"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png"
    if data.startswith(b"\xff\xd8\xff"):
        return ".jpg"
    if data.startswith(b"PK\x03\x04") and ext in {".docx", ".xlsx", ".zip"}:
        return ext
    if data.startswith(b"\xd0\xcf\x11\xe0") and ext in {".doc", ".xls"}:
        return ext
    if ext in ATTACHMENT_EXTS:
        return ext
    if "html" in ctype or ext in HTML_EXTS:
        return ".html"
    if "pdf" in ctype:
        return ".pdf"
    return ext if ext else ".bin"


def decode_html(data: bytes) -> str:
    for encoding in ("utf-8", "gb18030", "gbk"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            pass
    return data.decode("utf-8", errors="replace")


def page_info(data: bytes) -> tuple[BeautifulSoup, str, str, str]:
    html_text = decode_html(data)
    soup = BeautifulSoup(html_text, "html.parser")
    title = compact(soup.title.get_text(" ", strip=True) if soup.title else "")
    text = soup.get_text("\n", strip=True)
    date_match = re.search(r"(?<!\d)(20(?:24|25|26))[-年/.](\d{1,2})[-月/.](\d{1,2})日?", text[:10000])
    publish_date = ""
    if date_match:
        publish_date = f"{date_match.group(1)}-{int(date_match.group(2)):02d}-{int(date_match.group(3)):02d}"
    return soup, title, text, publish_date


def candidate_status(text: str) -> str:
    norm = compact(text)
    return "public_official_record" if any(term in norm for term in CANDIDATE_TERMS) else "collected"


def existing_raw_files() -> set[Path]:
    result: set[Path] = set()
    for path in ROOT.rglob("*"):
        if not path.is_file():
            continue
        if path.name in {"school_manifest.json", "school_coverage.csv", "school_notes.md"} or path.name.endswith("_parsed.txt"):
            continue
        result.add(path)
    return result


manifest_path = ROOT / "school_manifest.json"
if manifest_path.exists():
    manifest = json.loads(manifest_path.read_text("utf-8-sig"))
else:
    manifest = {"school_id": SCHOOL_ID, "school_name": SCHOOL_NAME, "sources": [], "assets": [], "failures": []}

old_sources = list(manifest.get("sources", []))
old_assets = list(manifest.get("assets", []))
old_failures = list(manifest.get("failures", []))
old_by_key: dict[tuple[int, str], dict[str, Any]] = {}
for item in old_sources + old_assets:
    try:
        old_by_key[(int(item.get("year")), item.get("official_url") or item.get("attachment_url") or "")] = item
    except (TypeError, ValueError):
        continue

sources_by_key = {(int(x.get("year", 0)), x.get("official_url", "")): x for x in old_sources if x.get("official_url")}
assets_by_key = {(int(x.get("year", 0)), x.get("attachment_url") or x.get("official_url", "")): x for x in old_assets if x.get("attachment_url") or x.get("official_url")}
failures: list[dict[str, Any]] = old_failures.copy()
fetch_cache: dict[str, tuple[bytes | None, dict[str, Any]]] = {}
success_urls: set[str] = set()
discovered_urls: set[str] = set()
before_raw = existing_raw_files()


def get_cached(url: str) -> tuple[bytes | None, dict[str, Any]]:
    if url not in fetch_cache:
        fetch_cache[url] = fetch(url)
    return fetch_cache[url]


def add_failure(year: int | None, url: str, status: str, reason: str, meta: dict[str, Any] | None = None, parent_url: str = "") -> None:
    item = {
        "school_id": SCHOOL_ID, "school_name": SCHOOL_NAME, "year": year,
        "url": url, "parent_url": parent_url, "status": status,
        "http_status": (meta or {}).get("http_status", "error"),
        "reason": reason[:1200], "checked_at": utc_now(),
    }
    key = (item["year"], item["url"], item["status"], item["reason"])
    if not any((f.get("year"), f.get("url"), f.get("status"), f.get("reason")) == key for f in failures):
        failures.append(item)


def save_official_document(
    *, year: int, url: str, data: bytes, meta: dict[str, Any], title: str,
    topics: list[str], parent_page_url: str = "", publish_date: str = "",
    discovery_url: str = "", page_text: str = "",
) -> tuple[dict[str, Any], BeautifulSoup | None]:
    final_url = meta.get("final_url") or url
    ext = extension_for(final_url, meta.get("content_type", ""), data)
    is_html = ext == ".html"
    soup: BeautifulSoup | None = None
    parsed_text = page_text
    if is_html:
        soup, parsed_title, parsed_text, parsed_date = page_info(data)
        title = title or parsed_title or f"皖西学院{year}年专升本官方页面"
        publish_date = publish_date or parsed_date
        if "专升本" not in compact(title + parsed_text[:20000]):
            raise ValueError("downloaded HTML is not a relevant 专升本 document")
    if not topics:
        topics = infer_topics(title + "\n" + parsed_text[:50000])
    topics = [t for t in TOPICS if t in set(topics)] or ["other_official_notice"]
    ptopic = primary_topic(topics)
    folder = ROOT / str(year) / topic_dir(ptopic)
    folder.mkdir(parents=True, exist_ok=True)
    base = f"DOC-{SCHOOL_ID}-{year}-{ptopic}-{short_id(url)}"
    local = folder / f"{base}{ext}"
    file_hash = digest(data)
    if not local.exists() or digest(local.read_bytes()) != file_hash:
        local.write_bytes(data)
    if is_html:
        parsed_path = folder / f"{base}_parsed.txt"
        parsed_payload = f"Title: {title}\nOfficial URL: {url}\nFinal URL: {final_url}\nPublish date: {publish_date}\n\n{parsed_text}\n"
        parsed_path.write_text(parsed_payload, "utf-8")

    old = old_by_key.get((year, url), {})
    retrieved_at = old.get("retrieved_at") if old.get("sha256") == file_hash else utc_now()
    notes = []
    if discovery_url:
        notes.append(f"official URL discovered via {discovery_url}; discovery page bytes not archived")
    if not meta.get("tls_verified", True):
        notes.append("official server fetched with TLS certificate verification disabled after verified attempts failed")
    status = candidate_status(title + "\n" + parsed_text[:50000])
    common = {
        "school_id": SCHOOL_ID, "school_name": SCHOOL_NAME, "year": year,
        "title": title, "publish_date": publish_date, "retrieved_at": retrieved_at,
        "official_page_url": url if is_html else (parent_page_url or url),
        "official_url": url, "final_url": final_url,
        "source_domain": urlparse(final_url).hostname or urlparse(url).hostname or "",
        "official_domain": urlparse(final_url).hostname or urlparse(url).hostname or "",
        "source_level": source_level(final_url), "document_type": "html" if is_html else "attachment",
        "topics": "|".join(topics), "file_type": ext.lstrip("."),
        "local_path": local.as_posix(), "file_size": len(data), "sha256": file_hash,
        "http_status": meta.get("http_status", 200), "content_type": meta.get("content_type", ""),
        "status": status, "notes": "; ".join(notes),
    }
    if is_html:
        common["source_id"] = f"SRC-{SCHOOL_ID}-{year}-{short_id(url)}"
        common["parent_page_url"] = parent_page_url
        sources_by_key[(year, url)] = common
    else:
        common.update({
            "asset_id": f"AST-{SCHOOL_ID}-{year}-{short_id(url)}",
            "parent_page": parent_page_url,
            "parent_page_url": parent_page_url,
            "attachment_url": url,
            "attachment_filename": Path(unquote(urlparse(final_url).path)).name or local.name,
            "attachment_sha256": file_hash,
        })
        assets_by_key[(year, url)] = common
    success_urls.add(url)
    return common, soup


def archive_url(spec: dict[str, Any], parent_page_url: str = "") -> BeautifulSoup | None:
    url = spec["url"]
    year = int(spec["year"])
    data, meta = get_cached(url)
    if data is None:
        code = meta.get("http_status")
        status = "access_restricted" if code in {401, 403, 407, 429, "error", 0} else "removed_or_unavailable"
        add_failure(year, url, status, meta.get("stderr") or meta.get("error") or f"HTTP {code}", meta, parent_page_url)
        return None
    try:
        entry, soup = save_official_document(
            year=year, url=url, data=data, meta=meta, title=spec.get("title", ""),
            topics=spec.get("topics") or [], parent_page_url=parent_page_url,
            discovery_url=spec.get("discovery_url", ""),
        )
        print(f"COLLECTED {year} {entry['file_type']} {url} -> {entry['local_path']}")
        return soup
    except Exception as exc:
        add_failure(year, url, "awaiting_manual_review", repr(exc), meta, parent_page_url)
        return None


def should_queue(link: str, anchor: str, depth: int) -> bool:
    if depth > MAX_DEPTH or not allowed(link):
        return False
    parsed = urlparse(link)
    ext = Path(unquote(parsed.path)).suffix.lower()
    if ext in ATTACHMENT_EXTS:
        return False
    token = compact(anchor + " " + link)
    if "专升本" in token or any(str(y) in token for y in YEARS):
        return True
    if "ahzsks.cn" in (parsed.hostname or "") and ("zyyx" in parsed.path or parsed.path.endswith("/")):
        return True
    if "wxc.edu.cn" in (parsed.hostname or "") and any(x in parsed.path for x in ("list", "c270", "zsb", "zsxx")):
        return True
    return False


def crawl() -> None:
    queue: deque[tuple[str, int, str]] = deque((url, 0, "") for url in CRAWL_SEEDS)
    seen: set[str] = set()
    pages = 0
    while queue and pages < MAX_CRAWL_PAGES:
        url, depth, parent = queue.popleft()
        url = url.split("#", 1)[0]
        if url in seen or not allowed(url):
            continue
        seen.add(url)
        data, meta = get_cached(url)
        pages += 1
        if data is None:
            continue
        ext = extension_for(meta.get("final_url") or url, meta.get("content_type", ""), data)
        if ext != ".html":
            continue
        soup, title, text, publish_date = page_info(data)
        combined = title + "\n" + text[:100000] + "\n" + url
        year = infer_year(combined)
        relevant = year in YEARS and "专升本" in compact(combined)
        page_topics = infer_topics(combined) if relevant else []
        if relevant and (year, url) not in sources_by_key:
            try:
                save_official_document(
                    year=year, url=url, data=data, meta=meta, title=title,
                    topics=page_topics, parent_page_url=parent, publish_date=publish_date,
                    page_text=text,
                )
                print(f"DISCOVERED {year} HTML {url}")
            except Exception as exc:
                add_failure(year, url, "awaiting_manual_review", repr(exc), meta, parent)

        for tag in soup.find_all("a", href=True):
            anchor = tag.get_text(" ", strip=True)
            link = urljoin(meta.get("final_url") or url, tag.get("href", "")).split("#", 1)[0]
            if not link.startswith(("http://", "https://")) or not allowed(link):
                continue
            discovered_urls.add(link)
            link_ext = Path(unquote(urlparse(link).path)).suffix.lower()
            if link_ext in ATTACHMENT_EXTS or "/_upload/" in link:
                bound_year = year or infer_year(anchor + " " + link)
                if relevant and bound_year in YEARS:
                    topics = infer_topics(anchor + "\n" + title + "\n" + text[:20000])
                    archive_url({
                        "year": bound_year, "url": link,
                        "title": anchor or f"{title}附件", "topics": topics,
                        "discovery_url": "",
                    }, parent_page_url=url)
                continue
            if should_queue(link, anchor, depth + 1):
                queue.append((link, depth + 1, url))
    print(f"CRAWL pages={pages} seen={len(seen)} discovered_links={len(discovered_urls)}")


for document in KNOWN_DOCUMENTS:
    archive_url(document)

# Parse attachments from known HTML pages immediately, then perform a bounded official-site crawl.
for document in KNOWN_DOCUMENTS:
    if Path(urlparse(document["url"]).path).suffix.lower() in HTML_EXTS:
        data_meta = fetch_cache.get(document["url"])
        if not data_meta or not data_meta[0]:
            continue
        data, meta = data_meta
        if extension_for(meta.get("final_url") or document["url"], meta.get("content_type", ""), data) != ".html":
            continue
        soup, title, text, _ = page_info(data)
        for tag in soup.find_all("a", href=True):
            anchor = tag.get_text(" ", strip=True)
            link = urljoin(meta.get("final_url") or document["url"], tag["href"]).split("#", 1)[0]
            ext = Path(unquote(urlparse(link).path)).suffix.lower()
            if allowed(link) and (ext in ATTACHMENT_EXTS or "/_upload/" in link):
                archive_url({
                    "year": document["year"], "url": link,
                    "title": anchor or f"{title}附件",
                    "topics": infer_topics(anchor + "\n" + title + "\n" + text[:20000]),
                    "discovery_url": "",
                }, parent_page_url=document["url"])

crawl()

# Remove stale network failures for URLs successfully collected, but preserve all other audit history.
failures = [f for f in failures if f.get("url") not in success_urls]
unique_failures: dict[tuple[Any, ...], dict[str, Any]] = {}
for failure in failures:
    key = (failure.get("year"), failure.get("url"), failure.get("status"), failure.get("reason"))
    unique_failures[key] = failure
failures = sorted(unique_failures.values(), key=lambda x: (str(x.get("year")), x.get("url", ""), x.get("status", "")))

sources = sorted(sources_by_key.values(), key=lambda x: (int(x.get("year", 0)), x.get("official_url", "")))
assets = sorted(assets_by_key.values(), key=lambda x: (int(x.get("year", 0)), x.get("attachment_url") or x.get("official_url", "")))
manifest.update({
    "school_id": SCHOOL_ID,
    "school_name": SCHOOL_NAME,
    "official_domains": ["wxc.edu.cn", "ahzsks.cn"],
    "years_audited": list(YEARS),
    "topics_audited": TOPICS,
    "sources": sources,
    "assets": assets,
    "failures": failures,
    "discovery_sources": [
        {"url": "https://www.hlsok.com/ah/news/68751.html", "purpose": "discover 2025 school-official attachment URLs; bytes not archived"},
        {"url": "https://www.hlsok.com/news/75297.html", "purpose": "discover 2026 school-official attachment URLs; bytes not archived"},
        {"url": "https://zsb.xdf.cn/202512/15059491.html", "purpose": "discover 2025 provincial-official charter URL; bytes not archived"},
    ],
    "raw_information_policy": "preserve complete bytes of publicly accessible official records; no login, permission bypass, or cross-source personal profiling",
    "original_information_preserved": True,
    "sanitized": False,
    "last_audited_at": utc_now(),
})
manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", "utf-8")

# Update the complete 3 x 28 coverage matrix.
coverage_path = ROOT / "school_coverage.csv"
coverage: dict[tuple[int, str], str] = {(year, topic): "not_found" for year in YEARS for topic in TOPICS}
if coverage_path.exists():
    with coverage_path.open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            try:
                key = (int(row["year"]), row["topic"])
            except (KeyError, ValueError):
                continue
            if key in coverage:
                coverage[key] = row.get("status") or "not_found"
for entry in sources + assets:
    year = int(entry["year"])
    for topic in str(entry.get("topics", "")).split("|"):
        if (year, topic) in coverage:
            coverage[(year, topic)] = "collected"
with coverage_path.open("w", encoding="utf-8-sig", newline="") as handle:
    writer = csv.writer(handle, lineterminator="\n")
    writer.writerow(["school_id", "school_name", "year", "topic", "status"])
    for year in YEARS:
        for topic in TOPICS:
            writer.writerow([SCHOOL_ID, SCHOOL_NAME, year, topic, coverage[(year, topic)]])

# Build notes and the required per-batch audit report from the committed files themselves.
covered_by_year = {
    year: [topic for topic in TOPICS if coverage[(year, topic)] == "collected"]
    for year in YEARS
}
missing_by_year = {
    year: [topic for topic in TOPICS if coverage[(year, topic)] != "collected"]
    for year in YEARS
}
after_raw = existing_raw_files()
all_raw_bytes = sum(path.stat().st_size for path in after_raw)
new_raw = after_raw - before_raw
new_raw_bytes = sum(path.stat().st_size for path in new_raw)
public_records = sum(1 for item in sources + assets if item.get("status") == "public_official_record")
status_counts: dict[str, int] = {}
for failure in failures:
    status_counts[failure.get("status", "unknown")] = status_counts.get(failure.get("status", "unknown"), 0) + 1
collected_cells = sum(1 for value in coverage.values() if value == "collected")
not_found_cells = sum(1 for value in coverage.values() if value == "not_found")

notes_lines = [
    f"# {SCHOOL_NAME} ({SCHOOL_ID})", "",
    f"- Last audited at: {manifest['last_audited_at']}",
    f"- Official source pages: {len(sources)}",
    f"- Official attachment files: {len(assets)}",
    f"- Raw original files: {len(after_raw)} ({all_raw_bytes} bytes)",
    f"- Collected coverage cells: {collected_cells}/84",
    f"- Public official candidate-level records preserved: {public_records}",
    "- Policy: official public bytes are preserved as published; no login, CAPTCHA, permission control, or non-public endpoint was bypassed.",
    "- Third-party pages were used only to discover official URLs and were not stored as formal evidence.", "",
]
for year in YEARS:
    notes_lines.extend([
        f"## {year}", "",
        f"- Collected topics ({len(covered_by_year[year])}): " + (", ".join(f"`{x}`" for x in covered_by_year[year]) or "none"),
        f"- Still unresolved ({len(missing_by_year[year])}): " + (", ".join(f"`{x}`" for x in missing_by_year[year]) or "none"), "",
    ])
if failures:
    notes_lines.extend(["## Retrieval failures / manual review", ""])
    for failure in failures:
        notes_lines.append(f"- {failure.get('year')}: `{failure.get('status')}` — {failure.get('url')} — {failure.get('reason')}")
    notes_lines.append("")
(ROOT / "school_notes.md").write_text("\n".join(notes_lines), "utf-8")

report_lines = [
    "# WXC 皖西学院 P0 原始数据补采审计（Batch 01）", "",
    f"> 生成时间：{manifest['last_audited_at']}", "",
    "## 本批汇总", "",
    "| 指标 | 数值 |", "|---|---:|",
    "| 本批学校数 | 1 |",
    f"| 新增 source document 数 | {max(0, len(sources) - len(old_sources))} |",
    f"| 新增原始文件数 | {len(new_raw)} |",
    f"| 新增总字节数 | {new_raw_bytes} |",
    f"| 当前原始文件总数 | {len(after_raw)} |",
    f"| 当前原始数据总字节数 | {all_raw_bytes} |",
    f"| collected 覆盖格数 | {collected_cells} |",
    f"| 仍 not_found 数 | {not_found_cells} |",
    f"| access_restricted 数 | {status_counts.get('access_restricted', 0)} |",
    f"| manual_download_required 数 | {status_counts.get('manual_download_required', 0)} |",
    f"| 公开官方考生级资料数 | {public_records} |", "",
    "## 学校—年份审计", "",
    "| 学校 | 年份 | 已补主题 | 仍缺主题 | 下一步 |", "|---|---:|---|---|---|",
]
for year in YEARS:
    report_lines.append(
        f"| 皖西学院 | {year} | "
        + ("、".join(covered_by_year[year]) or "无")
        + " | " + ("、".join(missing_by_year[year]) or "无")
        + " | 继续深挖学校招生网、信息公开网、录取/调剂栏目及历史附件 |"
    )
report_lines.extend(["", "## 已归档正式来源", ""])
for item in sources + assets:
    report_lines.append(
        f"- {item['year']}｜{item['title']}｜`{item['status']}`｜{item.get('official_url') or item.get('attachment_url')}｜"
        f"`{item['sha256']}`｜{item['file_size']} bytes"
    )
if failures:
    report_lines.extend(["", "## 仍需处理的失败项", ""])
    for failure in failures:
        report_lines.append(f"- {failure.get('year')}｜`{failure.get('status')}`｜{failure.get('url')}｜{failure.get('reason')}")
REPORT_PATH.write_text("\n".join(report_lines) + "\n", "utf-8")

summary = {
    "school": SCHOOL_ID,
    "sources": len(sources),
    "assets": len(assets),
    "new_raw_files": len(new_raw),
    "new_raw_bytes": new_raw_bytes,
    "collected_cells": collected_cells,
    "not_found_cells": not_found_cells,
    "failures": status_counts,
    "public_official_records": public_records,
    "report": REPORT_PATH.as_posix(),
}
print(json.dumps(summary, ensure_ascii=False, indent=2))

if not sources and not assets:
    raise SystemExit("No WXC official raw evidence was collected; see manifest failures")
