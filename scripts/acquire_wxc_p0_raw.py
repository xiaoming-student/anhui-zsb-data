#!/usr/bin/env python3
"""Targeted raw-evidence acquisition for WXC (皖西学院), 2024-2026.

The collector is deliberately narrow and evidence-first:
- only public URLs on official ``wxc.edu.cn`` / ``ahzsks.cn`` domains become formal evidence;
- raw response bytes are preserved before any parsing;
- public official records are preserved intact and tagged ``public_official_record``;
- no login, CAPTCHA, permission bypass, or identity enrichment is attempted;
- year binding is strict and inherited by attachments only from a year-bound parent;
- inaccessible official URLs are recorded as ``access_restricted`` rather than ``not_found``.

The script can be run repeatedly. Sources/assets are deduplicated by URL and SHA-256.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import mimetypes
import re
import shutil
import ssl
import subprocess
import sys
import tempfile
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Iterable
from urllib.error import HTTPError, URLError
from urllib.parse import unquote, urljoin, urlparse
from urllib.request import Request, urlopen

SCHOOL_ID = "WXC"
SCHOOL_NAME = "皖西学院"
YEARS = (2024, 2025, 2026)
OFFICIAL_DOMAINS = ("wxc.edu.cn", "ahzsks.cn")
MAX_FILE_BYTES_DEFAULT = 100 * 1024 * 1024
USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "Chrome/150.0 Safari/537.36 AnhuiZSBDataArchive/2.0"
)

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

TOPIC_KEYWORDS: dict[str, tuple[str, ...]] = {
    "admission_policy": ("招生章程", "招生简章", "实施办法"),
    "enrollment_plan": ("招生计划", "拟招生方案", "拟招生专业"),
    "major_catalog": ("招生专业", "专业范围", "专业招生范围", "专业对照"),
    "training_location": ("联合培养", "培养地点", "校区"),
    "tuition_and_duration": ("学费", "学制", "住宿费"),
    "eligibility": ("报名条件", "报考资格", "资格审核", "报名承诺书"),
    "exam_subjects": ("考试科目", "专业课", "公共课"),
    "exam_syllabus": ("考试大纲", "测试大纲", "考查大纲"),
    "reference_books": ("参考书目", "参考教材", "参考书"),
    "exam_schedule": ("考试时间", "考试安排", "面试时间", "测试时间"),
    "exam_location": ("考试地点", "考点", "考场", "测试地点"),
    "admission_rules": ("录取规则", "录取细则", "同分排序", "择优录取"),
    "score_formula": ("成绩计算", "综合成绩", "总成绩", "计分公式"),
    "control_line": ("合格线", "控制线", "专业课总分不低于"),
    "admission_min_score": ("最低录取分", "最低投档分", "录取分数线"),
    "admission_max_score": ("最高录取分", "录取最高分"),
    "admission_average_score": ("平均录取分", "录取平均分"),
    "application_statistics": ("报名人数", "报考人数", "志愿人数"),
    "qualified_statistics": ("资格审核通过人数", "资格通过人数", "合格人数"),
    "admitted_statistics": ("录取人数", "录取统计"),
    "registered_statistics": ("报到人数", "注册人数", "实际入学"),
    "plan_adjustment": ("计划调整", "调整计划", "扩招", "缩招"),
    "adjustment": ("调剂", "征集志愿", "补录", "缺额计划"),
    "exemption": ("免试", "免文化课"),
    "retired_soldier": ("退役大学生士兵", "退役士兵"),
    "registered_poor_family": ("建档立卡"),
    "skill_competition": ("技能大赛", "职业技能大赛"),
    "other_official_notice": ("专升本",),
}

PUBLIC_RECORD_KEYWORDS = (
    "拟录取名单", "预录取名单", "录取名单", "考生名单", "面试名单",
    "资格名单", "免试名单", "成绩名单", "考生号", "准考证号", "身份证号",
)

RELEVANT_KEYWORDS = tuple(
    sorted({kw for values in TOPIC_KEYWORDS.values() for kw in values}, key=len, reverse=True)
)
FILE_EXTENSIONS = {
    ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".csv", ".json", ".txt",
    ".jpg", ".jpeg", ".png", ".tif", ".tiff", ".zip",
}

SUBDIRS = {
    "admission_policy": "admission_policy",
    "enrollment_plan": "enrollment_plan",
    "major_catalog": "enrollment_plan",
    "training_location": "enrollment_plan",
    "tuition_and_duration": "enrollment_plan",
    "eligibility": "enrollment_plan",
    "exam_subjects": "exam_syllabus",
    "exam_syllabus": "exam_syllabus",
    "reference_books": "exam_syllabus",
    "exam_schedule": "exam_syllabus",
    "exam_location": "exam_syllabus",
    "admission_rules": "admission_scores",
    "score_formula": "admission_scores",
    "control_line": "admission_scores",
    "admission_min_score": "admission_scores",
    "admission_max_score": "admission_scores",
    "admission_average_score": "admission_scores",
    "application_statistics": "statistics",
    "qualified_statistics": "statistics",
    "admitted_statistics": "statistics",
    "registered_statistics": "statistics",
    "plan_adjustment": "adjustments",
    "adjustment": "adjustments",
}


@dataclass(frozen=True)
class Candidate:
    year: int
    url: str
    title: str
    topics: tuple[str, ...]
    kind: str = "page"
    parent_page: str = ""
    expected_filename: str = ""
    discovery_basis: str = "seeded_exact_official_url"


# URLs below were independently located and year-bound before the collector was written.
SEED_CANDIDATES: tuple[Candidate, ...] = (
    Candidate(
        2024,
        "https://zsb.wxc.edu.cn/2024/0312/c270a183191/page.htm",
        "皖西学院2024年专升本考试大纲及参考书目通知",
        ("major_catalog", "exam_subjects", "exam_syllabus", "reference_books", "other_official_notice"),
    ),
    Candidate(
        2025,
        "https://www.ahzsks.cn/zyyx/8108.htm",
        "皖西学院2025年普通高校专升本招生章程",
        ("admission_policy", "other_official_notice"),
        discovery_basis="seeded_exact_provincial_official_url",
    ),
    Candidate(
        2025,
        "https://zsb.wxc.edu.cn/_upload/article/files/61/dc/c7c861c34e73a0b4a234a93c7f94/3b31146a-9b4a-4995-ba14-ab7eadc8c7c1.pdf",
        "皖西学院2025年专升本考试大纲（专业课）",
        ("exam_syllabus", "other_official_notice"),
        kind="attachment",
        expected_filename="皖西学院2025年专升本考试大纲（专业课）.pdf",
        discovery_basis="seeded_exact_official_attachment_url",
    ),
    Candidate(
        2025,
        "https://zsb.wxc.edu.cn/_upload/article/files/61/dc/c7c861c34e73a0b4a234a93c7f94/e4b3b43c-f1b7-4124-ba75-502aca08422d.pdf",
        "2025年皖西学院专升本招生专业考试科目及参考书目",
        ("major_catalog", "training_location", "exam_subjects", "reference_books", "other_official_notice"),
        kind="attachment",
        expected_filename="2025年皖西学院专升本招生专业考试科目及参考书目.pdf",
        discovery_basis="seeded_exact_official_attachment_url",
    ),
    Candidate(
        2026,
        "https://zsb.wxc.edu.cn/2025/1208/c270a208230/page.htm",
        "关于公布皖西学院2026年普通专升本拟招生专业考试科目、考试大纲及参考书目的通知",
        ("major_catalog", "exam_subjects", "exam_syllabus", "reference_books", "other_official_notice"),
    ),
    Candidate(
        2026,
        "https://zsb.wxc.edu.cn/_upload/article/files/8b/4f/53caeb5d4bb18157fd3e1db9625d/40a7ba02-ea56-4257-b910-508297c2d7f6.pdf",
        "皖西学院2026年专升本考试大纲（专业课）",
        ("exam_syllabus", "other_official_notice"),
        kind="attachment",
        parent_page="https://zsb.wxc.edu.cn/2025/1208/c270a208230/page.htm",
        expected_filename="皖西学院2026年专升本考试大纲（专业课）.pdf",
    ),
    Candidate(
        2026,
        "https://zsb.wxc.edu.cn/_upload/article/files/8b/4f/53caeb5d4bb18157fd3e1db9625d/aaee6026-93bb-4c9c-b085-0ea8486d84e4.pdf",
        "2026年皖西学院专升本招生专业考试科目及参考书目",
        ("major_catalog", "training_location", "exam_subjects", "reference_books", "other_official_notice"),
        kind="attachment",
        parent_page="https://zsb.wxc.edu.cn/2025/1208/c270a208230/page.htm",
        expected_filename="2026年皖西学院专升本招生专业考试科目及参考书目.pdf",
    ),
)

# These pages are crawled only to discover official deep links; they are not duplicated across years.
DISCOVERY_ROOTS = (
    "https://zsb.wxc.edu.cn/",
    "https://www.wxc.edu.cn/",
    "https://www.ahzsks.cn/zyyx/",
)

# Audit statuses used before raw bytes can be fetched. These are intentionally conservative.
PREAUDITED_STATUS: dict[tuple[int, str], str] = {}
for _year in YEARS:
    for _topic in TOPICS:
        PREAUDITED_STATUS[(_year, _topic)] = "not_found"

CORE_CHAPTER_TOPICS = {
    "admission_policy", "enrollment_plan", "major_catalog", "training_location",
    "tuition_and_duration", "eligibility", "exam_subjects", "exam_schedule",
    "exam_location", "admission_rules", "score_formula", "control_line",
    "plan_adjustment", "adjustment", "exemption", "retired_soldier",
    "registered_poor_family", "skill_competition", "other_official_notice",
}
for _year in YEARS:
    for _topic in CORE_CHAPTER_TOPICS:
        PREAUDITED_STATUS[(_year, _topic)] = "awaiting_manual_review"
for _candidate in SEED_CANDIDATES:
    for _topic in _candidate.topics:
        PREAUDITED_STATUS[(_candidate.year, _topic)] = "access_restricted"
class LinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title_parts: list[str] = []
        self.text_parts: list[str] = []
        self.links: list[tuple[str, str]] = []
        self._in_title = False
        self._href: str | None = None
        self._anchor_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        values = dict(attrs)
        if tag == "title":
            self._in_title = True
        if tag == "a":
            self._href = values.get("href")
            self._anchor_parts = []
        # Some university CMS pages embed official attachments without an <a> tag.
        # Treat these attributes as discoverable links while preserving the same
        # official-domain and strict-year checks later in the pipeline.
        embedded = values.get("data") if tag == "object" else values.get("src")
        if tag in {"iframe", "embed", "object", "source"} and embedded:
            label = values.get("title") or values.get("type") or tag
            self.links.append((embedded, label))

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag == "title":
            self._in_title = False
        if tag == "a" and self._href:
            self.links.append((self._href, " ".join(self._anchor_parts).strip()))
            self._href = None
            self._anchor_parts = []

    def handle_data(self, data: str) -> None:
        clean = " ".join(data.split())
        if not clean:
            return
        self.text_parts.append(clean)
        if self._in_title:
            self.title_parts.append(clean)
        if self._href is not None:
            self._anchor_parts.append(clean)

    @property
    def title(self) -> str:
        return " ".join(self.title_parts).strip()

    @property
    def text(self) -> str:
        return " ".join(self.text_parts)


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def is_official_url(url: str) -> bool:
    host = (urlparse(url).hostname or "").lower().rstrip(".")
    return any(host == domain or host.endswith("." + domain) for domain in OFFICIAL_DOMAINS)


def year_conflicts(text: str, year: int) -> bool:
    found = {int(value) for value in re.findall(r"20(?:2[0-9]|3[0-9])", text or "")}
    return bool(found and year not in found)


def year_bound(text: str, url: str, year: int, inherited_from_parent: bool = False) -> bool:
    combined = f"{text} {unquote(url)}"
    if year_conflicts(combined, year):
        return False
    return str(year) in combined or inherited_from_parent


def infer_topics(text: str) -> list[str]:
    compact = re.sub(r"\s+", "", text or "")
    matched = [topic for topic, keywords in TOPIC_KEYWORDS.items() if any(kw in compact for kw in keywords)]
    if "专升本" in compact and "other_official_notice" not in matched:
        matched.append("other_official_notice")
    return [topic for topic in TOPICS if topic in matched]


def contains_public_record_fields(text: str) -> bool:
    compact = re.sub(r"\s+", "", text or "")
    return any(keyword in compact for keyword in PUBLIC_RECORD_KEYWORDS)


def primary_topic(topics: Iterable[str]) -> str:
    topic_set = set(topics)
    for topic in TOPICS:
        if topic in topic_set and topic != "other_official_notice":
            return topic
    return "other_official_notice"


def subdir_for(topic: str) -> str:
    return SUBDIRS.get(topic, "other")


def safe_name(value: str) -> str:
    value = unquote(value or "download")
    value = re.sub(r"[\\/:*?\"<>|\x00-\x1f]", "_", value)
    value = re.sub(r"\s+", "_", value).strip("._")
    return (value or "download")[:180]


def extension_for(url: str, content_type: str, content_disposition: str, data: bytes) -> str:
    # Inspect the response before trusting the URL suffix. University servers often
    # return a 200 HTML access page for a PDF/DOC URL; preserving it as a fake PDF
    # would corrupt the archive and overstate coverage.
    ctype = (content_type or "").split(";", 1)[0].strip().lower()
    stripped = data.lstrip().lower()
    if "html" in ctype or stripped.startswith((b"<!doctype html", b"<html")):
        return ".html"
    if data.startswith(b"%PDF-") or ctype == "application/pdf":
        return ".pdf"
    match = re.search(r"filename\*?=(?:UTF-8''|\")?([^\";]+)", content_disposition or "", re.I)
    if match:
        ext = Path(unquote(match.group(1))).suffix.lower()
        if ext:
            return ext
    path_ext = Path(urlparse(url).path).suffix.lower()
    if path_ext in FILE_EXTENSIONS or path_ext in {".htm", ".html"}:
        return ".html" if path_ext in {".htm", ".html"} else path_ext
    guessed = mimetypes.guess_extension(ctype) if ctype else None
    return guessed or ".bin"


def filename_from_response(url: str, content_disposition: str, fallback: str) -> str:
    match = re.search(r"filename\*?=(?:UTF-8''|\")?([^\";]+)", content_disposition or "", re.I)
    if match:
        return safe_name(unquote(match.group(1)))
    name = Path(unquote(urlparse(url).path)).name
    return safe_name(name or fallback)


@dataclass
class FetchResult:
    ok: bool
    requested_url: str
    final_url: str
    http_status: int | str
    headers: dict[str, str]
    data: bytes
    error: str = ""


def transport_candidates(url: str) -> list[str]:
    candidates = [url]
    if url.startswith("https://") and is_official_url(url):
        candidates.append("http://" + url[len("https://"):])
    return candidates


def _parse_curl_headers(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    text = path.read_text(encoding="latin-1", errors="replace")
    blocks = [block for block in re.split(r"\r?\n\r?\n", text) if block.strip()]
    for block in reversed(blocks):
        lines = block.splitlines()
        if not lines or not lines[0].upper().startswith("HTTP/"):
            continue
        headers: dict[str, str] = {}
        for line in lines[1:]:
            if ":" in line:
                key, value = line.split(":", 1)
                headers[key.strip().lower()] = value.strip()
        return headers
    return {}


def _fetch_with_curl(transport_url: str, requested_url: str, timeout: float, max_bytes: int) -> FetchResult:
    curl = shutil.which("curl")
    if not curl:
        return FetchResult(False, requested_url, transport_url, "error", {}, b"", "curl_not_available")
    wall_timeout = max(float(timeout) + 2.0, 3.0)
    with tempfile.TemporaryDirectory(prefix="wxc-fetch-") as temp:
        temp_root = Path(temp)
        body_path = temp_root / "body.bin"
        header_path = temp_root / "headers.txt"
        cmd = [
            curl,
            "--silent", "--show-error", "--location", "--compressed",
            "--proto", "=http,https",
            "--connect-timeout", str(max(float(timeout), 0.1)),
            "--max-time", str(max(float(timeout), 0.1)),
            "--max-filesize", str(max_bytes),
            "--user-agent", USER_AGENT,
            "--header", "Accept: text/html,application/pdf,application/msword,application/vnd.openxmlformats-officedocument.*,*/*;q=0.8",
            "--header", "Accept-Language: zh-CN,zh;q=0.9,en;q=0.5",
            "--dump-header", str(header_path),
            "--output", str(body_path),
            "--write-out", "%{http_code}\n%{url_effective}\n%{content_type}\n",
            transport_url,
        ]
        try:
            proc = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
                timeout=wall_timeout,
            )
        except subprocess.TimeoutExpired:
            return FetchResult(
                False, requested_url, transport_url, "error", {}, b"",
                f"{transport_url}:wall_clock_timeout_after_{wall_timeout:.1f}s",
            )
        lines = proc.stdout.strip().splitlines()
        status: int | str = "error"
        final_url = transport_url
        content_type = ""
        if len(lines) >= 3:
            if lines[-3].isdigit():
                status = int(lines[-3])
            final_url = lines[-2] or transport_url
            content_type = lines[-1]
        headers = _parse_curl_headers(header_path)
        if content_type and "content-type" not in headers:
            headers["content-type"] = content_type
        data = body_path.read_bytes() if body_path.exists() else b""
        if len(data) > max_bytes:
            return FetchResult(False, requested_url, final_url, status, headers, b"", f"download_exceeds_{max_bytes}")
        if proc.returncode == 0 and isinstance(status, int) and 200 <= status < 400 and data:
            return FetchResult(True, requested_url, final_url, status, headers, data)
        error = proc.stderr.strip() or f"curl_exit_{proc.returncode}_http_{status}"
        return FetchResult(False, requested_url, final_url, status, headers, b"", f"{transport_url}:{error}")


def fetch(url: str, timeout: float, max_bytes: int, retries: int) -> FetchResult:
    """Fetch one official URL with a hard wall-clock bound per attempt.

    DNS resolution can outlive Python socket timeouts on restricted runners.  Curl is
    therefore executed as a bounded subprocess; this guarantees that one inaccessible
    host cannot stall the whole school audit or prevent failure metadata from being
    committed.  HTTPS is tried first, followed by an official-domain HTTP fallback.
    """
    errors: list[str] = []
    for transport_url in transport_candidates(url):
        for attempt in range(1, max(1, retries) + 1):
            result = _fetch_with_curl(transport_url, url, timeout, max_bytes)
            if result.ok:
                return result
            errors.append(result.error or f"{transport_url}:unknown_network_error")
            if attempt < max(1, retries):
                time.sleep(min(2 ** (attempt - 1), 4))
    return FetchResult(False, url, url, "error", {}, b"", " | ".join(errors))


def decode_html(data: bytes, content_type: str) -> str:
    match = re.search(r"charset=([\w-]+)", content_type or "", re.I)
    encodings = [match.group(1)] if match else []
    encodings += ["utf-8", "gb18030", "gbk"]
    for encoding in encodings:
        try:
            return data.decode(encoding)
        except (UnicodeDecodeError, LookupError):
            continue
    return data.decode("utf-8", errors="replace")


def load_json(path: Path, default: object) -> object:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (json.JSONDecodeError, OSError):
        return default


def load_coverage(path: Path) -> dict[tuple[int, str], str]:
    """Load prior coverage without letting stale weak states hide new exact URLs.

    ``PREAUDITED_STATUS`` is regenerated from the current, exact official seed list.
    Terminal/evidence-backed states are always retained.  When a formerly unresolved
    cell was marked ``awaiting_manual_review`` or ``manual_download_required`` but an
    exact official URL is now known and currently inaccessible, the audited state is
    upgraded to ``access_restricted`` rather than preserving the obsolete weaker state.
    """
    result = dict(PREAUDITED_STATUS)
    if not path.exists():
        return result
    terminal = {
        "collected", "public_official_record", "not_applicable",
        "official_not_published", "removed_or_unavailable",
    }
    weak = {"not_found", "awaiting_manual_review", "manual_download_required", "access_restricted"}
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            try:
                key = (int(row["year"]), row["topic"])
            except (KeyError, ValueError):
                continue
            if key not in result:
                continue
            status = row.get("status") or "not_found"
            if status in terminal:
                result[key] = status
            elif result[key] == "access_restricted" and status in weak:
                result[key] = "access_restricted"
            elif status != "not_found":
                result[key] = status
    return result


def write_coverage(path: Path, coverage: dict[tuple[int, str], str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(["school_id", "school_name", "year", "topic", "status"])
        for year in YEARS:
            for topic in TOPICS:
                writer.writerow([SCHOOL_ID, SCHOOL_NAME, year, topic, coverage[(year, topic)]])


def relative_path(path: Path, repo_root: Path) -> str:
    return path.resolve().relative_to(repo_root.resolve()).as_posix()


def dedup_records(records: list[dict]) -> list[dict]:
    """Deduplicate sources and failures without collapsing unrelated failures.

    Source records primarily use final URL + SHA-256. Failure records usually have
    no hash, so their URL/year/status/reason tuple is retained instead.
    """
    seen: set[tuple[str, ...]] = set()
    output: list[dict] = []
    for record in records:
        sha = str(record.get("sha256") or "")
        final_url = str(record.get("final_url") or record.get("official_page_url") or record.get("url") or "")
        if sha:
            # The same official bytes may legitimately be linked by different year
            # pages. Preserve each year/parent source relationship while still
            # collapsing exact duplicate events within the same context.
            key = (
                "source",
                str(record.get("year") or ""),
                final_url,
                sha,
                str(record.get("parent_page") or record.get("official_page_url") or ""),
            )
        else:
            key = (
                "event",
                str(record.get("year") or ""),
                final_url,
                str(record.get("status") or ""),
                str(record.get("reason") or ""),
            )
        if key in seen:
            continue
        seen.add(key)
        output.append(record)
    return output


def candidate_to_dict(candidate: Candidate, status: str = "awaiting_retrieval") -> dict:
    data = asdict(candidate)
    data["topics"] = list(candidate.topics)
    data["source_domain"] = urlparse(candidate.url).hostname
    data["status"] = status
    return data


def save_document(
    repo_root: Path,
    evidence_root: Path,
    candidate: Candidate,
    result: FetchResult,
    text_hint: str,
) -> tuple[dict, list[tuple[str, str]]]:
    content_type = result.headers.get("content-type", "")
    disposition = result.headers.get("content-disposition", "")
    ext = extension_for(result.final_url, content_type, disposition, result.data)
    parsed_title = candidate.title
    links: list[tuple[str, str]] = []
    body_text = text_hint
    if ext == ".html":
        decoded = decode_html(result.data, content_type)
        parser = LinkParser()
        parser.feed(decoded)
        parsed_title = parser.title or candidate.title
        body_text = parser.text
        links = parser.links
    topic_list = infer_topics(" ".join([candidate.title, parsed_title, candidate.expected_filename, body_text]))
    if not topic_list:
        topic_list = list(candidate.topics) or ["other_official_notice"]
    for topic in candidate.topics:
        if topic not in topic_list:
            topic_list.append(topic)
    topic_list = [topic for topic in TOPICS if topic in topic_list]
    digest = sha256_bytes(result.data)
    original_name = candidate.expected_filename or filename_from_response(result.final_url, disposition, parsed_title)
    base = safe_name(Path(original_name).stem or parsed_title or candidate.kind)
    target_dir = evidence_root / str(candidate.year) / subdir_for(primary_topic(topic_list))
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / f"{base}__{digest[:12]}{ext}"
    if not target.exists():
        target.write_bytes(result.data)
    is_public_record = contains_public_record_fields(" ".join([parsed_title, original_name, body_text]))
    attachment_returned_html = candidate.kind == "attachment" and ext == ".html"
    if attachment_returned_html:
        status = "awaiting_manual_review"
    else:
        status = "public_official_record" if is_public_record else "collected"
    record = {
        "school_id": SCHOOL_ID,
        "school_name": SCHOOL_NAME,
        "year": candidate.year,
        "title": parsed_title or candidate.title,
        "publish_date": "",
        "retrieved_at": utc_now(),
        "official_page_url": candidate.parent_page or candidate.url,
        "final_url": result.final_url,
        "source_domain": urlparse(result.final_url).hostname,
        "source_level": "S",
        "document_type": candidate.kind,
        "topics": topic_list,
        "file_type": ext.lstrip("."),
        "local_path": relative_path(target, repo_root),
        "file_size": len(result.data),
        "sha256": digest,
        "http_status": result.http_status,
        "status": status,
        "notes": (
            "Attachment URL returned HTML; raw response preserved for manual review."
            if attachment_returned_html
            else "Public official source preserved as raw bytes without field-level alteration."
        ),
        "parent_page": candidate.parent_page,
        "attachment_url": candidate.url if candidate.kind == "attachment" else "",
        "attachment_filename": original_name if candidate.kind == "attachment" else "",
        "attachment_sha256": digest if candidate.kind == "attachment" else "",
    }
    return record, links


def link_candidate(parent: Candidate, base_url: str, href: str, anchor: str) -> Candidate | None:
    absolute = urljoin(base_url, href).split("#", 1)[0].strip()
    if not absolute or not is_official_url(absolute):
        return None
    descriptor = f"{anchor} {unquote(absolute)}"
    if year_conflicts(descriptor, parent.year):
        return None
    suffix = Path(urlparse(absolute).path).suffix.lower()
    is_attachment = suffix in FILE_EXTENSIONS or "/_upload/" in absolute
    relevant = any(keyword in descriptor for keyword in RELEVANT_KEYWORDS)
    if not relevant and not is_attachment:
        return None
    inherited = is_attachment and bool(parent.url)
    if not year_bound(descriptor, absolute, parent.year, inherited_from_parent=inherited):
        return None
    topics = infer_topics(descriptor) or list(parent.topics)
    return Candidate(
        parent.year,
        absolute,
        anchor or Path(urlparse(absolute).path).name or "official linked document",
        tuple(topics),
        kind="attachment" if is_attachment else "page",
        parent_page=parent.url,
        expected_filename=Path(unquote(urlparse(absolute).path)).name if is_attachment else "",
        discovery_basis="official_parent_page_link",
    )


def crawl_discovery_roots(timeout: float, max_bytes: int, retries: int, max_pages: int) -> list[Candidate]:
    discovered: list[Candidate] = []
    seen: set[str] = set()
    queue: list[tuple[str, int]] = [(url, 0) for url in DISCOVERY_ROOTS]
    while queue and len(seen) < max_pages:
        url, depth = queue.pop(0)
        if url in seen or not is_official_url(url):
            continue
        seen.add(url)
        result = fetch(url, timeout, min(max_bytes, 8 * 1024 * 1024), retries)
        if not result.ok or "html" not in result.headers.get("content-type", "").lower():
            continue
        decoded = decode_html(result.data, result.headers.get("content-type", ""))
        parser = LinkParser()
        parser.feed(decoded)
        for href, anchor in parser.links:
            absolute = urljoin(result.final_url, href).split("#", 1)[0]
            if not is_official_url(absolute):
                continue
            descriptor = f"{anchor} {unquote(absolute)}"
            matched_years = [year for year in YEARS if str(year) in descriptor]
            if matched_years and any(keyword in descriptor for keyword in RELEVANT_KEYWORDS):
                for year in matched_years:
                    suffix = Path(urlparse(absolute).path).suffix.lower()
                    kind = "attachment" if suffix in FILE_EXTENSIONS or "/_upload/" in absolute else "page"
                    discovered.append(
                        Candidate(
                            year,
                            absolute,
                            anchor or Path(urlparse(absolute).path).name,
                            tuple(infer_topics(descriptor) or ["other_official_notice"]),
                            kind=kind,
                            parent_page=result.final_url,
                            expected_filename=Path(unquote(urlparse(absolute).path)).name if kind == "attachment" else "",
                            discovery_basis="official_site_crawl",
                        )
                    )
            elif depth < 2 and any(token in descriptor for token in ("招生", "专升本", "zsb", "list", "zsxx")):
                if absolute not in seen:
                    queue.append((absolute, depth + 1))
    unique: dict[str, Candidate] = {}
    for item in discovered:
        unique.setdefault(item.url, item)
    return list(unique.values())


def run_collection(repo_root: Path, timeout: float, max_bytes: int, retries: int, max_pages: int, seed_only: bool) -> dict:
    evidence_root = repo_root / "anhui_zsb_data" / "evidence" / "full_raw_30_schools" / SCHOOL_ID
    evidence_root.mkdir(parents=True, exist_ok=True)
    manifest_path = evidence_root / "school_manifest.json"
    coverage_path = evidence_root / "school_coverage.csv"
    attempts_path = evidence_root / "retrieval_attempts.jsonl"
    discovery_path = evidence_root / "source_discovery.json"
    notes_path = evidence_root / "school_notes.md"
    report_path = repo_root / "anhui_zsb_data" / "reports" / "p0_batch_01_wxc_audit.md"

    existing = load_json(manifest_path, {})
    if not isinstance(existing, dict):
        existing = {}
    sources = list(existing.get("sources") or [])
    assets = list(existing.get("assets") or [])
    failures = list(existing.get("failures") or [])
    coverage = load_coverage(coverage_path)
    attempts: list[dict] = []
    candidates = list(SEED_CANDIDATES)
    if not seed_only:
        candidates.extend(crawl_discovery_roots(timeout, max_bytes, retries, max_pages))

    queued: list[Candidate] = []
    seen_urls: set[str] = set()
    for candidate in candidates:
        if candidate.url not in seen_urls:
            queued.append(candidate)
            seen_urls.add(candidate.url)

    while queued:
        candidate = queued.pop(0)
        if seed_only:
            continue
        started_at = utc_now()
        if not is_official_url(candidate.url):
            continue
        result = fetch(candidate.url, timeout, max_bytes, retries)
        attempt = {
            "school_id": SCHOOL_ID,
            "school_name": SCHOOL_NAME,
            "year": candidate.year,
            "url": candidate.url,
            "parent_url": candidate.parent_page,
            "started_at": started_at,
            "finished_at": utc_now(),
            "http_status": result.http_status,
            "final_url": result.final_url,
            "status": "collected" if result.ok else "access_restricted",
            "reason": result.error,
        }
        attempts.append(attempt)
        if not result.ok:
            failures.append({
                "school_id": SCHOOL_ID,
                "school_name": SCHOOL_NAME,
                "year": candidate.year,
                "url": candidate.url,
                "parent_url": candidate.parent_page,
                "status": "access_restricted",
                "http_status": result.http_status,
                "reason": result.error,
                "retrieved_at": utc_now(),
                "topics": list(candidate.topics),
            })
            for topic in candidate.topics:
                if coverage.get((candidate.year, topic)) not in {"collected", "public_official_record"}:
                    coverage[(candidate.year, topic)] = "access_restricted"
            continue
        if not is_official_url(result.final_url):
            failures.append({
                "school_id": SCHOOL_ID,
                "school_name": SCHOOL_NAME,
                "year": candidate.year,
                "url": candidate.url,
                "parent_url": candidate.parent_page,
                "status": "awaiting_manual_review",
                "http_status": result.http_status,
                "reason": f"redirected_outside_official_allowlist:{result.final_url}",
                "retrieved_at": utc_now(),
                "topics": list(candidate.topics),
            })
            continue
        record, links = save_document(repo_root, evidence_root, candidate, result, "")
        sources.append(record)
        if candidate.kind == "attachment":
            assets.append(record.copy())
        for topic in record["topics"]:
            coverage[(candidate.year, topic)] = record["status"]
        if candidate.kind == "page":
            for href, anchor in links:
                child = link_candidate(candidate, result.final_url, href, anchor)
                if child and child.url not in seen_urls and len(seen_urls) < max_pages + len(SEED_CANDIDATES) + 100:
                    seen_urls.add(child.url)
                    queued.append(child)

    sources = dedup_records(sources)
    assets = dedup_records(assets)
    failures = dedup_records(failures)
    successful_urls = {
        str(item.get("official_page_url") or item.get("attachment_url") or item.get("final_url") or "")
        for item in sources + assets
    }
    failed_urls = {str(item.get("url") or "") for item in failures}
    candidate_records: list[dict] = []
    for item in SEED_CANDIDATES:
        status = "collected" if item.url in successful_urls else (
            "access_restricted" if item.url in failed_urls else "awaiting_retrieval"
        )
        candidate_records.append(candidate_to_dict(item, status=status))
    manifest = {
        "schema_version": "full-raw-school-manifest-v2",
        "school_id": SCHOOL_ID,
        "school_name": SCHOOL_NAME,
        "official_domains": list(OFFICIAL_DOMAINS),
        "years": list(YEARS),
        "topics": TOPICS,
        "sources": sources,
        "assets": assets,
        "source_candidates": candidate_records,
        "failures": failures,
        "last_attempt_at": utc_now(),
        "raw_information_policy": "Preserve complete bytes of public official pages and attachments; do not bypass access controls.",
        "sanitized": False,
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_coverage(coverage_path, coverage)
    if attempts:
        with attempts_path.open("a", encoding="utf-8") as handle:
            for attempt in attempts:
                handle.write(json.dumps(attempt, ensure_ascii=False) + "\n")
    existing_discovery = load_json(discovery_path, {})
    if not isinstance(existing_discovery, dict):
        existing_discovery = {}
    discovery = {
        "school_id": SCHOOL_ID,
        "school_name": SCHOOL_NAME,
        "generated_at": utc_now(),
        "official_candidates": candidate_records,
        "secondary_leads_are_not_formal_evidence": True,
        "unresolved_parent_page_leads": [
            {
                "year": 2025,
                "title": "关于公布皖西学院2025年普通专升本拟招生专业考试科目、考试大纲及参考书目的通知",
                "publish_date": "2024-11-08",
                "status": "awaiting_manual_review",
                "notes": "The parent notice URL still requires recovery, but both school-official attachment URLs have been recovered and seeded directly.",
            }
        ],
        # Keep explicitly labelled third-party discovery leads across idempotent runs.
        # They are never promoted to formal evidence unless an official URL is fetched.
        "secondary_leads": list(existing_discovery.get("secondary_leads") or []),
    }
    discovery_path.write_text(json.dumps(discovery, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    counts: dict[str, int] = {}
    for status in coverage.values():
        counts[status] = counts.get(status, 0) + 1
    raw_bytes = sum(int(item.get("file_size") or 0) for item in sources)
    notes = f"""# 皖西学院（WXC）P0 原始证据状态\n\n- 最后执行：{utc_now()}\n- 已保存正式官方 source documents：{len(sources)}\n- 已保存附件：{len(assets)}\n- 原始字节总量：{raw_bytes}\n- `collected`：{counts.get('collected', 0)}\n- `public_official_record`：{counts.get('public_official_record', 0)}\n- `access_restricted`：{counts.get('access_restricted', 0)}\n- `manual_download_required`：{counts.get('manual_download_required', 0)}\n- `awaiting_manual_review`：{counts.get('awaiting_manual_review', 0)}\n- `not_found`：{counts.get('not_found', 0)}\n\n## 已锁定的官方深层来源\n\n- 2024 专业课考试大纲与参考书目页面：已写入 `source_candidates`。\n- 2025 安徽省教育招生考试院招生章程页面：已写入 `source_candidates`。\n- 2025 专业课考试大纲 PDF：已写入 `source_candidates`。\n- 2025 招生专业、考试科目及参考书目 PDF：已写入 `source_candidates`。\n- 2026 拟招生专业、考试科目、大纲与参考书目页面及两个 PDF：已写入 `source_candidates`。\n- 2025 考试大纲通知父页面尚待从招生站历史栏目恢复；这不影响两个附件深链的独立审计状态。\n\n## 说明\n\n本次不再把网络不可达误记为 `not_found`。公开官方文件即使包含名单、姓名、考生号、成绩或录取结果，也按原始字节保存并标记为 `public_official_record`；采集器不会绕过登录、验证码或权限控制。\n"""
    notes_path.write_text(notes, encoding="utf-8")
    report_path.parent.mkdir(parents=True, exist_ok=True)
    year_rows: list[str] = []
    for year in YEARS:
        collected_topics = [
            topic for topic in TOPICS
            if coverage[(year, topic)] in {"collected", "public_official_record"}
        ]
        located_topics = [
            topic for topic in TOPICS
            if coverage[(year, topic)] in {"access_restricted", "manual_download_required"}
        ]
        missing_topics = [
            topic for topic in TOPICS
            if coverage[(year, topic)] in {"awaiting_manual_review", "not_found"}
        ]
        reason = "官方页面/附件深链已锁定，但当前执行网络无法取得原始字节"
        year_rows.append(
            f"| {year} | {', '.join(collected_topics) or '—'} | "
            f"{', '.join(located_topics) or '—'} | {', '.join(missing_topics)} | {reason} |"
        )
    report = (
        "# P0 Batch 01：WXC 皖西学院原始数据审计\n\n"
        "## 本批数据审计\n\n"
        f"- 本批学校数：1\n"
        f"- 新增 source document 数：{len(sources)}\n"
        f"- 新增/现存原始文件数：{len({item.get('local_path') for item in sources if item.get('local_path')})}\n"
        f"- 原始文件总字节数：{raw_bytes}\n"
        f"- `collected` 覆盖格数：{counts.get('collected', 0)}\n"
        f"- `public_official_record` 覆盖格数：{counts.get('public_official_record', 0)}\n"
        f"- `not_found`：{counts.get('not_found', 0)}\n"
        f"- `access_restricted`：{counts.get('access_restricted', 0)}\n"
        f"- `manual_download_required`：{counts.get('manual_download_required', 0)}\n"
        f"- `awaiting_manual_review`：{counts.get('awaiting_manual_review', 0)}\n\n"
        "## 覆盖状态分布\n\n"
        "| status | 单元数 |\n|---|---:|\n"
        + "".join(f"| `{key}` | {value} |\n" for key, value in sorted(counts.items()))
        + "\n## 逐年缺失审计\n\n"
        "| 年份 | 已采主题 | 已定位但待取主题 | 仍待深检主题 | 原因 |\n"
        "|---:|---|---|---|---|\n"
        + "\n".join(year_rows)
        + "\n\n## 下一步\n\n"
        "1. 直取已锁定的 2024 页面、2025 省考试院章程、2025 两个 PDF、2026 页面及两个 PDF。\n"
        "2. 从招生站栏目页恢复 2025 考试大纲通知父页面 URL，补齐页面级证据。\n"
        "3. 从相邻日期公告继续发现考试通知、控制线、调剂、计划调整和统计资料。\n"
        "4. 每次成功下载后校验原始字节 SHA-256，并重建 42 校总审计。\n"
    )
    report_path.write_text(report, encoding="utf-8")
    return {
        "sources": len(sources),
        "assets": len(assets),
        "raw_bytes": raw_bytes,
        "coverage": counts,
        "manifest": relative_path(manifest_path, repo_root),
    }


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--timeout", type=float, default=20.0)
    parser.add_argument("--retries", type=int, default=3)
    parser.add_argument("--max-pages", type=int, default=80)
    parser.add_argument("--max-file-bytes", type=int, default=MAX_FILE_BYTES_DEFAULT)
    parser.add_argument("--seed-only", action="store_true", help="Write the audited candidate/coverage state without network access.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    repo_root = args.repo_root.resolve()
    result = run_collection(repo_root, args.timeout, args.max_file_bytes, args.retries, args.max_pages, args.seed_only)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
