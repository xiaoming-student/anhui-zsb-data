#!/usr/bin/env python3
"""Archive public official HBLG (淮北理工学院) 专升本 evidence for 2024-2026.

The collector intentionally prioritizes raw evidence over structure. It stores the
complete bytes returned by public official pages and attachments, computes SHA-256,
keeps strict year bindings, and records public candidate-level official records
without altering or enriching them. It never authenticates, solves CAPTCHAs, or
bypasses access controls.
"""
from __future__ import annotations

import csv
import hashlib
import html as html_module
import json
import os
import re
import time
from collections import defaultdict, deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import unquote, urljoin, urlparse

import requests
import urllib3
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

SCHOOL_ID = "HBLG"
SCHOOL_NAME = "淮北理工学院"
YEARS = (2024, 2025, 2026)
ROOT = Path("anhui_zsb_data/evidence/full_raw_30_schools") / SCHOOL_ID
REPORT_PATH = Path("anhui_zsb_data/reports/hblg_p0_raw_evidence_batch_01.md")
ROOT.mkdir(parents=True, exist_ok=True)
REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)

OFFICIAL_DOMAINS = ("hblgxy.edu.cn",)
MAX_FILE_BYTES = int(os.environ.get("HBLG_MAX_FILE_BYTES", str(120 * 1024 * 1024)))
REQUEST_DELAY = float(os.environ.get("HBLG_REQUEST_DELAY", "0.18"))
DISCOVERY_PAGE_LIMIT = int(os.environ.get("HBLG_DISCOVERY_PAGE_LIMIT", "8"))
CONNECT_TIMEOUT = float(os.environ.get("HBLG_CONNECT_TIMEOUT", "12"))
READ_TIMEOUT = float(os.environ.get("HBLG_READ_TIMEOUT", "80"))
USER_AGENT = "Mozilla/5.0 (compatible; AnhuiZSBDataResearch/2.0; public-official-archive)"

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
VALID_COVERAGE_STATUS = {
    "collected", "official_not_published", "not_found", "not_applicable",
    "removed_or_unavailable", "access_restricted", "manual_download_required",
    "public_official_record", "awaiting_manual_review",
}

TOPIC_KEYWORDS: dict[str, tuple[str, ...]] = {
    "admission_policy": ("招生章程", "招生简章", "招生实施办法"),
    "enrollment_plan": ("招生计划", "拟招生方案", "招生方案", "缺额计划"),
    "major_catalog": ("招生专业", "专业招生范围", "招生范围", "专业范围"),
    "training_location": ("联合培养", "培养地点", "培养校区", "就读地点"),
    "tuition_and_duration": ("学费", "学制", "住宿费"),
    "eligibility": ("报名条件", "报考条件", "资格审查", "资格审核", "报名资格"),
    "exam_subjects": ("考试科目", "专业课", "公共课"),
    "exam_syllabus": ("考试大纲", "测试大纲", "考查大纲", "职业适应性测试大纲"),
    "reference_books": ("参考书目", "参考教材", "教材版本"),
    "exam_schedule": ("考试时间", "考试安排", "测试时间", "面试时间", "准考证"),
    "exam_location": ("考试地点", "测试地点", "面试地点", "考点", "考场"),
    "admission_rules": ("录取规则", "录取细则", "同分排序", "择优录取"),
    "score_formula": ("综合成绩", "总成绩", "成绩计算", "计分公式"),
    "control_line": ("合格线", "控制线", "专业课合格"),
    "admission_min_score": ("最低录取分", "最低投档分", "录取分数线", "拟录取分数线", "文化课分数线"),
    "admission_max_score": ("最高录取分", "录取最高分"),
    "admission_average_score": ("平均录取分", "录取平均分"),
    "application_statistics": ("报名人数", "报考人数", "志愿人数"),
    "qualified_statistics": ("资格审查结果", "资格审核结果", "资格通过人数", "合格人数"),
    "admitted_statistics": ("录取人数", "录取统计"),
    "registered_statistics": ("报到人数", "注册人数", "新生报到"),
    "plan_adjustment": ("计划调整", "调整计划", "扩招", "缩招", "计划转入", "计划转出"),
    "adjustment": ("调剂", "征集志愿", "补录", "缺额计划"),
    "exemption": ("免试", "免文化课"),
    "retired_soldier": ("退役大学生士兵", "退役士兵"),
    "registered_poor_family": ("建档立卡"),
    "skill_competition": ("技能大赛", "职业技能大赛", "鼓励政策"),
    "other_official_notice": ("专升本",),
}

ATTACHMENT_EXTENSIONS = {
    ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".csv", ".zip",
    ".jpg", ".jpeg", ".png", ".tif", ".tiff",
}
HTML_EXTENSIONS = {"", ".htm", ".html", ".shtml", ".asp", ".aspx", ".php"}

PUBLIC_RECORD_TITLE_TERMS = (
    "拟录取名单", "预录取名单", "录取名单公示", "考生名单", "测试成绩的公示",
    "测试成绩公示", "面试成绩结果公示", "资格审查结果公示", "资格审核结果公示",
)

# Exact official pages discovered and verified through official-site indexing.
# Topic hints supplement, but never replace, topics inferred from archived content.
SEEDS: list[dict[str, Any]] = [
    {
        "year": 2024,
        "url": "https://zsb.hblgxy.edu.cn/info/1020/2103.htm",
        "title": "淮北理工学院2024年普通高校专升本招生章程",
        "topics": [
            "admission_policy", "enrollment_plan", "major_catalog", "training_location",
            "tuition_and_duration", "eligibility", "exam_subjects", "exam_syllabus",
            "reference_books", "exam_schedule", "exam_location", "admission_rules",
            "score_formula", "control_line", "exemption", "retired_soldier",
            "registered_poor_family", "skill_competition", "adjustment",
        ],
    },
    {
        "year": 2024,
        "url": "https://zsb.hblgxy.edu.cn/info/1020/2141.htm",
        "title": "2024年普通高校专升本免试退役士兵职业适应性测试成绩公示",
        "topics": ["retired_soldier", "exemption", "control_line", "other_official_notice"],
    },
    {
        "year": 2024,
        "url": "https://zsb.hblgxy.edu.cn/info/1020/2166.htm",
        "title": "淮北理工学院2024年专升本校外调剂B段拟录取名单公示",
        "topics": ["adjustment", "admission_min_score", "admission_rules", "admitted_statistics"],
    },
    {
        "year": 2025,
        "url": "https://zsb.hblgxy.edu.cn/info/1020/2216.htm",
        "title": "淮北理工学院2025年普通高校专升本拟招生方案",
        "topics": ["enrollment_plan", "major_catalog", "exam_subjects", "exam_syllabus", "reference_books"],
    },
    {
        "year": 2025,
        "url": "https://zsb.hblgxy.edu.cn/info/1020/2238.htm",
        "title": "淮北理工学院2025年普通高校专升本招生章程（招生动态栏目）",
        "topics": [
            "admission_policy", "enrollment_plan", "major_catalog", "training_location",
            "tuition_and_duration", "eligibility", "exam_subjects", "exam_syllabus",
            "reference_books", "exam_schedule", "exam_location", "admission_rules",
            "score_formula", "control_line", "exemption", "retired_soldier",
            "registered_poor_family", "skill_competition", "adjustment",
        ],
    },
    {
        "year": 2025,
        "url": "https://zsb.hblgxy.edu.cn/info/1021/2239.htm",
        "title": "淮北理工学院2025年普通高校专升本招生章程（招生章程栏目）",
        "topics": ["admission_policy", "enrollment_plan", "major_catalog", "exam_subjects", "exam_syllabus", "reference_books"],
    },
    {
        "year": 2025,
        "url": "https://zsb.hblgxy.edu.cn/info/1020/2261.htm",
        "title": "淮北理工学院2025年普通专升本鼓励政策考生资格审查结果公示",
        "topics": ["qualified_statistics", "exemption", "retired_soldier", "skill_competition"],
    },
    {
        "year": 2025,
        "url": "https://zsb.hblgxy.edu.cn/info/1020/2268.htm",
        "title": "2025年专升本技能大赛获奖鼓励政策面试成绩结果公示",
        "topics": ["skill_competition", "exemption", "control_line"],
    },
    {
        "year": 2025,
        "url": "https://zsb.hblgxy.edu.cn/info/1020/2269.htm",
        "title": "2025年普通高校专升本免试退役士兵职业适应性测试成绩公示",
        "topics": ["retired_soldier", "exemption", "control_line"],
    },
    {
        "year": 2025,
        "url": "https://zsb.hblgxy.edu.cn/info/1020/2296.htm",
        "title": "淮北理工学院2025年普通高校专升本校外调剂拟录取结果查询通知",
        "topics": ["adjustment", "admission_min_score", "admission_rules", "registered_poor_family"],
    },
    {
        "year": 2025,
        "url": "https://zsb.hblgxy.edu.cn/info/1020/2345.htm",
        "title": "淮北理工学院2025年招生工作进展",
        "topics": ["enrollment_plan", "admitted_statistics", "other_official_notice"],
    },
    {
        "year": 2026,
        "url": "https://zsb.hblgxy.edu.cn/info/1020/2352.htm",
        "title": "淮北理工学院2026年普通高校专升本拟招生方案",
        "topics": ["enrollment_plan", "major_catalog", "exam_subjects", "exam_syllabus", "reference_books"],
    },
    {
        "year": 2026,
        "url": "https://zsb.hblgxy.edu.cn/info/1020/2361.htm",
        "title": "淮北理工学院2026年普通高校专升本招生章程",
        "topics": [
            "admission_policy", "enrollment_plan", "major_catalog", "training_location",
            "tuition_and_duration", "eligibility", "exam_subjects", "exam_syllabus",
            "reference_books", "exam_schedule", "exam_location", "admission_rules",
            "score_formula", "control_line", "exemption", "retired_soldier",
            "registered_poor_family", "skill_competition", "adjustment",
        ],
    },
    {
        "year": 2026,
        "url": "https://zsb.hblgxy.edu.cn/info/1032/2384.htm",
        "title": "安徽省2026年普通高校专升本公共课合格线公布",
        "topics": ["control_line", "adjustment", "other_official_notice"],
    },
    {
        "year": 2026,
        "url": "https://zsb.hblgxy.edu.cn/info/1020/2398.htm",
        "title": "2026年普通专升本校外调剂免试退役士兵专项计划职业适应性综合面试须知",
        "topics": ["adjustment", "retired_soldier", "exemption", "exam_schedule", "exam_location", "admission_rules", "control_line"],
    },
]

DISCOVERY_LISTS = [
    "https://zsb.hblgxy.edu.cn/tzgg.htm",
    "https://zsb.hblgxy.edu.cn/zsdt/19.htm",
    "https://zsb.hblgxy.edu.cn/zszc.htm",
]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def short_id(value: str) -> str:
    return hashlib.sha1(value.encode("utf-8", "replace")).hexdigest()[:12]


def compact(value: str) -> str:
    return re.sub(r"\s+", "", value or "")


def allowed_official_url(url: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    return any(host == domain or host.endswith("." + domain) for domain in OFFICIAL_DOMAINS)


def safe_filename(value: str) -> str:
    value = html_module.unescape(unquote(value or ""))
    value = re.sub(r"[\\/:*?\"<>|\x00-\x1f]", "_", value).strip(" .")
    return (value or "download")[:180]


def infer_year(text: str) -> int | None:
    matched = {year for year in YEARS if str(year) in text}
    return next(iter(matched)) if len(matched) == 1 else None


def infer_topics(text: str) -> list[str]:
    normalized = compact(text)
    result = [topic for topic, words in TOPIC_KEYWORDS.items() if any(word in normalized for word in words)]
    if "专升本" in normalized and "other_official_notice" not in result:
        result.append("other_official_notice")
    return [topic for topic in TOPICS if topic in result]


def merge_topics(*groups: Iterable[str]) -> list[str]:
    merged: set[str] = set()
    for group in groups:
        merged.update(topic for topic in group if topic in TOPICS)
    return [topic for topic in TOPICS if topic in merged]


def primary_topic(topics: list[str]) -> str:
    for topic in TOPICS:
        if topic in topics and topic != "other_official_notice":
            return topic
    return "other_official_notice"


def category_directory(topic: str) -> str:
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


def is_public_official_record(title: str, text: str) -> bool:
    normalized_title = compact(title)
    if any(term in normalized_title for term in PUBLIC_RECORD_TITLE_TERMS):
        return True
    normalized_text = compact(text[:120000])
    return (
        any(term in normalized_title for term in ("公示", "成绩", "资格审查", "资格审核"))
        and "考生号" in normalized_text
        and "姓名" in normalized_text
    )


def parse_publish_date(text: str) -> str:
    match = re.search(r"(?<!\d)(20(?:24|25|26))[-年/.](\d{1,2})[-月/.](\d{1,2})日?", text[:15000])
    if not match:
        return ""
    return f"{match.group(1)}-{int(match.group(2)):02d}-{int(match.group(3)):02d}"


def decode_html(data: bytes) -> str:
    for encoding in ("utf-8", "gb18030", "gbk"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def parse_html(data: bytes) -> tuple[BeautifulSoup, str, str, str]:
    decoded = decode_html(data)
    soup = BeautifulSoup(decoded, "html.parser")
    title = soup.title.get_text(" ", strip=True) if soup.title else ""
    text = soup.get_text("\n", strip=True)
    return soup, compact(title), text, parse_publish_date(text)


def looks_like_html(data: bytes, content_type: str) -> bool:
    prefix = data[:1024].lstrip().lower()
    return "html" in (content_type or "").lower() or prefix.startswith((b"<!doctype html", b"<html", b"<?xml"))


def infer_extension(url: str, meta: dict[str, Any], data: bytes) -> str:
    path_ext = Path(unquote(urlparse(meta.get("final_url") or url).path)).suffix.lower()
    content_type = (meta.get("content_type") or "").lower()
    disposition = meta.get("content_disposition") or ""
    disposition_match = re.search(r"filename\*?=(?:UTF-8''|\")?([^\";]+)", disposition, re.IGNORECASE)
    disposition_ext = Path(unquote(disposition_match.group(1))).suffix.lower() if disposition_match else ""

    if data.startswith(b"%PDF-"):
        return ".pdf"
    if data.startswith(b"PK\x03\x04"):
        if path_ext in {".docx", ".xlsx", ".zip"}:
            return path_ext
        if disposition_ext in {".docx", ".xlsx", ".zip"}:
            return disposition_ext
        return ".zip"
    if data.startswith(b"\xd0\xcf\x11\xe0"):
        if path_ext in {".doc", ".xls"}:
            return path_ext
        if disposition_ext in {".doc", ".xls"}:
            return disposition_ext
        return ".doc"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png"
    if data.startswith(b"\xff\xd8\xff"):
        return ".jpg"
    if looks_like_html(data, content_type):
        return ".html"
    if path_ext in ATTACHMENT_EXTENSIONS:
        return path_ext
    if disposition_ext in ATTACHMENT_EXTENSIONS:
        return disposition_ext
    if "pdf" in content_type:
        return ".pdf"
    return path_ext if path_ext else ".bin"


urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
session = requests.Session()
session.trust_env = False
retry = Retry(
    total=2,
    connect=2,
    read=2,
    backoff_factor=0.7,
    status_forcelist=(429, 500, 502, 503, 504),
    allowed_methods=frozenset(("GET",)),
)
session.mount("https://", HTTPAdapter(max_retries=retry))
session.mount("http://", HTTPAdapter(max_retries=retry))
session.headers.update(
    {
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/pdf,application/octet-stream,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.5",
    }
)


def fetch_public(url: str, referer: str = "") -> tuple[bytes | None, dict[str, Any]]:
    attempts: list[tuple[str, bool, str]] = [(url, True, "https-verified")]
    if url.startswith("https://"):
        attempts.extend(
            [
                (url, False, "https-unverified"),
                ("http://" + url[len("https://") :], True, "http-fallback"),
            ]
        )
    errors: list[str] = []
    for attempt_url, verify, transport in attempts:
        try:
            headers = {"Referer": referer} if referer else None
            response = session.get(
                attempt_url,
                headers=headers,
                timeout=(CONNECT_TIMEOUT, READ_TIMEOUT),
                allow_redirects=True,
                verify=verify,
                stream=True,
            )
            meta: dict[str, Any] = {
                "http_status": response.status_code,
                "final_url": response.url,
                "content_type": response.headers.get("Content-Type", ""),
                "content_disposition": response.headers.get("Content-Disposition", ""),
                "transport": transport,
                "tls_verified": verify if attempt_url.startswith("https://") else None,
            }
            if response.status_code >= 400:
                errors.append(f"{transport}: HTTP {response.status_code}")
                response.close()
                continue
            declared = int(response.headers.get("Content-Length", "0") or 0)
            if declared > MAX_FILE_BYTES:
                response.close()
                meta.update({"error": f"declared size {declared} exceeds {MAX_FILE_BYTES}", "file_size": declared})
                return None, meta
            chunks: list[bytes] = []
            total = 0
            for chunk in response.iter_content(1024 * 1024):
                if not chunk:
                    continue
                total += len(chunk)
                if total > MAX_FILE_BYTES:
                    response.close()
                    meta.update({"error": f"download exceeded {MAX_FILE_BYTES}", "file_size": total})
                    return None, meta
                chunks.append(chunk)
            response.close()
            data = b"".join(chunks)
            meta.update({"file_size": len(data), "sha256": sha256(data)})
            if not data:
                errors.append(f"{transport}: empty response")
                continue
            time.sleep(REQUEST_DELAY)
            return data, meta
        except Exception as exc:
            errors.append(f"{transport}: {type(exc).__name__}: {exc}")
    return None, {
        "http_status": "error",
        "final_url": url,
        "error": " | ".join(errors),
        "transport": "failed",
    }


manifest_path = ROOT / "school_manifest.json"
if manifest_path.exists():
    manifest: dict[str, Any] = json.loads(manifest_path.read_text("utf-8-sig"))
else:
    manifest = {}

old_sources: list[dict[str, Any]] = list(manifest.get("sources", []))
old_assets: list[dict[str, Any]] = list(manifest.get("assets", []))
old_failures: list[dict[str, Any]] = list(manifest.get("failures", []))

sources_by_url: dict[tuple[int, str], dict[str, Any]] = {}
assets_by_relation: dict[tuple[int, str, str], dict[str, Any]] = {}
for entry in old_sources:
    if entry.get("official_url"):
        sources_by_url[(int(entry.get("year", 0)), entry["official_url"])] = entry
for entry in old_assets:
    url = entry.get("attachment_url") or entry.get("official_url")
    if url:
        assets_by_relation[(int(entry.get("year", 0)), entry.get("parent_page_url", ""), url)] = entry

failures: list[dict[str, Any]] = old_failures.copy()
coverage_evidence: dict[tuple[int, str], list[str]] = defaultdict(list)
failed_topic_status: dict[tuple[int, str], set[str]] = defaultdict(set)
raw_path_by_hash: dict[str, str] = {}
for entry in old_sources + old_assets:
    if entry.get("sha256") and entry.get("local_path"):
        raw_path_by_hash[entry["sha256"]] = entry["local_path"]
    year = int(entry.get("year", 0) or 0)
    topics_value = entry.get("topics", "")
    entry_topics = topics_value.split("|") if isinstance(topics_value, str) else list(topics_value or [])
    for topic in entry_topics:
        if year in YEARS and topic in TOPICS:
            coverage_evidence[(year, topic)].append(entry.get("local_path", ""))

before_raw_paths = {
    path
    for path in ROOT.rglob("*")
    if path.is_file()
    and path.name not in {"school_manifest.json", "school_coverage.csv", "school_notes.md"}
    and not path.name.endswith("_parsed.txt")
}


def add_failure(
    *,
    year: int | None,
    url: str,
    title: str,
    topics: list[str],
    status: str,
    meta: dict[str, Any],
    parent_page_url: str = "",
) -> None:
    failure = {
        "school_id": SCHOOL_ID,
        "school_name": SCHOOL_NAME,
        "year": year,
        "title": title,
        "url": url,
        "parent_page_url": parent_page_url,
        "topics": "|".join(topics),
        "http_status": meta.get("http_status", "error"),
        "status": status,
        "reason": (meta.get("error") or f"HTTP {meta.get('http_status')}")[:2000],
        "checked_at": utc_now(),
    }
    key = (failure["year"], failure["url"], failure["status"], failure["reason"])
    if not any((item.get("year"), item.get("url"), item.get("status"), item.get("reason")) == key for item in failures):
        failures.append(failure)
    if year in YEARS:
        for topic in topics:
            if topic in TOPICS:
                failed_topic_status[(year, topic)].add(status)


def determine_failure_status(meta: dict[str, Any]) -> str:
    status = meta.get("http_status")
    if status in (401, 403, 407, 429, "error", 0, None):
        return "access_restricted"
    if status == 404:
        return "removed_or_unavailable"
    return "awaiting_manual_review"


def store_bytes(
    *,
    year: int,
    url: str,
    data: bytes,
    meta: dict[str, Any],
    title: str,
    topics: list[str],
    page_text: str,
    publish_date: str,
    parent_page_url: str,
    is_html_page: bool,
    public_record: bool,
    attachment_name: str = "",
) -> dict[str, Any]:
    topics = merge_topics(topics) or ["other_official_notice"]
    topic = primary_topic(topics)
    folder = ROOT / str(year) / category_directory(topic)
    folder.mkdir(parents=True, exist_ok=True)
    extension = infer_extension(url, meta, data)
    prefix = "SRC" if is_html_page else "AST"
    base = f"{prefix}-{SCHOOL_ID}-{year}-{topic}-{short_id(parent_page_url + '|' + url)}"
    target = folder / f"{base}{extension}"
    file_hash = sha256(data)
    deduplicated = file_hash in raw_path_by_hash and Path(raw_path_by_hash[file_hash]).is_file()
    if deduplicated:
        local_path = raw_path_by_hash[file_hash]
    else:
        target.write_bytes(data)
        local_path = target.as_posix()
        raw_path_by_hash[file_hash] = local_path

    parsed_path = ""
    if is_html_page:
        parsed = folder / f"{base}_parsed.txt"
        parsed.write_text(
            f"Title: {title}\nOfficial URL: {url}\nFinal URL: {meta.get('final_url', url)}\n"
            f"Publish date: {publish_date}\nRetrieved at: {utc_now()}\n\n{page_text}\n",
            "utf-8",
        )
        parsed_path = parsed.as_posix()

    status = "public_official_record" if public_record else "collected"
    common: dict[str, Any] = {
        "school_id": SCHOOL_ID,
        "school_name": SCHOOL_NAME,
        "year": year,
        "title": title,
        "publish_date": publish_date,
        "retrieved_at": utc_now(),
        "official_page_url": url if is_html_page else parent_page_url,
        "official_url": url,
        "final_url": meta.get("final_url", url),
        "source_domain": urlparse(meta.get("final_url") or url).hostname or "",
        "document_type": "html" if is_html_page else "attachment",
        "topics": "|".join(topics),
        "file_type": extension.lstrip("."),
        "local_path": local_path,
        "parsed_text_path": parsed_path,
        "file_size": len(data),
        "sha256": file_hash,
        "http_status": meta.get("http_status", 200),
        "content_type": meta.get("content_type", ""),
        "status": status,
        "deduplicated": deduplicated,
        "transport": meta.get("transport", ""),
        "tls_verified": meta.get("tls_verified"),
        "notes": "publicly accessible official record preserved byte-for-byte; no authentication or access-control bypass",
    }
    if is_html_page:
        common.update(
            {
                "source_id": f"SRC-{SCHOOL_ID}-{year}-{short_id(url)}",
                "parent_page_url": parent_page_url,
            }
        )
    else:
        common.update(
            {
                "asset_id": f"AST-{SCHOOL_ID}-{year}-{short_id(parent_page_url + '|' + url)}",
                "parent_page": parent_page_url,
                "parent_page_url": parent_page_url,
                "attachment_url": url,
                "attachment_filename": attachment_name or Path(unquote(urlparse(meta.get("final_url") or url).path)).name or Path(local_path).name,
                "attachment_sha256": file_hash,
            }
        )
    for evidence_topic in topics:
        coverage_evidence[(year, evidence_topic)].append(local_path)
    return common


fetched_cache: dict[str, tuple[bytes | None, dict[str, Any]]] = {}
success_urls: set[str] = set()


def cached_fetch(url: str, referer: str = "") -> tuple[bytes | None, dict[str, Any]]:
    if url not in fetched_cache:
        fetched_cache[url] = fetch_public(url, referer=referer)
    return fetched_cache[url]


def attachment_candidate(url: str, anchor: str) -> bool:
    path = unquote(urlparse(url).path)
    extension = Path(path).suffix.lower()
    token = compact(anchor + " " + path + " " + url)
    return (
        extension in ATTACHMENT_EXTENSIONS
        or "/_upload/" in path
        or "downloadattach" in url.lower()
        or "news.DownloadAttachUrl" in url
        or any(ext in token.lower() for ext in (".pdf", ".doc", ".docx", ".xls", ".xlsx", ".zip"))
        or "附件" in anchor
    )


def archive_attachment(
    *,
    year: int,
    url: str,
    parent_page_url: str,
    parent_title: str,
    parent_text: str,
    parent_topics: list[str],
    public_record: bool,
    anchor: str,
    publish_date: str,
) -> None:
    relation_key = (year, parent_page_url, url)
    if relation_key in assets_by_relation:
        return
    data, meta = cached_fetch(url, referer=parent_page_url)
    attachment_topics = merge_topics(parent_topics, infer_topics(anchor + "\n" + parent_title + "\n" + parent_text[:30000]))
    if data is None:
        add_failure(
            year=year,
            url=url,
            title=anchor or f"{parent_title}附件",
            topics=attachment_topics,
            status=determine_failure_status(meta),
            meta=meta,
            parent_page_url=parent_page_url,
        )
        return
    extension = infer_extension(url, meta, data)
    if extension == ".html" and not looks_like_html(data, meta.get("content_type", "")):
        add_failure(
            year=year,
            url=url,
            title=anchor or f"{parent_title}附件",
            topics=attachment_topics,
            status="awaiting_manual_review",
            meta={**meta, "error": "attachment response type could not be verified"},
            parent_page_url=parent_page_url,
        )
        return
    if extension == ".html":
        _, returned_title, returned_text, _ = parse_html(data)
        error_token = compact(returned_title + returned_text[:5000]).lower()
        if any(token in error_token for token in ("404", "页面不存在", "访问出错", "login", "登录")):
            add_failure(
                year=year,
                url=url,
                title=anchor or f"{parent_title}附件",
                topics=attachment_topics,
                status="removed_or_unavailable",
                meta={**meta, "error": "attachment endpoint returned an HTML error/login page"},
                parent_page_url=parent_page_url,
            )
            return
    entry = store_bytes(
        year=year,
        url=url,
        data=data,
        meta=meta,
        title=anchor or f"{parent_title}附件",
        topics=attachment_topics,
        page_text="",
        publish_date=publish_date,
        parent_page_url=parent_page_url,
        is_html_page=False,
        public_record=public_record,
        attachment_name=safe_filename(anchor),
    )
    assets_by_relation[relation_key] = entry
    success_urls.add(url)
    print(f"ASSET {year} {entry['file_type']} {entry['file_size']} {url}")


def archive_page(spec: dict[str, Any], discovered_from: str = "") -> None:
    year = int(spec["year"])
    url = spec["url"]
    key = (year, url)
    data, meta = cached_fetch(url, referer=discovered_from)
    topic_hints = merge_topics(spec.get("topics", []))
    if data is None:
        add_failure(
            year=year,
            url=url,
            title=spec.get("title", ""),
            topics=topic_hints,
            status=determine_failure_status(meta),
            meta=meta,
            parent_page_url=discovered_from,
        )
        return
    if not looks_like_html(data, meta.get("content_type", "")):
        add_failure(
            year=year,
            url=url,
            title=spec.get("title", ""),
            topics=topic_hints,
            status="awaiting_manual_review",
            meta={**meta, "error": "expected official HTML article but response was not HTML"},
            parent_page_url=discovered_from,
        )
        return
    soup, parsed_title, text, publish_date = parse_html(data)
    title = spec.get("title") or parsed_title or f"{SCHOOL_NAME}{year}年专升本官方页面"
    relevance = compact(title + "\n" + text[:80000])
    if "专升本" not in relevance:
        add_failure(
            year=year,
            url=url,
            title=title,
            topics=topic_hints,
            status="awaiting_manual_review",
            meta={**meta, "error": "official page did not contain a 专升本 binding"},
            parent_page_url=discovered_from,
        )
        return
    content_year = infer_year(title + "\n" + text[:50000])
    if content_year is not None and content_year != year:
        add_failure(
            year=year,
            url=url,
            title=title,
            topics=topic_hints,
            status="awaiting_manual_review",
            meta={**meta, "error": f"strict year-binding mismatch: expected {year}, content indicated {content_year}"},
            parent_page_url=discovered_from,
        )
        return
    page_topics = merge_topics(topic_hints, infer_topics(title + "\n" + text[:100000]))
    public_record = is_public_official_record(title, text)
    if key not in sources_by_url:
        entry = store_bytes(
            year=year,
            url=url,
            data=data,
            meta=meta,
            title=title,
            topics=page_topics,
            page_text=text,
            publish_date=publish_date,
            parent_page_url=discovered_from,
            is_html_page=True,
            public_record=public_record,
        )
        sources_by_url[key] = entry
        print(f"SOURCE {year} {entry['status']} {entry['file_size']} {url}")
    success_urls.add(url)

    page_final_url = meta.get("final_url") or url
    for anchor_tag in soup.find_all("a", href=True):
        anchor = anchor_tag.get_text(" ", strip=True)
        href = html_module.unescape(anchor_tag.get("href", "")).strip()
        if not href or href.lower().startswith(("javascript:", "mailto:", "tel:")):
            continue
        attachment_url = urljoin(page_final_url, href).split("#", 1)[0]
        if not attachment_url.startswith(("http://", "https://")) or not allowed_official_url(attachment_url):
            continue
        if attachment_candidate(attachment_url, anchor):
            archive_attachment(
                year=year,
                url=attachment_url,
                parent_page_url=url,
                parent_title=title,
                parent_text=text,
                parent_topics=page_topics,
                public_record=public_record,
                anchor=anchor,
                publish_date=publish_date,
            )


def discover_relevant_articles() -> list[dict[str, Any]]:
    discovered: dict[tuple[int, str], dict[str, Any]] = {}
    queue: deque[str] = deque(DISCOVERY_LISTS)
    seen: set[str] = set()
    while queue and len(seen) < DISCOVERY_PAGE_LIMIT:
        list_url = queue.popleft()
        if list_url in seen:
            continue
        seen.add(list_url)
        data, meta = cached_fetch(list_url)
        if data is None or not looks_like_html(data, meta.get("content_type", "")):
            continue
        soup, _, _, _ = parse_html(data)
        final = meta.get("final_url") or list_url
        for tag in soup.find_all("a", href=True):
            anchor = tag.get_text(" ", strip=True)
            href = html_module.unescape(tag.get("href", "")).strip()
            if not href or href.lower().startswith(("javascript:", "mailto:", "tel:")):
                continue
            candidate = urljoin(final, href).split("#", 1)[0]
            if not allowed_official_url(candidate):
                continue
            token = compact(anchor + " " + candidate)
            article_year = infer_year(token)
            if article_year in YEARS and "专升本" in token and "/info/" in urlparse(candidate).path:
                discovered[(article_year, candidate)] = {
                    "year": article_year,
                    "url": candidate,
                    "title": anchor,
                    "topics": infer_topics(anchor),
                    "discovered_from": list_url,
                }
            path = urlparse(candidate).path
            if (
                any(part in path for part in ("tzgg", "zsdt", "zszc"))
                and candidate not in seen
                and len(seen) + len(queue) < DISCOVERY_PAGE_LIMIT
            ):
                queue.append(candidate)
    return list(discovered.values())


for seed in SEEDS:
    archive_page(seed)

for discovered in discover_relevant_articles():
    if (int(discovered["year"]), discovered["url"]) not in sources_by_url:
        archive_page(discovered, discovered_from=discovered.get("discovered_from", ""))

failures = [failure for failure in failures if failure.get("url") not in success_urls]
unique_failures: dict[tuple[Any, ...], dict[str, Any]] = {}
for failure in failures:
    key = (
        failure.get("year"),
        failure.get("url"),
        failure.get("status"),
        failure.get("reason"),
        failure.get("parent_page_url"),
    )
    unique_failures[key] = failure
failures = sorted(
    unique_failures.values(),
    key=lambda item: (str(item.get("year")), item.get("url", ""), item.get("status", "")),
)

sources = sorted(sources_by_url.values(), key=lambda item: (int(item.get("year", 0)), item.get("official_url", "")))
assets = sorted(
    assets_by_relation.values(),
    key=lambda item: (int(item.get("year", 0)), item.get("parent_page_url", ""), item.get("attachment_url", "")),
)

manifest.update(
    {
        "school_id": SCHOOL_ID,
        "school_name": SCHOOL_NAME,
        "school_type": "民办",
        "official_domains": list(OFFICIAL_DOMAINS),
        "years_audited": list(YEARS),
        "topics_audited": TOPICS,
        "sources": sources,
        "assets": assets,
        "failures": failures,
        "raw_information_policy": (
            "preserve complete bytes of publicly accessible official records, including public candidate-level records; "
            "do not authenticate, bypass access controls, or enrich personal identities"
        ),
        "original_information_preserved": True,
        "sanitized": False,
        "last_audited_at": utc_now(),
    }
)
manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", "utf-8")

coverage_path = ROOT / "school_coverage.csv"
coverage: dict[tuple[int, str], str] = {(year, topic): "not_found" for year in YEARS for topic in TOPICS}
for (year, topic), paths in coverage_evidence.items():
    if year in YEARS and topic in TOPICS and any(paths):
        coverage[(year, topic)] = "collected"
for (year, topic), statuses in failed_topic_status.items():
    if coverage[(year, topic)] == "collected":
        continue
    if "access_restricted" in statuses:
        coverage[(year, topic)] = "access_restricted"
    elif "manual_download_required" in statuses:
        coverage[(year, topic)] = "manual_download_required"
    elif "removed_or_unavailable" in statuses:
        coverage[(year, topic)] = "removed_or_unavailable"
    elif "awaiting_manual_review" in statuses:
        coverage[(year, topic)] = "awaiting_manual_review"

with coverage_path.open("w", encoding="utf-8-sig", newline="") as handle:
    writer = csv.writer(handle, lineterminator="\n")
    writer.writerow(["school_id", "school_name", "year", "topic", "status"])
    for year in YEARS:
        for topic in TOPICS:
            status = coverage[(year, topic)]
            if status not in VALID_COVERAGE_STATUS:
                raise RuntimeError(f"invalid coverage status: {status}")
            writer.writerow([SCHOOL_ID, SCHOOL_NAME, year, topic, status])

unique_raw_paths = {
    Path(entry["local_path"])
    for entry in sources + assets
    if entry.get("local_path") and Path(entry["local_path"]).is_file()
}
after_raw_paths = {
    path
    for path in ROOT.rglob("*")
    if path.is_file()
    and path.name not in {"school_manifest.json", "school_coverage.csv", "school_notes.md"}
    and not path.name.endswith("_parsed.txt")
}
new_raw_paths = after_raw_paths - before_raw_paths
public_record_documents = [entry for entry in sources + assets if entry.get("status") == "public_official_record"]
status_counts: dict[str, int] = defaultdict(int)
for status in coverage.values():
    status_counts[status] += 1
failure_counts: dict[str, int] = defaultdict(int)
for failure in failures:
    failure_counts[failure.get("status", "unknown")] += 1

covered_by_year = {
    year: [topic for topic in TOPICS if coverage[(year, topic)] == "collected"]
    for year in YEARS
}
unresolved_by_year = {
    year: [topic for topic in TOPICS if coverage[(year, topic)] != "collected"]
    for year in YEARS
}

notes_lines = [
    f"# {SCHOOL_NAME} ({SCHOOL_ID})",
    "",
    f"- Last audited at: {manifest['last_audited_at']}",
    f"- Official HTML source pages: {len(sources)}",
    f"- Official attachment relations: {len(assets)}",
    f"- Unique raw original files: {len(unique_raw_paths)}",
    f"- Unique raw bytes: {sum(path.stat().st_size for path in unique_raw_paths)}",
    f"- Collected coverage cells: {status_counts.get('collected', 0)}/84",
    f"- Public official candidate-level documents: {len(public_record_documents)}",
    "- Public official records are preserved as published; no login, CAPTCHA, permission control, or non-public endpoint was bypassed.",
    "- Search engines were used only to discover official URLs; formal evidence is restricted to the official domain.",
    "",
]
for year in YEARS:
    notes_lines.extend(
        [
            f"## {year}",
            "",
            f"- Collected topics ({len(covered_by_year[year])}): "
            + (", ".join(f"`{topic}`" for topic in covered_by_year[year]) or "none"),
            f"- Still unresolved ({len(unresolved_by_year[year])}): "
            + (", ".join(f"`{topic}`" for topic in unresolved_by_year[year]) or "none"),
            "",
        ]
    )
if failures:
    notes_lines.extend(["## Retrieval failures / manual review", ""])
    for failure in failures:
        notes_lines.append(
            f"- {failure.get('year')}: `{failure.get('status')}` — {failure.get('url')} — {failure.get('reason')}"
        )
    notes_lines.append("")
(ROOT / "school_notes.md").write_text("\n".join(notes_lines), "utf-8")

report_lines = [
    "# HBLG 淮北理工学院 P0 原始数据补采审计（Batch 01）",
    "",
    f"> 生成时间：{manifest['last_audited_at']}",
    "",
    "## 本批汇总",
    "",
    "| 指标 | 数值 |",
    "|---|---:|",
    "| 本批学校数 | 1 |",
    f"| 新增 source document 数 | {max(0, len(sources) - len(old_sources))} |",
    f"| 新增 attachment relation 数 | {max(0, len(assets) - len(old_assets))} |",
    f"| 新增原始文件数 | {len(new_raw_paths)} |",
    f"| 新增总字节数 | {sum(path.stat().st_size for path in new_raw_paths)} |",
    f"| 当前唯一原始文件总数 | {len(unique_raw_paths)} |",
    f"| 当前原始数据总字节数 | {sum(path.stat().st_size for path in unique_raw_paths)} |",
    f"| collected 覆盖格数 | {status_counts.get('collected', 0)} |",
    f"| 仍 not_found 数 | {status_counts.get('not_found', 0)} |",
    f"| access_restricted 覆盖格数 | {status_counts.get('access_restricted', 0)} |",
    f"| manual_download_required 覆盖格数 | {status_counts.get('manual_download_required', 0)} |",
    f"| 公开官方考生级资料数 | {len(public_record_documents)} |",
    "",
    "## 学校—年份审计",
    "",
    "| 学校 | 年份 | 已补主题 | 仍缺主题 | 下一步 |",
    "|---|---:|---|---|---|",
]
for year in YEARS:
    report_lines.append(
        f"| 淮北理工学院 | {year} | "
        + ("、".join(covered_by_year[year]) or "无")
        + " | "
        + ("、".join(unresolved_by_year[year]) or "无")
        + " | 继续补查报名统计、资格人数、报到注册、最高分、平均分及计划调整 |"
    )
report_lines.extend(["", "## 已归档正式来源", ""])
for entry in sources:
    report_lines.append(
        f"- {entry['year']}｜{entry['title']}｜`{entry['status']}`｜{entry['official_url']}｜"
        f"`{entry['sha256']}`｜{entry['file_size']} bytes"
    )
report_lines.extend(["", "## 附件汇总", ""])
for entry in assets:
    report_lines.append(
        f"- {entry['year']}｜{entry['attachment_filename']}｜`{entry['status']}`｜{entry['attachment_url']}｜"
        f"`{entry['sha256']}`｜{entry['file_size']} bytes"
    )
if failures:
    report_lines.extend(["", "## 仍需处理的失败项", ""])
    for failure in failures:
        report_lines.append(
            f"- {failure.get('year')}｜`{failure.get('status')}`｜{failure.get('url')}｜{failure.get('reason')}"
        )
REPORT_PATH.write_text("\n".join(report_lines) + "\n", "utf-8")

summary = {
    "school_id": SCHOOL_ID,
    "sources": len(sources),
    "attachment_relations": len(assets),
    "unique_raw_files": len(unique_raw_paths),
    "raw_bytes": sum(path.stat().st_size for path in unique_raw_paths),
    "new_raw_files": len(new_raw_paths),
    "new_raw_bytes": sum(path.stat().st_size for path in new_raw_paths),
    "collected_cells": status_counts.get("collected", 0),
    "not_found_cells": status_counts.get("not_found", 0),
    "public_official_records": len(public_record_documents),
    "failure_counts": dict(failure_counts),
    "report": REPORT_PATH.as_posix(),
}
print(json.dumps(summary, ensure_ascii=False, indent=2))

if not sources:
    raise SystemExit("No HBLG official HTML source was collected; inspect manifest failures")
if not assets:
    raise SystemExit("No HBLG official attachment was collected; inspect page parsing and manifest failures")
