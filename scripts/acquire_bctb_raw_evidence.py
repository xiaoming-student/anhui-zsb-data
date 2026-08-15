#!/usr/bin/env python3
"""Acquire official 2024-2026 Anhui zhuanshengben evidence for BCTB.

Only official bctb.edu.cn bytes are archived. Candidate-level pages and attachments
are excluded before writing. Every raw file receives SHA-256 metadata and a strict
explicit-year binding inherited from the audited target URL.
"""
from __future__ import annotations

import csv
import hashlib
import json
import mimetypes
import os
import re
import shutil
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import unquote, urljoin, urlparse
from xml.etree import ElementTree

import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

ROOT = Path(os.environ.get("REPO_ROOT", ".")).resolve()
SCHOOL_ID = "BCTB"
SCHOOL_NAME = "蚌埠工商学院"
OFFICIAL_DOMAIN = "bctb.edu.cn"
YEARS = (2024, 2025, 2026)
OUT = ROOT / "anhui_zsb_data" / "evidence" / "full_raw_30_schools" / SCHOOL_ID
REPORT_DIR = ROOT / "anhui_zsb_data" / "reports"
BATCH_DIR = ROOT / "anhui_zsb_data" / "evidence" / "full_raw_30_schools" / "_acquisition_reports" / "p0_batch_02"
RETRIEVED_AT = datetime.now(timezone.utc).isoformat()
MAX_BYTES = 100 * 1024 * 1024

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

KEYWORDS = {
    "admission_policy": ["招生章程", "招生简章", "招生实施办法"],
    "enrollment_plan": ["招生计划", "分专业计划", "招生方案", "拟招生专业"],
    "major_catalog": ["招生专业范围", "专业招生范围", "招生范围", "拟招生专业"],
    "training_location": ["联合培养", "培养地点", "办学地点", "培养校区"],
    "tuition_and_duration": ["学费", "学制", "住宿费"],
    "eligibility": ["报名条件", "报考条件", "报考资格", "资格审核"],
    "exam_subjects": ["考试科目", "专业课1", "专业课2", "公共课考试科目"],
    "exam_syllabus": ["考试大纲", "测试大纲", "考查大纲"],
    "reference_books": ["参考书目", "参考教材", "主要参考书"],
    "exam_schedule": ["考试时间", "时间安排", "面试时间", "考查时间"],
    "exam_location": ["考试地点", "面试地点", "考点", "考场", "格物楼"],
    "admission_rules": ["录取规则", "同分排序", "依序录取"],
    "score_formula": ["成绩计算", "综合成绩", "总成绩", "计分公式"],
    "control_line": ["合格线", "控制线", "专业课总分不低于"],
    "admission_min_score": ["最低成绩", "最低录取分", "最低投档分"],
    "admission_max_score": ["最高录取分", "录取最高分"],
    "admission_average_score": ["平均录取分", "录取平均分"],
    "application_statistics": ["报名人数", "报考人数", "报考统计"],
    "qualified_statistics": ["资格审核通过人数", "资格通过人数", "合格人数"],
    "admitted_statistics": ["录取人数", "录取统计"],
    "registered_statistics": ["报到人数", "注册人数"],
    "plan_adjustment": ["计划调整", "调整计划", "扩招", "缩招"],
    "adjustment": ["校外调剂", "调剂计划", "第二轮调剂", "征集志愿", "补录"],
    "exemption": ["免试", "免文化课"],
    "retired_soldier": ["退役大学生士兵", "退役士兵"],
    "registered_poor_family": ["建档立卡"],
    "skill_competition": ["技能大赛", "职业技能大赛", "鼓励政策"],
    "other_official_notice": ["专升本"],
}

PRIVATE_LABELS = [
    "拟录取名单", "预录取名单", "录取人员名单", "考生名单", "面试名单",
    "审核名单", "免试名单", "成绩名单", "资格审核结果名单", "面试成绩公示",
    "专项计划考生名单",
]
PRIVATE_FIELDS = ["身份证号", "考生号", "准考证号", "手机号"]
ALLOWED_EXTS = {
    ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".csv", ".json", ".txt",
    ".jpg", ".jpeg", ".png", ".tif", ".tiff", ".zip",
}

@dataclass(frozen=True)
class Target:
    year: int
    url: str
    label: str
    hints: tuple[str, ...] = ()

TARGETS = (
    Target(2024, "https://zs.bctb.edu.cn/2024/0321/c1031a24235/page.psp", "蚌埠工商学院2024年普通高校专升本招生章程", ("admission_policy",)),
    Target(2024, "https://zs.bctb.edu.cn/2024/0531/c1028a25201/page.psp", "蚌埠工商学院2024年专升本校外调剂免文化课退役士兵职业适应性综合考查通知", ("adjustment", "exemption", "retired_soldier", "exam_schedule", "exam_location", "admission_rules", "control_line")),
    Target(2025, "https://zs.bctb.edu.cn/2024/1107/c1028a27024/page.psp", "蚌埠工商学院2025年普通专升本招生方案", ("enrollment_plan", "major_catalog", "exam_subjects", "exam_syllabus")),
    Target(2025, "https://zs.bctb.edu.cn/2025/0310/c1031a28046/page.psp", "蚌埠工商学院2025年普通高校专升本招生章程", ("admission_policy",)),
    Target(2025, "https://zs.bctb.edu.cn/2025/0526/c1028a28880/page.psp", "蚌埠工商学院2025年普通专升本招生考试校外调剂通知", ("adjustment", "enrollment_plan", "retired_soldier", "registered_poor_family", "control_line")),
    Target(2025, "https://zs.bctb.edu.cn/2025/0530/c1028a28977/page.htm", "蚌埠工商学院2025年校外调剂免文化课退役士兵职业适应性综合考查通知", ("adjustment", "exemption", "retired_soldier", "exam_schedule", "exam_location", "admission_rules", "control_line")),
    Target(2025, "https://zs.bctb.edu.cn/2025/0604/c1028a28996/page.htm", "蚌埠工商学院2025年校外调剂免文化课退役士兵职业适应性综合考查成绩查询通知", ("adjustment", "exemption", "retired_soldier", "other_official_notice")),
    Target(2025, "https://zs.bctb.edu.cn/2025/0609/c1028a29033/page.psp", "蚌埠工商学院2025年普通高校专升本校外调剂拟录取结果查询及最低成绩", ("adjustment", "admission_min_score", "control_line")),
    Target(2026, "https://zs.bctb.edu.cn/2025/1117/c1028a31309/page.psp", "蚌埠工商学院2026年普通专升本招生方案", ("enrollment_plan", "major_catalog", "exam_subjects", "exam_syllabus")),
    Target(2026, "https://zs.bctb.edu.cn/2026/0131/c1028a33852/page.psp", "蚌埠工商学院2026年专升本招生分专业计划", ("enrollment_plan", "major_catalog")),
    Target(2026, "https://zs.bctb.edu.cn/2026/0318/c1031a34139/page.psp", "蚌埠工商学院2026年普通高校专升本招生章程", ("admission_policy",)),
    Target(2026, "https://zs.bctb.edu.cn/87/87/c1028a34695/page.htm", "蚌埠工商学院2026年普通高校专升本专业课成绩查询及复核通知", ("other_official_notice",)),
    Target(2026, "https://zs.bctb.edu.cn/8b/6a/c1028a35690/page.htm", "蚌埠工商学院2026年第二轮校外调剂拟录取结果查询及最低成绩", ("adjustment", "admission_min_score", "control_line")),
)

KNOWN_PRIVACY_EXCLUSIONS = [
    {
        "year": 2025,
        "url": "https://zs.bctb.edu.cn/2025/0326/c1028a28226/page.psp",
        "title": "2025年免文化课退役士兵职业适应性综合考查通知（正文含考生号和姓名）",
        "status": "candidate_personal_data_excluded",
        "reason": "page contains candidate numbers and names",
    },
    {
        "year": 2026,
        "url": "https://zs.bctb.edu.cn/8a/55/c1028a35413/page.htm",
        "title": "2026年校外调剂免文化课退役士兵面试成绩公示",
        "status": "candidate_personal_data_excluded",
        "reason": "page contains candidate numbers, names and individual scores",
    },
]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def short_id(value: str) -> str:
    return hashlib.sha1(value.encode("utf-8", "replace")).hexdigest()[:10]


def official(url: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    return host == OFFICIAL_DOMAIN or host.endswith("." + OFFICIAL_DOMAIN)


def safe_name(value: str) -> str:
    value = unquote(value or "download")
    value = re.sub(r'[\\/:*?"<>|\x00-\x1f]', "_", value).strip(" .")
    return (value or "download")[:180]


def session() -> requests.Session:
    value = requests.Session()
    retry = Retry(total=3, connect=3, read=3, status=3, backoff_factor=0.8, status_forcelist=(429, 500, 502, 503, 504), allowed_methods=frozenset({"GET", "HEAD"}))
    value.mount("https://", HTTPAdapter(max_retries=retry, pool_connections=20, pool_maxsize=20))
    value.headers.update({
        "User-Agent": "Mozilla/5.0 (compatible; AnhuiZSBDataResearch/1.0; official raw evidence archive)",
        "Accept": "*/*",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.6",
    })
    return value


HTTP = session()


def fetch(url: str) -> tuple[bytes | None, dict[str, Any]]:
    try:
        response = HTTP.get(url, timeout=(8, 35), allow_redirects=True, stream=True)
        content = bytearray()
        for chunk in response.iter_content(1024 * 128):
            if not chunk:
                continue
            content.extend(chunk)
            if len(content) > MAX_BYTES:
                return None, {
                    "http_status": response.status_code,
                    "final_url": response.url,
                    "content_type": response.headers.get("Content-Type", ""),
                    "status": "manual_download_required",
                    "reason": "response exceeds 100 MiB",
                }
        body = bytes(content)
        meta = {
            "http_status": response.status_code,
            "final_url": response.url,
            "content_type": response.headers.get("Content-Type", ""),
            "content_disposition": response.headers.get("Content-Disposition", ""),
            "file_size": len(body),
            "sha256": digest(body),
        }
        if response.status_code >= 400:
            return None, meta
        if not official(response.url):
            meta["reason"] = "redirected outside official domain"
            return None, meta
        return body, meta
    except Exception as exc:
        return None, {"http_status": "error", "final_url": url, "reason": repr(exc)}


def decode_html(body: bytes) -> tuple[BeautifulSoup, str]:
    soup = BeautifulSoup(body, "html.parser")
    return soup, soup.get_text("\n", strip=True)


def privacy_label(text: str) -> str | None:
    compact = re.sub(r"\s+", "", text or "")
    return next((term for term in PRIVATE_LABELS if term in compact), None)


def privacy_record_pattern(text: str) -> str | None:
    compact = re.sub(r"\s+", "", text or "")
    if "姓名" in compact and any(field in compact for field in PRIVATE_FIELDS):
        if len(re.findall(r"(?<!\d)\d{10,18}(?!\d)", compact)) >= 2:
            return "candidate-record-pattern"
    return None


def topics_for(text: str, hints: Iterable[str] = ()) -> list[str]:
    compact = re.sub(r"\s+", "", text or "")
    found = set(hints)
    for topic, words in KEYWORDS.items():
        if any(word in compact for word in words):
            found.add(topic)
    if "专升本" in compact:
        found.add("other_official_notice")
    return [topic for topic in TOPICS if topic in found]


def primary_topic(topics: Iterable[str]) -> str:
    values = set(topics)
    for topic in TOPICS:
        if topic in values and topic != "other_official_notice":
            return topic
    return "other_official_notice"


def folder(topic: str) -> str:
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


def published_date(text: str) -> str:
    match = re.search(r"(?:发布时间|发布日期)[：:]?\s*(20\d{2})[-年/.](\d{1,2})[-月/.](\d{1,2})", text)
    if not match:
        return ""
    return f"{int(match.group(1)):04d}-{int(match.group(2)):02d}-{int(match.group(3)):02d}"


def extension(url: str, meta: dict[str, Any], body: bytes | None = None) -> str:
    ext = Path(urlparse(meta.get("final_url") or url).path).suffix.lower()
    if ext in ALLOWED_EXTS:
        return ext
    disposition = meta.get("content_disposition", "")
    match = re.search(r"filename\*?=(?:UTF-8''|\")?([^\";]+)", disposition, re.I)
    if match:
        ext = Path(unquote(match.group(1))).suffix.lower()
        if ext in ALLOWED_EXTS:
            return ext
    ctype = meta.get("content_type", "").lower().split(";", 1)[0]
    mapping = {
        "application/pdf": ".pdf", "application/msword": ".doc",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
        "application/vnd.ms-excel": ".xls",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ".xlsx",
        "text/csv": ".csv", "application/json": ".json", "text/plain": ".txt",
        "image/jpeg": ".jpg", "image/png": ".png", "image/tiff": ".tif",
        "application/zip": ".zip",
    }
    if ctype in mapping:
        return mapping[ctype]
    if body and body.startswith(b"%PDF-"):
        return ".pdf"
    if body and body.startswith(b"PK\x03\x04"):
        return ".zip"
    return ""


def original_filename(url: str, meta: dict[str, Any]) -> str:
    disposition = meta.get("content_disposition", "")
    match = re.search(r"filename\*?=(?:UTF-8''|\")?([^\";]+)", disposition, re.I)
    if match:
        return safe_name(match.group(1))
    return safe_name(Path(urlparse(meta.get("final_url") or url).path).name)


def docx_text(data: bytes) -> str:
    try:
        from io import BytesIO
        with zipfile.ZipFile(BytesIO(data)) as archive:
            names = [name for name in archive.namelist() if name.startswith("word/") and name.endswith(".xml")]
            chunks: list[str] = []
            for name in names:
                root = ElementTree.fromstring(archive.read(name))
                for node in root.iter():
                    if node.tag.endswith("}t") and node.text:
                        chunks.append(node.text)
            return "\n".join(chunks)
    except Exception:
        return ""


def candidate_links(soup: BeautifulSoup, final_url: str) -> list[dict[str, str]]:
    output: list[dict[str, str]] = []
    seen: set[str] = set()
    for node in soup.find_all(["a", "img", "iframe", "embed", "object"]):
        raw = node.get("href") or node.get("src") or node.get("data")
        if not raw:
            continue
        url = urljoin(final_url, raw).split("#", 1)[0].strip()
        if not url.startswith(("http://", "https://")) or not official(url) or url in seen:
            continue
        path = urlparse(url).path.lower()
        ext = Path(path).suffix.lower()
        is_article_upload = "/_upload/article/" in path
        is_attachment = ext in ALLOWED_EXTS and (node.name != "img" or is_article_upload)
        if not is_attachment:
            continue
        if node.name == "img" and not is_article_upload:
            continue
        label = node.get_text(" ", strip=True) or node.get("title") or node.get("alt") or Path(path).name
        seen.add(url)
        output.append({"url": url, "label": label[:500], "kind": "inline_image" if node.name == "img" else "attachment"})
    # Some Webplus pages expose attachment paths only inside scripts.
    html = str(soup)
    for raw in re.findall(r"(?:https?://[^\"'<>\s]+|/_upload/article/[^\"'<>\s]+)", html, re.I):
        url = urljoin(final_url, raw.replace("&amp;", "&")).split("#", 1)[0]
        ext = Path(urlparse(url).path).suffix.lower()
        if official(url) and ext in ALLOWED_EXTS and url not in seen:
            seen.add(url)
            output.append({"url": url, "label": Path(urlparse(url).path).name, "kind": "attachment"})
    return output


def prepare() -> None:
    if OUT.exists():
        shutil.rmtree(OUT)
    for year in YEARS:
        for name in ("admission_policy", "enrollment_plan", "exam_syllabus", "admission_scores", "statistics", "adjustments", "other"):
            (OUT / str(year) / name).mkdir(parents=True, exist_ok=True)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    BATCH_DIR.mkdir(parents=True, exist_ok=True)


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> None:
    prepare()
    sources: list[dict[str, Any]] = []
    assets: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    privacy: list[dict[str, Any]] = list(KNOWN_PRIVACY_EXCLUSIONS)
    attachment_jobs: list[dict[str, Any]] = []

    def get_target(target: Target) -> dict[str, Any]:
        body, meta = fetch(target.url)
        return {"target": target, "body": body, "meta": meta}

    results: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = [pool.submit(get_target, target) for target in TARGETS]
        for future in as_completed(futures):
            results.append(future.result())

    for result in sorted(results, key=lambda item: (item["target"].year, item["target"].url)):
        target: Target = result["target"]
        body: bytes | None = result["body"]
        meta: dict[str, Any] = result["meta"]
        if body is None:
            status = meta.get("status") or ("removed_or_unavailable" if meta.get("http_status") in (404, 410) else "access_restricted")
            failures.append({"year": target.year, "url": target.url, "title": target.label, "topics": list(target.hints), "status": status, "http_status": meta.get("http_status"), "reason": meta.get("reason", "")})
            continue
        soup, text = decode_html(body)
        title = soup.title.get_text(" ", strip=True) if soup.title else target.label
        privacy_hit = privacy_label(title) or privacy_record_pattern(text)
        if privacy_hit:
            privacy.append({"year": target.year, "url": meta.get("final_url") or target.url, "title": title, "status": "candidate_personal_data_excluded", "reason": privacy_hit})
            continue
        topics = topics_for(title + "\n" + target.label + "\n" + text[:300000], target.hints)
        primary = primary_topic(topics)
        source_id = f"SRC-{SCHOOL_ID}-{target.year}-{short_id(meta.get('final_url') or target.url)}"
        stored = f"DOC-{SCHOOL_ID}-{target.year}-{primary}-{short_id(meta.get('final_url') or target.url)}.html"
        raw_path = OUT / str(target.year) / folder(primary) / stored
        raw_path.write_bytes(body)
        parsed_path = raw_path.with_name(raw_path.stem + "_parsed.txt")
        parsed_path.write_text(text, encoding="utf-8")
        source = {
            "school_id": SCHOOL_ID, "school_name": SCHOOL_NAME, "year": target.year,
            "source_id": source_id, "title": title, "publish_date": published_date(text),
            "retrieved_at": RETRIEVED_AT, "official_page_url": target.url,
            "final_url": meta.get("final_url") or target.url,
            "source_domain": urlparse(meta.get("final_url") or target.url).hostname or "",
            "document_type": "html", "topics": topics, "file_type": ".html",
            "local_path": str(raw_path.relative_to(ROOT)), "file_size": len(body),
            "sha256": digest(body), "http_status": meta.get("http_status"),
            "status": "collected", "notes": f"explicit_year={target.year}; target_label={target.label}",
        }
        sources.append(source)
        assets.append({
            "asset_id": f"AST-{SCHOOL_ID}-{target.year}-{short_id(str(parsed_path))}",
            "source_id": source_id, "school_id": SCHOOL_ID, "school_name": SCHOOL_NAME,
            "year": target.year, "title": title + " parsed text", "topics": topics,
            "asset_type": "parsed_text", "file_type": ".txt",
            "local_path": str(parsed_path.relative_to(ROOT)), "file_size": parsed_path.stat().st_size,
            "sha256": digest(parsed_path.read_bytes()), "official_page_url": target.url,
            "attachment_url": "", "original_filename": "", "parent_page": meta.get("final_url") or target.url,
            "retrieved_at": RETRIEVED_AT, "status": "collected",
            "notes": "derived text; raw HTML retained",
        })
        for link in candidate_links(soup, meta.get("final_url") or target.url):
            hit = privacy_label(link["label"] + " " + link["url"])
            if hit:
                privacy.append({"year": target.year, "url": link["url"], "title": link["label"], "status": "candidate_personal_data_excluded", "reason": hit, "parent_page": meta.get("final_url") or target.url})
                continue
            attachment_jobs.append({
                "year": target.year, "url": link["url"], "label": link["label"],
                "kind": link["kind"], "source_id": source_id,
                "parent_page": meta.get("final_url") or target.url,
                "parent_title": title, "parent_topics": topics,
            })

    unique_jobs: list[dict[str, Any]] = []
    seen_jobs: set[tuple[int, str]] = set()
    for job in attachment_jobs:
        key = (job["year"], job["url"])
        if key not in seen_jobs:
            seen_jobs.add(key)
            unique_jobs.append(job)

    def get_asset(job: dict[str, Any]) -> dict[str, Any]:
        body, meta = fetch(job["url"])
        return {"job": job, "body": body, "meta": meta}

    asset_results: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=12) as pool:
        futures = [pool.submit(get_asset, job) for job in unique_jobs]
        for future in as_completed(futures):
            asset_results.append(future.result())

    for result in sorted(asset_results, key=lambda item: (item["job"]["year"], item["job"]["url"])):
        job = result["job"]
        body: bytes | None = result["body"]
        meta: dict[str, Any] = result["meta"]
        if body is None:
            status = meta.get("status") or ("removed_or_unavailable" if meta.get("http_status") in (404, 410) else "access_restricted")
            failures.append({"year": job["year"], "url": job["url"], "title": job["label"], "topics": job["parent_topics"], "status": status, "http_status": meta.get("http_status"), "reason": meta.get("reason", ""), "parent_page": job["parent_page"]})
            continue
        ext = extension(job["url"], meta, body)
        if ext not in ALLOWED_EXTS:
            continue
        name = original_filename(job["url"], meta)
        extracted = docx_text(body) if ext == ".docx" else ""
        privacy_hit = privacy_label(job["label"] + " " + name) or privacy_record_pattern(extracted)
        if privacy_hit:
            privacy.append({"year": job["year"], "url": meta.get("final_url") or job["url"], "title": job["label"] or name, "status": "candidate_personal_data_excluded", "reason": privacy_hit, "parent_page": job["parent_page"]})
            continue
        topics = topics_for(job["parent_title"] + "\n" + job["label"] + "\n" + name + "\n" + extracted[:200000], job["parent_topics"])
        primary = primary_topic(topics)
        stored = f"DOC-{SCHOOL_ID}-{job['year']}-{primary}-{short_id(meta.get('final_url') or job['url'])}{ext}"
        raw_path = OUT / str(job["year"]) / folder(primary) / stored
        raw_path.write_bytes(body)
        asset_id = f"AST-{SCHOOL_ID}-{job['year']}-{short_id(meta.get('final_url') or job['url'])}"
        assets.append({
            "asset_id": asset_id, "source_id": job["source_id"],
            "school_id": SCHOOL_ID, "school_name": SCHOOL_NAME, "year": job["year"],
            "title": job["label"] or name, "topics": topics,
            "asset_type": job["kind"], "file_type": ext,
            "local_path": str(raw_path.relative_to(ROOT)), "file_size": len(body),
            "sha256": digest(body), "official_page_url": job["parent_page"],
            "attachment_url": meta.get("final_url") or job["url"],
            "original_filename": name, "parent_page": job["parent_page"],
            "retrieved_at": RETRIEVED_AT, "http_status": meta.get("http_status"),
            "status": "collected", "notes": f"explicit_year={job['year']}; attachment_label={job['label']}",
        })
        if extracted:
            parsed_path = raw_path.with_name(raw_path.stem + "_parsed.txt")
            parsed_path.write_text(extracted, encoding="utf-8")
            assets.append({
                "asset_id": asset_id + "-TXT", "source_id": job["source_id"],
                "school_id": SCHOOL_ID, "school_name": SCHOOL_NAME, "year": job["year"],
                "title": (job["label"] or name) + " parsed text", "topics": topics,
                "asset_type": "parsed_text", "file_type": ".txt",
                "local_path": str(parsed_path.relative_to(ROOT)), "file_size": parsed_path.stat().st_size,
                "sha256": digest(parsed_path.read_bytes()), "official_page_url": job["parent_page"],
                "attachment_url": meta.get("final_url") or job["url"],
                "original_filename": name, "parent_page": job["parent_page"],
                "retrieved_at": RETRIEVED_AT, "status": "collected",
                "notes": "derived DOCX text; original attachment retained",
            })

    def dedupe(rows: list[dict[str, Any]], fields: tuple[str, ...]) -> list[dict[str, Any]]:
        output: list[dict[str, Any]] = []
        seen: set[tuple[Any, ...]] = set()
        for row in rows:
            key = tuple(row.get(field) for field in fields)
            if key not in seen:
                seen.add(key)
                output.append(row)
        return output

    sources = dedupe(sources, ("year", "final_url", "sha256"))
    assets = dedupe(assets, ("year", "attachment_url", "sha256", "asset_type"))
    failures = dedupe(failures, ("year", "url", "status"))
    privacy = dedupe(privacy, ("year", "url", "reason"))

    hashes: dict[str, list[dict[str, Any]]] = {}
    for item in assets:
        if item.get("asset_type") != "parsed_text":
            hashes.setdefault(item["sha256"], []).append(item)
    duplicate_counter = 0
    for group in hashes.values():
        if len(group) > 1:
            duplicate_counter += 1
            duplicate_group = f"DUP-{SCHOOL_ID}-{duplicate_counter:04d}"
            for item in group:
                item["duplicate_group"] = duplicate_group

    collected_by_cell: dict[tuple[int, str], list[str]] = {}
    for source in sources:
        for topic in source["topics"]:
            collected_by_cell.setdefault((source["year"], topic), []).append(source["source_id"])
    for asset in assets:
        if asset.get("asset_type") == "parsed_text":
            continue
        for topic in asset["topics"]:
            collected_by_cell.setdefault((asset["year"], topic), []).append(asset["asset_id"])
    failed_by_cell: dict[tuple[int, str], list[str]] = {}
    for failure in failures:
        for topic in failure.get("topics", []):
            failed_by_cell.setdefault((failure["year"], topic), []).append(failure["url"])

    coverage: list[dict[str, Any]] = []
    for year in YEARS:
        for topic in TOPICS:
            evidence = sorted(set(collected_by_cell.get((year, topic), [])))
            if evidence:
                status = "collected"
                notes = f"{len(evidence)} evidence record(s)"
            elif (year, topic) in failed_by_cell:
                status = "access_restricted"
                notes = f"{len(failed_by_cell[(year, topic)])} targeted official URL(s) failed"
            else:
                status = "not_found"
                notes = "not obtained in this targeted deep-search batch"
            coverage.append({
                "school_id": SCHOOL_ID, "school_name": SCHOOL_NAME, "year": year,
                "topic": topic, "status": status, "evidence_count": len(evidence),
                "evidence_ids": "|".join(evidence), "notes": notes,
            })

    manifest = {
        "school_id": SCHOOL_ID, "school_name": SCHOOL_NAME,
        "official_domains": [OFFICIAL_DOMAIN], "years": list(YEARS),
        "sources": sources, "assets": assets, "failures": failures,
        "privacy_exclusions": privacy, "generated_at": utc_now(),
        "sanitized": True, "acquisition_batch": "p0_batch_02_bctb",
    }
    write_json(OUT / "school_manifest.json", manifest)
    with (OUT / "school_coverage.csv").open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=["school_id", "school_name", "year", "topic", "status", "evidence_count", "evidence_ids", "notes"])
        writer.writeheader()
        writer.writerows(coverage)

    status_counts: dict[str, int] = {}
    for row in coverage:
        status_counts[row["status"]] = status_counts.get(row["status"], 0) + 1
    raw_assets = [item for item in assets if item.get("asset_type") != "parsed_text"]
    raw_files = len(sources) + len(raw_assets)
    raw_bytes = sum(int(item["file_size"]) for item in sources + raw_assets)
    year_topics = {year: [row["topic"] for row in coverage if row["year"] == year and row["status"] == "collected"] for year in YEARS}
    notes_lines = [
        f"# {SCHOOL_NAME} ({SCHOOL_ID})", "",
        "- Acquisition batch: p0_batch_02_bctb",
        f"- Retrieved at: {RETRIEVED_AT}",
        f"- Official source documents: {len(sources)}",
        f"- Raw attachments/images: {len(raw_assets)}",
        f"- Raw files total: {raw_files}",
        f"- Raw bytes: {raw_bytes}",
        f"- Collected coverage cells: {status_counts.get('collected', 0)} / 84",
        f"- Not found cells: {status_counts.get('not_found', 0)}",
        f"- Access restricted cells: {status_counts.get('access_restricted', 0)}",
        f"- Privacy exclusions: {len(privacy)}", "",
    ]
    for year in YEARS:
        notes_lines.extend([f"## {year}", "", "- Collected topics: " + (", ".join(year_topics[year]) if year_topics[year] else "none"), ""])
    notes_lines.extend([
        "## Quality and privacy notes", "",
        "- Raw HTML and original official attachments are retained; parsed text is derivative only.",
        "- Candidate-level lists, candidate numbers, names and individual scores are excluded.",
        "- `not_found` means this batch did not obtain an official source; it does not mean the school never published it.",
    ])
    (OUT / "school_notes.md").write_text("\n".join(notes_lines) + "\n", encoding="utf-8")

    # Validate hashes, matrix shape, official-domain provenance and privacy labels.
    assert len(coverage) == 84
    assert {int(row["year"]) for row in coverage} == set(YEARS)
    assert {row["topic"] for row in coverage} == set(TOPICS)
    for item in sources + assets:
        path = ROOT / item["local_path"]
        assert path.is_file(), path
        data = path.read_bytes()
        assert len(data) == int(item["file_size"]), path
        assert digest(data) == item["sha256"], path
        source_url = item.get("final_url") or item.get("attachment_url") or item.get("official_page_url") or ""
        assert official(source_url), source_url
        label = " ".join(str(item.get(key, "")) for key in ("title", "original_filename", "notes"))
        assert not privacy_label(label), label
    assert raw_files > 0, "no official raw evidence collected"

    result = {
        "batch": "p0_batch_02_bctb", "generated_at": utc_now(),
        "school_id": SCHOOL_ID, "school_name": SCHOOL_NAME,
        "source_documents": len(sources), "raw_attachments_and_images": len(raw_assets),
        "raw_files": raw_files, "raw_bytes": raw_bytes,
        "collected": status_counts.get("collected", 0),
        "not_found": status_counts.get("not_found", 0),
        "access_restricted": status_counts.get("access_restricted", 0),
        "manual_download_required": sum(1 for item in failures if item["status"] == "manual_download_required"),
        "privacy_excluded": len(privacy), "year_topics": year_topics,
        "failures": failures, "privacy_exclusions": privacy,
    }
    write_json(REPORT_DIR / "p0_batch_02_bctb_result.json", result)
    write_json(BATCH_DIR / "BCTB_result.json", result)

    audit = [
        "# P0 Batch 02 — BCTB 原始证据采集审计", "",
        f"- 生成时间：{result['generated_at']}",
        f"- 学校：{SCHOOL_ID} {SCHOOL_NAME}",
        "- 年份：2024、2025、2026", "- 主题矩阵：3 × 28 = 84", "",
        "## 批次指标", "",
        "- 本批学校数：1",
        f"- 新增 source document 数：{result['source_documents']}",
        f"- 新增原始附件/有效图片数：{result['raw_attachments_and_images']}",
        f"- 新增原始文件数：{result['raw_files']}",
        f"- 新增总字节数：{result['raw_bytes']}",
        f"- 新增 collected 覆盖格数：{result['collected']}",
        f"- 仍 not_found 数：{result['not_found']}",
        f"- access_restricted 数：{result['access_restricted']}",
        f"- manual_download_required 数：{result['manual_download_required']}",
        f"- privacy excluded 数：{result['privacy_excluded']}", "",
        "## 逐年已补主题", "",
    ]
    for year in YEARS:
        audit.append(f"- {year}：" + (", ".join(year_topics[year]) if year_topics[year] else "无"))
    audit.extend([
        "", "## 质量说明", "",
        "- 仅保存 `bctb.edu.cn` 官方域名返回的原始字节。",
        "- 页面附件和文章正文承载的有效图片均检查并保存；站点模板图片不保存。",
        "- 所有原始文件记录 SHA-256、字节数、最终 URL、父页面和严格年份绑定。",
        "- 含姓名、考生号、准考证号、身份证号或个人成绩的页面/附件不归档。",
        "- `not_found` 不等同于 `official_not_published`，后续仍需二次深挖。", "",
    ])
    (REPORT_DIR / "p0_batch_02_bctb_audit.md").write_text("\n".join(audit), encoding="utf-8")
    print(json.dumps({key: result[key] for key in ("source_documents", "raw_attachments_and_images", "raw_files", "raw_bytes", "collected", "not_found", "access_restricted", "manual_download_required", "privacy_excluded")}, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
