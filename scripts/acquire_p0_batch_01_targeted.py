#!/usr/bin/env python3
"""Targeted raw-evidence acquisition for P0 batch 01 (WXC and AHSZU).

The inputs are year-bound official URLs discovered and manually verified before this
run. Search results are not archived as evidence. Only official-domain bytes are
saved. Candidate-level personal data is excluded before writing to disk.
"""
from __future__ import annotations

import csv
import hashlib
import json
import os
import re
import shutil
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import unquote, urljoin, urlparse

import requests
from bs4 import BeautifulSoup

REPO_ROOT = Path(os.environ.get("REPO_ROOT", ".")).resolve()
EVIDENCE_ROOT = REPO_ROOT / "anhui_zsb_data" / "evidence" / "full_raw_30_schools"
REPORT_ROOT = REPO_ROOT / "anhui_zsb_data" / "reports"
BATCH_REPORT_ROOT = EVIDENCE_ROOT / "_acquisition_reports" / "p0_batch_01"
RETRIEVED_AT = datetime.now(timezone.utc).isoformat()
YEARS = (2024, 2025, 2026)

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

TOPIC_KEYWORDS = {
    "admission_policy": ["招生章程", "招生简章", "招生实施办法"],
    "enrollment_plan": ["招生计划", "拟招生方案", "拟招生专业"],
    "major_catalog": ["招生专业", "专业招生范围", "招生范围", "报考范围"],
    "training_location": ["联合培养", "培养地点", "培养校区", "办学地点"],
    "tuition_and_duration": ["学费", "学制", "住宿费"],
    "eligibility": ["报名条件", "报考条件", "报考资格", "资格审核"],
    "exam_subjects": ["考试科目", "专业课", "公共课"],
    "exam_syllabus": ["考试大纲", "测试大纲", "考查大纲"],
    "reference_books": ["参考书目", "参考教材", "教材"],
    "exam_schedule": ["考试时间", "考试安排", "面试时间"],
    "exam_location": ["考试地点", "考点", "考场"],
    "admission_rules": ["录取规则", "录取细则", "同分排序"],
    "score_formula": ["计分公式", "成绩计算", "综合成绩", "总成绩"],
    "control_line": ["合格线", "控制线", "专业课合格"],
    "admission_min_score": ["最低录取分", "最低投档分", "录取分数线", "最低分"],
    "admission_max_score": ["最高录取分", "录取最高分", "最高分"],
    "admission_average_score": ["平均录取分", "录取平均分", "平均分"],
    "application_statistics": ["报考人数", "报名人数", "报考统计"],
    "qualified_statistics": ["资格审核通过人数", "资格通过人数", "合格人数"],
    "admitted_statistics": ["录取人数", "录取统计"],
    "registered_statistics": ["报到人数", "注册人数"],
    "plan_adjustment": ["计划调整", "调整计划", "扩招", "缩招"],
    "adjustment": ["调剂", "补录", "征集志愿", "缺额计划"],
    "exemption": ["免试", "免文化课"],
    "retired_soldier": ["退役大学生士兵", "退役士兵"],
    "registered_poor_family": ["建档立卡"],
    "skill_competition": ["技能大赛", "职业技能大赛"],
    "other_official_notice": ["专升本"],
}

PRIVACY_TITLE_TERMS = [
    "拟录取名单", "预录取名单", "录取名单", "考生名单", "面试名单",
    "审核名单", "免试名单", "成绩名单", "资格审核结果名单", "个人成绩表",
]
PRIVACY_FIELD_TERMS = ["身份证号", "考生号", "准考证号", "手机号"]
ALLOWED_EXTS = {".pdf", ".doc", ".docx", ".xls", ".xlsx", ".csv", ".json", ".txt", ".jpg", ".jpeg", ".png", ".tif", ".tiff", ".zip"}
MAX_BYTES = 100 * 1024 * 1024

SCHOOLS = {
    "WXC": {"name": "皖西学院", "domains": ["wxc.edu.cn"]},
    "AHSZU": {"name": "宿州学院", "domains": ["ahszu.edu.cn"]},
}

@dataclass(frozen=True)
class Target:
    school_id: str
    year: int
    url: str
    label: str
    kind: str = "page"
    topic_hints: tuple[str, ...] = ()

TARGETS: tuple[Target, ...] = (
    Target("WXC", 2025, "https://zsb.wxc.edu.cn/_upload/article/files/61/dc/c7c861c34e73a0b4a234a93c7f94/3b31146a-9b4a-4995-ba14-ab7eadc8c7c1.pdf", "皖西学院2025年普通专升本专业课考试大纲", "file", ("exam_syllabus",)),
    Target("WXC", 2025, "https://zsb.wxc.edu.cn/_upload/article/files/61/dc/c7c861c34e73a0b4a234a93c7f94/e4b3b43c-f1b7-4124-ba75-502aca08422d.pdf", "皖西学院2025年普通专升本考试科目及参考书目", "file", ("exam_subjects", "reference_books")),
    Target("AHSZU", 2024, "https://www.ahszu.edu.cn/zs/info/1039/5667.htm", "宿州学院2024年普通高校专升本招生章程", topic_hints=("admission_policy",)),
    Target("AHSZU", 2024, "https://www.ahszu.edu.cn/zs/info/1039/5639.htm", "宿州学院2024年普通专升本招生计划", topic_hints=("enrollment_plan", "major_catalog")),
    Target("AHSZU", 2024, "https://www.ahszu.edu.cn/zs/info/1062/5673.htm", "宿州学院2024年免文化课退役士兵职业适应性测试大纲", topic_hints=("exam_syllabus", "exemption", "retired_soldier")),
    Target("AHSZU", 2024, "https://www.ahszu.edu.cn/zs/info/1039/5739.htm", "宿州学院2024年普通专升本报考人数统计", topic_hints=("application_statistics",)),
    Target("AHSZU", 2024, "https://www.ahszu.edu.cn/zs/info/1039/5762.htm", "宿州学院2024年普通专升本专业课考试通知", topic_hints=("exam_subjects", "exam_schedule", "exam_location")),
    Target("AHSZU", 2024, "https://www.ahszu.edu.cn/zs/info/1039/5786.htm", "宿州学院2024年普通专升本专业课合格线及录取通知", topic_hints=("control_line", "admission_min_score")),
    Target("AHSZU", 2025, "https://www.ahszu.edu.cn/zs/info/1062/6003.htm", "宿州学院2025年普通高校专升本拟招生专业计划及考试大纲", topic_hints=("enrollment_plan", "major_catalog", "exam_subjects", "exam_syllabus", "reference_books")),
    Target("AHSZU", 2025, "https://www.ahszu.edu.cn/zs/info/1039/6239.htm", "宿州学院2025年普通高校专升本招生章程", topic_hints=("admission_policy",)),
    Target("AHSZU", 2025, "https://www.ahszu.edu.cn/zs/info/1039/6309.htm", "宿州学院2025年免文化课退役士兵职业适应性测试大纲", topic_hints=("exam_syllabus", "exemption", "retired_soldier")),
    Target("AHSZU", 2025, "https://www.ahszu.edu.cn/zs/info/1039/7209.htm", "宿州学院2025年普通专升本专业课合格线及最低分", topic_hints=("control_line", "admission_min_score")),
    Target("AHSZU", 2025, "https://www.ahszu.edu.cn/zs/info/1062/8129.htm", "宿州学院2025年普通专升本录取人数统计", topic_hints=("admitted_statistics",)),
    Target("AHSZU", 2026, "https://www.ahszu.edu.cn/zs/info/1062/8249.htm", "宿州学院2026年普通高校专升本拟招生专业计划及专业课考试大纲", topic_hints=("enrollment_plan", "major_catalog", "exam_subjects", "exam_syllabus", "reference_books")),
    Target("AHSZU", 2026, "https://www.ahszu.edu.cn/zs/info/1062/8549.htm", "宿州学院2026年普通高校专升本招生章程", topic_hints=("admission_policy",)),
    Target("AHSZU", 2026, "https://www.ahszu.edu.cn/zs/info/1039/8559.htm", "宿州学院2026年免文化课退役士兵职业适应性测试大纲", topic_hints=("exam_syllabus", "exemption", "retired_soldier")),
    Target("AHSZU", 2026, "https://www.ahszu.edu.cn/zs/info/1039/8789.htm", "宿州学院2026年技能大赛鼓励政策考生面试通知", topic_hints=("skill_competition", "exam_schedule", "exam_location")),
    Target("AHSZU", 2026, "https://www.ahszu.edu.cn/zs/info/1039/8869.htm", "宿州学院2026年普通专升本专业课考试通知", topic_hints=("exam_subjects", "exam_schedule", "exam_location")),
    Target("AHSZU", 2026, "https://www.ahszu.edu.cn/zs/info/1062/8889.htm", "宿州学院2026年普通专升本专业课成绩查询及复核通知", topic_hints=("other_official_notice",)),
)

_thread_local = threading.local()


def session() -> requests.Session:
    value = getattr(_thread_local, "session", None)
    if value is None:
        value = requests.Session()
        value.headers.update({
            "User-Agent": "Mozilla/5.0 (compatible; AnhuiZSBDataResearch/1.1; raw evidence archiver)",
            "Accept": "*/*",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.6",
        })
        _thread_local.session = value
    return value


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def short_id(value: str) -> str:
    return hashlib.sha1(value.encode("utf-8", "replace")).hexdigest()[:10]


def official(url: str, school_id: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    return any(host == domain or host.endswith("." + domain) for domain in SCHOOLS[school_id]["domains"])


def sanitize_filename(value: str) -> str:
    value = unquote(value or "download")
    value = re.sub(r'[\\/:*?"<>|\x00-\x1f]', "_", value).strip(" .")
    return (value or "download")[:180]


def privacy_title_hit(text: str) -> str | None:
    compact = re.sub(r"\s+", "", text or "")
    return next((term for term in PRIVACY_TITLE_TERMS if term in compact), None)


def record_pattern_hit(text: str) -> str | None:
    compact = re.sub(r"\s+", "", text or "")
    if "姓名" in compact:
        identifiers = re.findall(r"(?<!\d)\d{10,18}(?!\d)", compact)
        if len(identifiers) >= 2 and any(term in compact for term in PRIVACY_FIELD_TERMS):
            return "candidate-record-pattern"
    return None


def topics_for(text: str, hints: Iterable[str] = ()) -> list[str]:
    compact = re.sub(r"\s+", "", text or "")
    found = set(hints)
    for topic, words in TOPIC_KEYWORDS.items():
        if any(word in compact for word in words):
            found.add(topic)
    if "专升本" in compact:
        found.add("other_official_notice")
    return [topic for topic in TOPICS if topic in found]


def primary_topic(topics: Iterable[str]) -> str:
    for topic in TOPICS:
        if topic in topics and topic != "other_official_notice":
            return topic
    return "other_official_notice"


def subdir(topic: str) -> str:
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


def fetch(url: str) -> tuple[bytes | None, dict[str, Any]]:
    try:
        response = session().get(url, timeout=(5, 12), allow_redirects=True)
        meta: dict[str, Any] = {
            "http_status": response.status_code,
            "final_url": response.url,
            "content_type": response.headers.get("Content-Type", ""),
            "content_disposition": response.headers.get("Content-Disposition", ""),
        }
        if response.status_code >= 400:
            return None, meta
        body = response.content
        if len(body) > MAX_BYTES:
            meta.update({"too_large": True, "file_size": len(body), "sha256": sha256(body)})
            return None, meta
        meta.update({"file_size": len(body), "sha256": sha256(body)})
        return body, meta
    except Exception as exc:
        return None, {"http_status": "error", "final_url": url, "error": repr(exc)}


def file_extension(url: str, meta: dict[str, Any], body: bytes | None) -> str:
    ext = Path(urlparse(meta.get("final_url") or url).path).suffix.lower()
    if ext in ALLOWED_EXTS:
        return ext
    disposition = meta.get("content_disposition", "")
    match = re.search(r"filename\*?=(?:UTF-8''|\")?([^\";]+)", disposition, re.I)
    if match:
        ext = Path(unquote(match.group(1))).suffix.lower()
        if ext in ALLOWED_EXTS:
            return ext
    content_type = meta.get("content_type", "").lower().split(";", 1)[0]
    mapping = {
        "application/pdf": ".pdf",
        "application/msword": ".doc",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
        "application/vnd.ms-excel": ".xls",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ".xlsx",
        "text/csv": ".csv",
        "application/json": ".json",
        "image/jpeg": ".jpg",
        "image/png": ".png",
        "image/tiff": ".tif",
        "application/zip": ".zip",
    }
    if content_type in mapping:
        return mapping[content_type]
    if body and body.startswith(b"%PDF-"):
        return ".pdf"
    if body and body.startswith(b"PK\x03\x04"):
        return ".zip"
    return ""


def original_name(url: str, meta: dict[str, Any]) -> str:
    disposition = meta.get("content_disposition", "")
    match = re.search(r"filename\*?=(?:UTF-8''|\")?([^\";]+)", disposition, re.I)
    if match:
        return sanitize_filename(match.group(1))
    return sanitize_filename(Path(urlparse(meta.get("final_url") or url).path).name)


def failure_status(meta: dict[str, Any]) -> str:
    status = meta.get("http_status")
    if status in (404, 410):
        return "removed_or_unavailable"
    if meta.get("too_large"):
        return "manual_download_required"
    return "access_restricted"


def attachment_candidates(html_body: bytes, final_url: str, school_id: str) -> list[tuple[str, str]]:
    soup = BeautifulSoup(html_body, "html.parser")
    candidates: list[tuple[str, str]] = []
    seen: set[str] = set()
    for node in soup.find_all(["a", "iframe", "embed", "object"]):
        href = node.get("href") or node.get("src") or node.get("data")
        if not href:
            continue
        url = urljoin(final_url, href).split("#", 1)[0].strip()
        if not url.startswith(("http://", "https://")) or not official(url, school_id):
            continue
        path = urlparse(url).path.lower()
        label = node.get_text(" ", strip=True)[:300]
        if not (Path(path).suffix.lower() in ALLOWED_EXTS or any(key in path for key in ("_upload", "download", "system/_content"))):
            continue
        if url in seen:
            continue
        seen.add(url)
        candidates.append((url, label))
    return candidates


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=["school_id", "school_name", "year", "topic", "status"])
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    EVIDENCE_ROOT.mkdir(parents=True, exist_ok=True)
    REPORT_ROOT.mkdir(parents=True, exist_ok=True)
    BATCH_REPORT_ROOT.mkdir(parents=True, exist_ok=True)
    for school_id in SCHOOLS:
        school_dir = EVIDENCE_ROOT / school_id
        if school_dir.exists():
            shutil.rmtree(school_dir)
        for year in YEARS:
            for directory in ("admission_policy", "enrollment_plan", "exam_syllabus", "admission_scores", "statistics", "adjustments", "other"):
                (school_dir / str(year) / directory).mkdir(parents=True, exist_ok=True)

    sources: list[dict[str, Any]] = []
    assets: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    privacy: list[dict[str, Any]] = []
    attachment_jobs: list[dict[str, Any]] = []

    def process_target(target: Target) -> dict[str, Any]:
        body, meta = fetch(target.url)
        return {"target": target, "body": body, "meta": meta}

    target_results: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=10) as pool:
        futures = [pool.submit(process_target, target) for target in TARGETS]
        for future in as_completed(futures):
            target_results.append(future.result())

    for result in sorted(target_results, key=lambda item: (item["target"].school_id, item["target"].year, item["target"].url)):
        target: Target = result["target"]
        body: bytes | None = result["body"]
        meta: dict[str, Any] = result["meta"]
        school_id = target.school_id
        school_name = SCHOOLS[school_id]["name"]
        final_url = meta.get("final_url") or target.url
        if body is None:
            failures.append({
                "school_id": school_id, "school_name": school_name, "year": target.year,
                "url": target.url, "parent_url": "", "status": failure_status(meta),
                "http_status": meta.get("http_status"),
                "reason": "file >100MB" if meta.get("too_large") else meta.get("error", ""),
            })
            continue

        ext = file_extension(target.url, meta, body)
        is_html = target.kind == "page" and ("html" in meta.get("content_type", "").lower() or not ext)
        if target.kind == "file" or (ext and not is_html):
            hit = privacy_title_hit(target.label + " " + target.url)
            if hit:
                privacy.append({"school_id": school_id, "school_name": school_name, "year": target.year, "url": final_url, "reason": hit, "status": "candidate_personal_data_excluded"})
                continue
            if not ext:
                failures.append({"school_id": school_id, "school_name": school_name, "year": target.year, "url": final_url, "parent_url": "", "status": "awaiting_manual_review", "http_status": meta.get("http_status"), "reason": "unknown file type"})
                continue
            doc_topics = topics_for(target.label, target.topic_hints)
            primary = primary_topic(doc_topics)
            stored = f"DOC-{school_id}-{target.year}-{primary}-{short_id(final_url)}{ext}"
            destination = EVIDENCE_ROOT / school_id / str(target.year) / subdir(primary) / stored
            destination.write_bytes(body)
            assets.append({
                "asset_id": f"AST-{school_id}-{target.year}-{short_id(final_url)}",
                "source_id": "", "school_id": school_id, "school_name": school_name,
                "year": target.year, "asset_type": ext.lstrip("."),
                "local_path": str(destination.relative_to(REPO_ROOT)),
                "original_file_name": original_name(target.url, meta),
                "stored_file_name": stored, "file_extension": ext,
                "mime_type": meta.get("content_type", ""), "file_size": len(body),
                "sha256": sha256(body), "retrieval_url": final_url,
                "retrieved_at": RETRIEVED_AT, "parent_asset_id": "",
                "parser_name": "", "parser_version": "", "generated_at": "",
                "privacy_classification": "public_aggregate_or_policy",
                "duplicate_group": "", "status": "collected",
                "notes": f"target_label={target.label}; explicit_year={target.year}; direct_official_file=true",
                "topics": "|".join(doc_topics),
            })
            continue

        soup = BeautifulSoup(body, "html.parser")
        title = soup.title.get_text(" ", strip=True) if soup.title else target.label
        text = soup.get_text("\n", strip=True)
        hit = privacy_title_hit(title + " " + target.label) or record_pattern_hit(text)
        if hit:
            privacy.append({"school_id": school_id, "school_name": school_name, "year": target.year, "url": final_url, "reason": hit, "status": "candidate_personal_data_excluded"})
            continue
        doc_topics = topics_for(title + "\n" + target.label + "\n" + text[:150000], target.topic_hints)
        primary = primary_topic(doc_topics)
        source_id = f"SRC-{school_id}-{target.year}-{short_id(final_url)}"
        stored = f"DOC-{school_id}-{target.year}-{primary}-{short_id(final_url)}.html"
        destination = EVIDENCE_ROOT / school_id / str(target.year) / subdir(primary) / stored
        destination.write_bytes(body)
        parsed = destination.with_name(destination.stem + "_parsed.txt")
        parsed.write_text(text, encoding="utf-8")
        sources.append({
            "school_id": school_id, "school_name": school_name, "year": target.year,
            "source_id": source_id, "document_type": "html",
            "topics": "|".join(doc_topics), "title": title,
            "official_url": target.url, "final_url": final_url,
            "parent_page_url": "", "publish_date": "",
            "retrieved_at": RETRIEVED_AT,
            "official_domain": urlparse(final_url).hostname or "",
            "source_level": "school_official", "http_status": meta.get("http_status"),
            "content_type": meta.get("content_type", ""), "status": "collected",
            "notes": f"target_label={target.label}; explicit_year={target.year}",
            "local_path": str(destination.relative_to(REPO_ROOT)),
            "sha256": sha256(body), "file_size": len(body),
        })
        assets.append({
            "asset_id": f"AST-{school_id}-{target.year}-{short_id(str(parsed.relative_to(REPO_ROOT)))}",
            "source_id": source_id, "school_id": school_id, "school_name": school_name,
            "year": target.year, "asset_type": "parsed_text",
            "local_path": str(parsed.relative_to(REPO_ROOT)),
            "original_file_name": "", "stored_file_name": parsed.name,
            "file_extension": ".txt", "mime_type": "text/plain",
            "file_size": parsed.stat().st_size, "sha256": sha256(parsed.read_bytes()),
            "retrieval_url": final_url, "retrieved_at": RETRIEVED_AT,
            "parent_asset_id": "", "parser_name": "BeautifulSoup",
            "parser_version": "bs4", "generated_at": RETRIEVED_AT,
            "privacy_classification": "public_aggregate_or_policy",
            "duplicate_group": "", "status": "collected",
            "notes": "derived parsed text; not a replacement for raw HTML",
            "topics": "|".join(doc_topics),
        })
        for attachment_url, attachment_label in attachment_candidates(body, final_url, school_id):
            attachment_hit = privacy_title_hit(attachment_label + " " + attachment_url)
            if attachment_hit:
                privacy.append({"school_id": school_id, "school_name": school_name, "year": target.year, "url": attachment_url, "reason": attachment_hit, "status": "candidate_personal_data_excluded"})
                continue
            attachment_jobs.append({
                "school_id": school_id, "school_name": school_name, "year": target.year,
                "parent_url": final_url, "source_id": source_id, "url": attachment_url,
                "label": attachment_label, "target_label": target.label,
                "topic_hints": target.topic_hints,
            })

    def process_attachment(job: dict[str, Any]) -> dict[str, Any]:
        body, meta = fetch(job["url"])
        return {"job": job, "body": body, "meta": meta}

    unique_jobs: list[dict[str, Any]] = []
    seen_jobs: set[tuple[str, int, str]] = set()
    for job in attachment_jobs:
        key = (job["school_id"], job["year"], job["url"])
        if key not in seen_jobs:
            seen_jobs.add(key)
            unique_jobs.append(job)

    attachment_results: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=12) as pool:
        futures = [pool.submit(process_attachment, job) for job in unique_jobs]
        for future in as_completed(futures):
            attachment_results.append(future.result())

    for result in sorted(attachment_results, key=lambda item: (item["job"]["school_id"], item["job"]["year"], item["job"]["url"])):
        job = result["job"]
        body = result["body"]
        meta = result["meta"]
        if body is None:
            failures.append({
                "school_id": job["school_id"], "school_name": job["school_name"],
                "year": job["year"], "url": job["url"], "parent_url": job["parent_url"],
                "status": failure_status(meta), "http_status": meta.get("http_status"),
                "reason": "file >100MB" if meta.get("too_large") else meta.get("error", ""),
            })
            continue
        final_url = meta.get("final_url") or job["url"]
        ext = file_extension(job["url"], meta, body)
        if ext not in ALLOWED_EXTS:
            continue
        name = original_name(job["url"], meta)
        hit = privacy_title_hit(job["label"] + " " + name + " " + final_url)
        if hit:
            privacy.append({"school_id": job["school_id"], "school_name": job["school_name"], "year": job["year"], "url": final_url, "reason": hit, "status": "candidate_personal_data_excluded"})
            continue
        doc_topics = topics_for(job["target_label"] + " " + job["label"] + " " + name, job["topic_hints"])
        primary = primary_topic(doc_topics)
        stored = f"DOC-{job['school_id']}-{job['year']}-{primary}-{short_id(final_url)}{ext}"
        destination = EVIDENCE_ROOT / job["school_id"] / str(job["year"]) / subdir(primary) / stored
        destination.write_bytes(body)
        assets.append({
            "asset_id": f"AST-{job['school_id']}-{job['year']}-{short_id(final_url)}",
            "source_id": job["source_id"], "school_id": job["school_id"],
            "school_name": job["school_name"], "year": job["year"],
            "asset_type": ext.lstrip("."), "local_path": str(destination.relative_to(REPO_ROOT)),
            "original_file_name": name, "stored_file_name": stored,
            "file_extension": ext, "mime_type": meta.get("content_type", ""),
            "file_size": len(body), "sha256": sha256(body),
            "retrieval_url": final_url, "retrieved_at": RETRIEVED_AT,
            "parent_asset_id": "", "parser_name": "", "parser_version": "",
            "generated_at": "", "privacy_classification": "public_aggregate_or_policy",
            "duplicate_group": "", "status": "collected",
            "notes": f"parent={job['parent_url']}; attachment_label={job['label']}; explicit_year={job['year']}",
            "topics": "|".join(doc_topics),
        })

    def uniq(rows: list[dict[str, Any]], keys: tuple[str, ...]) -> list[dict[str, Any]]:
        output: list[dict[str, Any]] = []
        seen: set[tuple[Any, ...]] = set()
        for row in rows:
            key = tuple(row.get(field) for field in keys)
            if key not in seen:
                seen.add(key)
                output.append(row)
        return output

    sources = uniq(sources, ("school_id", "year", "final_url", "sha256"))
    assets = uniq(assets, ("school_id", "year", "retrieval_url", "sha256", "asset_type"))
    failures = uniq(failures, ("school_id", "year", "url", "status"))
    privacy = uniq(privacy, ("school_id", "year", "url", "reason"))

    hash_groups: dict[str, list[dict[str, Any]]] = {}
    for asset in assets:
        if asset.get("asset_type") != "parsed_text" and asset.get("sha256"):
            hash_groups.setdefault(asset["sha256"], []).append(asset)
    duplicate_index = 0
    for group in hash_groups.values():
        if len(group) > 1:
            duplicate_index += 1
            duplicate_id = f"DUP-P0B01-{duplicate_index:04d}"
            for asset in group:
                asset["duplicate_group"] = duplicate_id

    coverage_rows: list[dict[str, Any]] = []
    for school_id, school in SCHOOLS.items():
        collected: set[tuple[int, str]] = set()
        for source in sources:
            if source["school_id"] == school_id:
                collected.update((int(source["year"]), topic) for topic in source.get("topics", "").split("|") if topic in TOPICS)
        for asset in assets:
            if asset["school_id"] == school_id:
                collected.update((int(asset["year"]), topic) for topic in asset.get("topics", "").split("|") if topic in TOPICS)
        for year in YEARS:
            for topic in TOPICS:
                coverage_rows.append({
                    "school_id": school_id, "school_name": school["name"],
                    "year": year, "topic": topic,
                    "status": "collected" if (year, topic) in collected else "not_found",
                })

    for school_id, school in SCHOOLS.items():
        school_sources = [row for row in sources if row["school_id"] == school_id]
        school_assets = [row for row in assets if row["school_id"] == school_id]
        school_failures = [row for row in failures if row["school_id"] == school_id]
        school_privacy = [row for row in privacy if row["school_id"] == school_id]
        school_dir = EVIDENCE_ROOT / school_id
        manifest = {
            "school_id": school_id, "school_name": school["name"],
            "official_domains": school["domains"], "sources": school_sources,
            "assets": school_assets, "failures": school_failures,
            "privacy_exclusions": school_privacy, "generated_at": now(),
            "sanitized": True, "acquisition_batch": "p0_batch_01_targeted_fast",
        }
        write_json(school_dir / "school_manifest.json", manifest)
        write_csv(school_dir / "school_coverage.csv", [row for row in coverage_rows if row["school_id"] == school_id])
        raw_assets = [asset for asset in school_assets if asset.get("asset_type") != "parsed_text"]
        statuses: dict[str, int] = {}
        for row in coverage_rows:
            if row["school_id"] == school_id:
                statuses[row["status"]] = statuses.get(row["status"], 0) + 1
        notes = [
            f"# {school['name']} ({school_id})", "",
            "- Acquisition batch: p0_batch_01_targeted_fast",
            f"- Official domains: {', '.join(school['domains'])}",
            f"- Source HTML documents: {len(school_sources)}",
            f"- Raw attachment files: {len(raw_assets)}",
            f"- Parsed text derivatives: {len(school_assets) - len(raw_assets)}",
            f"- Failures: {len(school_failures)}",
            f"- Privacy exclusions: {len(school_privacy)}",
            f"- Collected coverage cells: {statuses.get('collected', 0)} / 84",
            f"- Not found coverage cells: {statuses.get('not_found', 0)} / 84", "",
            "`not_found` means this targeted batch did not obtain an official source; it does not assert that the school never published the topic.",
        ]
        (school_dir / "school_notes.md").write_text("\n".join(notes) + "\n", encoding="utf-8")

    forbidden_labels = PRIVACY_TITLE_TERMS + ["身份证号", "考生号", "准考证号"]
    for school_id in SCHOOLS:
        school_dir = EVIDENCE_ROOT / school_id
        with (school_dir / "school_coverage.csv").open(encoding="utf-8-sig", newline="") as file:
            rows = list(csv.DictReader(file))
        assert len(rows) == 84, (school_id, len(rows))
        assert {int(row["year"]) for row in rows} == set(YEARS)
        assert {row["topic"] for row in rows} == set(TOPICS)
        manifest = json.loads((school_dir / "school_manifest.json").read_text(encoding="utf-8"))
        for record in manifest["sources"] + manifest["assets"]:
            path = REPO_ROOT / record["local_path"]
            assert path.is_file(), path
            data = path.read_bytes()
            assert len(data) == int(record["file_size"]), path
            assert sha256(data) == record["sha256"], path
            url = record.get("final_url") or record.get("retrieval_url") or ""
            assert official(url, school_id), url
            label = " ".join(str(record.get(key, "")) for key in ("title", "original_file_name", "stored_file_name", "notes"))
            assert not any(term in label for term in forbidden_labels), label

    school_rows: list[dict[str, Any]] = []
    totals = {
        "schools": len(SCHOOLS), "source_documents": 0, "raw_files": 0,
        "raw_bytes": 0, "collected": 0, "not_found": 0,
        "access_restricted": 0, "manual_download_required": 0,
        "privacy_excluded": len(privacy),
    }
    for school_id, school in SCHOOLS.items():
        school_sources = [row for row in sources if row["school_id"] == school_id]
        school_assets = [row for row in assets if row["school_id"] == school_id and row.get("asset_type") != "parsed_text"]
        school_failures = [row for row in failures if row["school_id"] == school_id]
        school_coverage = [row for row in coverage_rows if row["school_id"] == school_id]
        year_topics = {year: [row["topic"] for row in school_coverage if row["year"] == year and row["status"] == "collected"] for year in YEARS}
        raw_bytes = sum(int(row["file_size"]) for row in school_sources + school_assets)
        status_counts: dict[str, int] = {}
        for row in school_coverage:
            status_counts[row["status"]] = status_counts.get(row["status"], 0) + 1
        entry = {
            "school_id": school_id, "school_name": school["name"],
            "source_documents": len(school_sources), "raw_files": len(school_sources) + len(school_assets),
            "raw_bytes": raw_bytes, "collected": status_counts.get("collected", 0),
            "not_found": status_counts.get("not_found", 0),
            "access_restricted": sum(1 for row in school_failures if row["status"] == "access_restricted"),
            "manual_download_required": sum(1 for row in school_failures if row["status"] == "manual_download_required"),
            "privacy_excluded": sum(1 for row in privacy if row["school_id"] == school_id),
            "year_topics": year_topics,
        }
        school_rows.append(entry)
        totals["source_documents"] += entry["source_documents"]
        totals["raw_files"] += entry["raw_files"]
        totals["raw_bytes"] += entry["raw_bytes"]
        totals["collected"] += entry["collected"]
        totals["not_found"] += entry["not_found"]
        totals["access_restricted"] += entry["access_restricted"]
        totals["manual_download_required"] += entry["manual_download_required"]

    result = {
        "batch": "p0_batch_01_targeted_fast", "generated_at": now(),
        "schools": school_rows, "totals": totals,
        "failures": failures, "privacy_exclusions": privacy,
    }
    write_json(REPORT_ROOT / "p0_batch_01_result.json", result)
    write_json(BATCH_REPORT_ROOT / "batch_result.json", result)
    write_json(BATCH_REPORT_ROOT / "WXC_result.json", {"school": next(row for row in school_rows if row["school_id"] == "WXC"), "manifest": json.loads((EVIDENCE_ROOT / "WXC" / "school_manifest.json").read_text(encoding="utf-8"))})
    write_json(BATCH_REPORT_ROOT / "AHSZU_result.json", {"school": next(row for row in school_rows if row["school_id"] == "AHSZU"), "manifest": json.loads((EVIDENCE_ROOT / "AHSZU" / "school_manifest.json").read_text(encoding="utf-8"))})

    markdown = [
        "# P0 Batch 01 原始证据采集审计", "",
        f"- 生成时间：{result['generated_at']}",
        "- 范围：WXC 皖西学院、AHSZU 宿州学院；2024—2026；28 个主题", "",
        "## 批次汇总", "",
        f"- 本批学校数：{totals['schools']}",
        f"- 新增 source document 数：{totals['source_documents']}",
        f"- 新增原始文件数（HTML + 原始附件）：{totals['raw_files']}",
        f"- 新增总字节数：{totals['raw_bytes']}",
        f"- 新增 collected 覆盖格数：{totals['collected']}",
        f"- 仍 not_found 数：{totals['not_found']}",
        f"- access_restricted 数：{totals['access_restricted']}",
        f"- manual_download_required 数：{totals['manual_download_required']}",
        f"- privacy excluded 数：{totals['privacy_excluded']}", "",
        "## 分校明细", "",
    ]
    for row in school_rows:
        markdown.extend([
            f"### {row['school_id']} {row['school_name']}",
            f"- source documents：{row['source_documents']}",
            f"- 原始文件：{row['raw_files']}；{row['raw_bytes']} bytes",
            f"- collected：{row['collected']}；not_found：{row['not_found']}",
            f"- access_restricted：{row['access_restricted']}；manual_download_required：{row['manual_download_required']}；privacy excluded：{row['privacy_excluded']}",
        ])
        for year in YEARS:
            collected_topics = ", ".join(row["year_topics"][year]) if row["year_topics"][year] else "无"
            markdown.append(f"- {year} 已补主题：{collected_topics}")
        markdown.append("")
    markdown.extend([
        "## 质量说明", "",
        "- 仅保存学校官方域名返回的原始字节；搜索引擎仅用于发现和人工核验 URL。",
        "- HTML、PDF/DOC/DOCX/XLS/XLSX 等原件均记录 SHA-256、字节数、最终 URL 和检索时间。",
        "- parsed text 仅为派生文件，不能替代原始 HTML 或附件。",
        "- 拟录取名单、考生名单、考生号、准考证号、身份证号等候选人级数据在落盘前排除。",
        "- `not_found` 仅表示本轮定向深检仍未取得；不等同于 `official_not_published`。", "",
    ])
    (REPORT_ROOT / "p0_batch_01_audit.md").write_text("\n".join(markdown), encoding="utf-8")
    print(json.dumps(result["totals"], ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
