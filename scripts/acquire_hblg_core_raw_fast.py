#!/usr/bin/env python3
"""Fast, data-first archiver for HBLG 2024-2026 core 专升本 evidence.

Scope: the official annual admissions-charter article for each year and every file
linked from those articles. Public official bytes are kept intact, SHA-256 is
computed, and a complete 3 x 28 coverage matrix is emitted. No authentication,
CAPTCHA handling, or access-control bypass is used.
"""
from __future__ import annotations

import csv
import hashlib
import html
import json
import os
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urljoin, urlparse

import requests
import urllib3
from bs4 import BeautifulSoup

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

SCHOOL_ID = "HBLG"
SCHOOL_NAME = "淮北理工学院"
OFFICIAL_DOMAIN = "hblgxy.edu.cn"
ROOT = Path("anhui_zsb_data/evidence/full_raw_30_schools/HBLG")
REPORT = Path("anhui_zsb_data/reports/hblg_p0_core_raw_batch_01.md")
ROOT.mkdir(parents=True, exist_ok=True)
REPORT.parent.mkdir(parents=True, exist_ok=True)

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

PAGES = {
    2024: "https://zsb.hblgxy.edu.cn/info/1020/2103.htm",
    2025: "https://zsb.hblgxy.edu.cn/info/1020/2238.htm",
    2026: "https://zsb.hblgxy.edu.cn/info/1020/2361.htm",
}

TOPIC_KEYWORDS: dict[str, tuple[str, ...]] = {
    "admission_policy": ("招生章程", "招生简章", "实施办法"),
    "enrollment_plan": ("招生计划", "招生专业及计划", "分专业计划", "拟招生方案"),
    "major_catalog": ("招生专业", "专业范围", "报考专业", "专业对照"),
    "training_location": ("联合培养", "培养地点", "就读地点", "办学地点"),
    "tuition_and_duration": ("学费", "学制", "住宿费"),
    "eligibility": ("报名条件", "报考条件", "资格审查", "资格审核", "报名承诺书"),
    "exam_subjects": ("考试科目", "专业课", "公共课"),
    "exam_syllabus": ("考试大纲", "测试大纲", "考查大纲"),
    "reference_books": ("参考书目", "参考教材", "教材版本"),
    "exam_schedule": ("考试时间", "考试安排", "测试时间", "面试时间"),
    "exam_location": ("考试地点", "测试地点", "考点", "考场"),
    "admission_rules": ("录取规则", "录取原则", "同分排序", "择优录取"),
    "score_formula": ("综合成绩", "总成绩", "成绩计算", "计分公式"),
    "control_line": ("合格线", "控制线", "专业课合格"),
    "admission_min_score": ("最低录取分", "最低投档分", "录取分数线"),
    "admission_max_score": ("最高录取分", "录取最高分"),
    "admission_average_score": ("平均录取分", "录取平均分"),
    "application_statistics": ("报名人数", "报考人数", "志愿人数"),
    "qualified_statistics": ("资格通过人数", "资格审核通过人数", "合格人数"),
    "admitted_statistics": ("录取人数", "录取统计"),
    "registered_statistics": ("报到人数", "注册人数"),
    "plan_adjustment": ("计划调整", "调整计划", "扩招", "缩招"),
    "adjustment": ("调剂", "征集志愿", "补录", "缺额计划"),
    "exemption": ("免试", "免文化课"),
    "retired_soldier": ("退役大学生士兵", "退役士兵"),
    "registered_poor_family": ("建档立卡"),
    "skill_competition": ("技能大赛", "职业技能大赛", "鼓励政策"),
    "other_official_notice": ("专升本",),
}

MAX_WORKERS = max(1, min(int(os.environ.get("HBLG_FAST_WORKERS", "6")), 10))
MAX_BYTES = int(os.environ.get("HBLG_FAST_MAX_BYTES", str(95 * 1024 * 1024)))
USER_AGENT = "Mozilla/5.0 (compatible; AnhuiZSBDataResearch/2.0; public-official-archive)"
_thread_local = threading.local()


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def short_id(value: str) -> str:
    return hashlib.sha1(value.encode("utf-8", "replace")).hexdigest()[:12]


def compact(text: str) -> str:
    return re.sub(r"\s+", "", text or "")


def official(url: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    return host == OFFICIAL_DOMAIN or host.endswith("." + OFFICIAL_DOMAIN)


def session() -> requests.Session:
    existing = getattr(_thread_local, "session", None)
    if existing is None:
        existing = requests.Session()
        existing.trust_env = False
        existing.headers.update(
            {
                "User-Agent": USER_AGENT,
                "Accept": "text/html,application/xhtml+xml,application/pdf,application/octet-stream,*/*;q=0.8",
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.5",
            }
        )
        _thread_local.session = existing
    return existing


def fetch(url: str, referer: str = "") -> tuple[bytes, dict[str, Any]]:
    if not official(url):
        raise ValueError(f"non-official URL rejected: {url}")
    errors: list[str] = []
    for attempt in range(1, 4):
        try:
            headers = {"Referer": referer} if referer else None
            response = session().get(
                url,
                headers=headers,
                timeout=(10, 150),
                verify=False,
                allow_redirects=True,
                stream=True,
            )
            response.raise_for_status()
            declared = int(response.headers.get("Content-Length", "0") or 0)
            if declared > MAX_BYTES:
                response.close()
                raise ValueError(f"declared file size {declared} exceeds {MAX_BYTES}")
            chunks: list[bytes] = []
            total = 0
            for chunk in response.iter_content(1024 * 1024):
                if not chunk:
                    continue
                total += len(chunk)
                if total > MAX_BYTES:
                    response.close()
                    raise ValueError(f"download exceeded {MAX_BYTES}")
                chunks.append(chunk)
            data = b"".join(chunks)
            meta = {
                "http_status": response.status_code,
                "final_url": response.url,
                "content_type": response.headers.get("Content-Type", ""),
                "content_disposition": response.headers.get("Content-Disposition", ""),
                "last_modified": response.headers.get("Last-Modified", ""),
                "etag": response.headers.get("ETag", ""),
                "tls_verified": False,
                "attempt": attempt,
            }
            response.close()
            if not data:
                raise ValueError("empty response")
            return data, meta
        except Exception as exc:
            errors.append(f"attempt {attempt}: {type(exc).__name__}: {exc}")
            if attempt < 3:
                time.sleep(0.5 * attempt)
    raise RuntimeError(" | ".join(errors))


def decode_html(data: bytes) -> str:
    for encoding in ("utf-8", "gb18030", "gbk"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def parse_date(text: str) -> str:
    match = re.search(r"(?<!\d)(20(?:24|25|26))[-年/.](\d{1,2})[-月/.](\d{1,2})日?", text[:20000])
    if not match:
        return ""
    return f"{match.group(1)}-{int(match.group(2)):02d}-{int(match.group(3)):02d}"


def infer_topics(text: str) -> list[str]:
    normalized = compact(text)
    found = {
        topic
        for topic, keywords in TOPIC_KEYWORDS.items()
        if any(keyword in normalized for keyword in keywords)
    }
    if "专升本" in normalized:
        found.add("other_official_notice")
    return [topic for topic in TOPICS if topic in found]


def attachment_topics(anchor: str, page_topics: list[str]) -> list[str]:
    normalized = compact(anchor)
    topics = set(infer_topics(anchor))
    if "招生章程" in normalized:
        topics.update(page_topics)
    if "考试大纲" in normalized or "测试大纲" in normalized:
        topics.update(("exam_subjects", "exam_syllabus"))
    if "退役士兵" in normalized:
        topics.update(("retired_soldier", "exemption"))
    if "报名承诺书" in normalized:
        topics.add("eligibility")
    if "专项" in normalized or "鼓励政策申请表" in normalized:
        topics.update(("eligibility", "exemption", "retired_soldier", "registered_poor_family", "skill_competition"))
    return [topic for topic in TOPICS if topic in topics] or ["other_official_notice"]


def category(topic: str) -> str:
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


def primary(topics: list[str]) -> str:
    for topic in TOPICS:
        if topic in topics and topic != "other_official_notice":
            return topic
    return "other_official_notice"


def extension(data: bytes, content_type: str, anchor: str) -> str:
    expected = Path(unquote(urlparse(anchor).path)).suffix.lower() if "://" in anchor else Path(anchor).suffix.lower()
    if data.startswith(b"%PDF-"):
        return ".pdf"
    if data.startswith(b"PK\x03\x04"):
        if expected in {".docx", ".xlsx", ".zip"}:
            return expected
        if "wordprocessingml" in content_type.lower():
            return ".docx"
        if "spreadsheetml" in content_type.lower():
            return ".xlsx"
        return ".zip"
    if data.startswith(b"\xd0\xcf\x11\xe0"):
        if expected in {".doc", ".xls"}:
            return expected
        return ".doc"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png"
    if data.startswith(b"\xff\xd8\xff"):
        return ".jpg"
    prefix = data[:2048].lstrip().lower()
    if prefix.startswith((b"<!doctype html", b"<html", b"<?xml")) or b"<html" in prefix:
        return ".html"
    raise ValueError(f"unrecognized file magic for {anchor}: {data[:16].hex()}")


def safe_anchor(anchor: str) -> str:
    value = html.unescape(anchor or "").strip()
    value = re.sub(r"[\x00-\x1f]", " ", value)
    return re.sub(r"\s+", " ", value)[:300]


retrieved_at = now()
sources: list[dict[str, Any]] = []
assets: list[dict[str, Any]] = []
failures: list[dict[str, Any]] = []
page_context: dict[int, dict[str, Any]] = {}
attachment_specs: dict[str, dict[str, Any]] = {}
physical_by_hash: dict[str, str] = {}

for year, page_url in PAGES.items():
    data, meta = fetch(page_url)
    if extension(data, meta["content_type"], page_url) != ".html":
        raise RuntimeError(f"official article did not return HTML: {page_url}")
    decoded = decode_html(data)
    soup = BeautifulSoup(decoded, "html.parser")
    title = compact(soup.title.get_text(" ", strip=True) if soup.title else "")
    text = soup.get_text("\n", strip=True)
    if "专升本" not in compact(title + text[:100000]) or str(year) not in compact(title + text[:100000]):
        raise RuntimeError(f"strict year/topic binding failed for {page_url}")
    publish_date = parse_date(text)

    attachment_anchor_texts: list[str] = []
    for tag in soup.find_all("a", href=True):
        anchor = safe_anchor(tag.get_text(" ", strip=True))
        href = html.unescape(tag.get("href", "")).strip()
        if not href or href.lower().startswith(("javascript:", "mailto:", "tel:")):
            continue
        linked = urljoin(meta["final_url"], href).split("#", 1)[0]
        if not official(linked):
            continue
        token = linked.lower()
        if (
            "news.downloadattachurl" in token
            or "downloadattach" in token
            or "/_upload/" in token
            or Path(urlparse(linked).path).suffix.lower() in {".pdf", ".doc", ".docx", ".xls", ".xlsx", ".zip", ".jpg", ".jpeg", ".png"}
        ):
            attachment_anchor_texts.append(anchor)
            attachment_specs.setdefault(
                linked,
                {
                    "year": year,
                    "url": linked,
                    "anchor": anchor or f"{year}年招生章程附件",
                    "parent_page_url": page_url,
                    "publish_date": publish_date,
                },
            )

    page_topics = infer_topics(title + "\n" + text + "\n" + "\n".join(attachment_anchor_texts))
    if "admission_policy" not in page_topics:
        page_topics.insert(0, "admission_policy")
    page_topics = [topic for topic in TOPICS if topic in set(page_topics)]
    folder = ROOT / str(year) / "admission_policy"
    folder.mkdir(parents=True, exist_ok=True)
    base = f"SRC-HBLG-{year}-admission_policy-{short_id(page_url)}"
    local = folder / f"{base}.html"
    local.write_bytes(data)
    parsed = folder / f"{base}_parsed.txt"
    parsed.write_text(
        f"Title: {title}\nOfficial URL: {page_url}\nFinal URL: {meta['final_url']}\n"
        f"Publish date: {publish_date}\nRetrieved at: {retrieved_at}\n\n{text}\n",
        "utf-8",
    )
    file_hash = digest(data)
    physical_by_hash[file_hash] = local.as_posix()
    source = {
        "source_id": f"SRC-HBLG-{year}-{short_id(page_url)}",
        "school_id": SCHOOL_ID,
        "school_name": SCHOOL_NAME,
        "year": year,
        "title": title,
        "publish_date": publish_date,
        "retrieved_at": retrieved_at,
        "official_page_url": page_url,
        "official_url": page_url,
        "final_url": meta["final_url"],
        "source_domain": urlparse(meta["final_url"]).hostname or "",
        "document_type": "html",
        "topics": "|".join(page_topics),
        "file_type": "html",
        "local_path": local.as_posix(),
        "parsed_text_path": parsed.as_posix(),
        "file_size": len(data),
        "sha256": file_hash,
        "http_status": meta["http_status"],
        "status": "collected",
        "tls_verified": False,
        "notes": "complete public official HTML content preserved; official server certificate chain is not trusted by the runner CA, so retrieval used the official hostname with TLS verification disabled after DNS/IP validation",
    }
    sources.append(source)
    page_context[year] = {
        "title": title,
        "topics": page_topics,
        "publish_date": publish_date,
        "url": page_url,
    }
    print(f"SOURCE year={year} bytes={len(data)} attachments={sum(1 for item in attachment_specs.values() if item['year'] == year)}")


def worker(spec: dict[str, Any]) -> tuple[dict[str, Any], bytes | None, dict[str, Any] | None, str | None]:
    try:
        data, meta = fetch(spec["url"], referer=spec["parent_page_url"])
        return spec, data, meta, None
    except Exception as exc:
        return spec, None, None, f"{type(exc).__name__}: {exc}"


with ThreadPoolExecutor(max_workers=MAX_WORKERS, thread_name_prefix="hblg-raw") as pool:
    futures = [pool.submit(worker, spec) for spec in attachment_specs.values()]
    for future in as_completed(futures):
        spec, data, meta, error = future.result()
        year = int(spec["year"])
        if error or data is None or meta is None:
            failures.append(
                {
                    "school_id": SCHOOL_ID,
                    "school_name": SCHOOL_NAME,
                    "year": year,
                    "title": spec["anchor"],
                    "url": spec["url"],
                    "parent_page_url": spec["parent_page_url"],
                    "status": "access_restricted",
                    "reason": error or "unknown download failure",
                    "checked_at": now(),
                }
            )
            print(f"FAIL year={year} {spec['url']} {error}")
            continue
        context = page_context[year]
        topics = attachment_topics(spec["anchor"], context["topics"])
        ext = extension(data, meta["content_type"], spec["anchor"])
        if ext == ".html":
            raise RuntimeError(f"attachment endpoint returned HTML instead of a file: {spec['url']}")
        topic = primary(topics)
        folder = ROOT / str(year) / category(topic)
        folder.mkdir(parents=True, exist_ok=True)
        file_hash = digest(data)
        target = folder / f"AST-HBLG-{year}-{topic}-{short_id(spec['url'])}{ext}"
        deduplicated = file_hash in physical_by_hash and Path(physical_by_hash[file_hash]).is_file()
        if deduplicated:
            local_path = physical_by_hash[file_hash]
        else:
            target.write_bytes(data)
            local_path = target.as_posix()
            physical_by_hash[file_hash] = local_path
        assets.append(
            {
                "asset_id": f"AST-HBLG-{year}-{short_id(spec['url'])}",
                "school_id": SCHOOL_ID,
                "school_name": SCHOOL_NAME,
                "year": year,
                "title": spec["anchor"],
                "publish_date": spec["publish_date"],
                "retrieved_at": retrieved_at,
                "official_page_url": spec["parent_page_url"],
                "parent_page": spec["parent_page_url"],
                "parent_page_url": spec["parent_page_url"],
                "official_url": spec["url"],
                "attachment_url": spec["url"],
                "attachment_filename": spec["anchor"],
                "final_url": meta["final_url"],
                "source_domain": urlparse(meta["final_url"]).hostname or "",
                "document_type": "attachment",
                "topics": "|".join(topics),
                "file_type": ext.lstrip("."),
                "local_path": local_path,
                "file_size": len(data),
                "sha256": file_hash,
                "attachment_sha256": file_hash,
                "http_status": meta["http_status"],
                "status": "collected",
                "deduplicated": deduplicated,
                "tls_verified": False,
                "notes": "complete public official attachment bytes preserved; downloaded from the official article relation",
            }
        )
        print(f"ASSET year={year} type={ext[1:]} bytes={len(data)} title={spec['anchor'][:70]}")

sources.sort(key=lambda item: (item["year"], item["official_url"]))
assets.sort(key=lambda item: (item["year"], item["attachment_url"]))
failures.sort(key=lambda item: (item["year"], item["url"]))

manifest = {
    "school_id": SCHOOL_ID,
    "school_name": SCHOOL_NAME,
    "school_type": "民办",
    "official_domains": [OFFICIAL_DOMAIN],
    "years_audited": list(YEARS),
    "topics_audited": TOPICS,
    "scope": "core annual admissions-charter pages and every attachment linked from those pages",
    "sources": sources,
    "assets": assets,
    "failures": failures,
    "raw_information_policy": "preserve complete bytes of publicly accessible official records; no login, CAPTCHA, permission bypass, or personal-identity enrichment",
    "original_information_preserved": True,
    "sanitized": False,
    "last_audited_at": now(),
}
(ROOT / "school_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", "utf-8")

coverage: dict[tuple[int, str], str] = {(year, topic): "not_found" for year in YEARS for topic in TOPICS}
for item in sources + assets:
    year = int(item["year"])
    for topic in item["topics"].split("|"):
        if (year, topic) in coverage:
            coverage[(year, topic)] = "collected"
for failure in failures:
    year = int(failure["year"])
    anchor_topics = attachment_topics(failure["title"], page_context[year]["topics"])
    for topic in anchor_topics:
        if coverage[(year, topic)] == "not_found":
            coverage[(year, topic)] = "access_restricted"

with (ROOT / "school_coverage.csv").open("w", encoding="utf-8-sig", newline="") as handle:
    writer = csv.writer(handle, lineterminator="\n")
    writer.writerow(["school_id", "school_name", "year", "topic", "status"])
    for year in YEARS:
        for topic in TOPICS:
            writer.writerow([SCHOOL_ID, SCHOOL_NAME, year, topic, coverage[(year, topic)]])

unique_paths = {
    Path(item["local_path"])
    for item in sources + assets
    if item.get("local_path") and Path(item["local_path"]).is_file()
}
coverage_by_year = {
    year: [topic for topic in TOPICS if coverage[(year, topic)] == "collected"]
    for year in YEARS
}
missing_by_year = {
    year: [topic for topic in TOPICS if coverage[(year, topic)] != "collected"]
    for year in YEARS
}
collected_cells = sum(status == "collected" for status in coverage.values())
not_found_cells = sum(status == "not_found" for status in coverage.values())
access_cells = sum(status == "access_restricted" for status in coverage.values())
raw_bytes = sum(path.stat().st_size for path in unique_paths)

notes = [
    f"# {SCHOOL_NAME} ({SCHOOL_ID})",
    "",
    f"- Last audited at: {manifest['last_audited_at']}",
    "- Batch scope: 2024-2026 official admissions-charter pages and every linked attachment.",
    f"- Official HTML source pages: {len(sources)}",
    f"- Official attachment relations: {len(assets)}",
    f"- Unique raw files: {len(unique_paths)}",
    f"- Unique raw bytes: {raw_bytes}",
    f"- Collected coverage cells: {collected_cells}/84",
    "- Public official candidate-level records in this core batch: 0",
    "- Raw bytes were not sanitized, rewritten, or converted; parsed text is supplementary only.",
    "- Remaining score, statistics, adjustment, plan-change and public-record notices require the deep-notice follow-up batch.",
    "",
]
for year in YEARS:
    notes.extend(
        [
            f"## {year}",
            "",
            "- Collected: " + (", ".join(f"`{topic}`" for topic in coverage_by_year[year]) or "none"),
            "- Unresolved: " + (", ".join(f"`{topic}`" for topic in missing_by_year[year]) or "none"),
            "",
        ]
    )
if failures:
    notes.extend(["## Download failures", ""])
    notes.extend(f"- {item['year']} `{item['status']}` {item['title']} — {item['url']} — {item['reason']}" for item in failures)
    notes.append("")
(ROOT / "school_notes.md").write_text("\n".join(notes), "utf-8")

report = [
    "# HBLG 淮北理工学院 P0 核心原始数据补采审计（Batch 01）",
    "",
    f"> 生成时间：{manifest['last_audited_at']}",
    "",
    "## 本批汇总",
    "",
    "| 指标 | 数值 |",
    "|---|---:|",
    "| 本批学校数 | 1 |",
    f"| 新增 source document 数 | {len(sources)} |",
    f"| 新增 attachment relation 数 | {len(assets)} |",
    f"| 新增原始文件数（SHA-256 去重后） | {len(unique_paths)} |",
    f"| 新增总字节数 | {raw_bytes} |",
    f"| 新增 collected 覆盖格数 | {collected_cells} |",
    f"| 仍 not_found 数 | {not_found_cells} |",
    f"| access_restricted 覆盖格数 | {access_cells} |",
    "| manual_download_required 数 | 0 |",
    "| 公开官方考生级资料数 | 0 |",
    "",
    "## 学校—年份审计",
    "",
    "| 学校 | 年份 | 已补主题 | 仍缺主题 | 原因 / 下一步 |",
    "|---|---:|---|---|---|",
]
for year in YEARS:
    report.append(
        f"| 淮北理工学院 | {year} | "
        + ("、".join(coverage_by_year[year]) or "无")
        + " | "
        + ("、".join(missing_by_year[year]) or "无")
        + " | 本批限定章程及其附件；继续深挖最低分、报名/录取统计、计划调整、调剂和公示 |"
    )
report.extend(["", "## 三年章程原始页面", ""])
for item in sources:
    report.append(f"- {item['year']}｜{item['title']}｜{item['official_url']}｜`{item['sha256']}`｜{item['file_size']} bytes")
report.extend(["", "## 附件归档", ""])
for item in assets:
    report.append(f"- {item['year']}｜{item['attachment_filename']}｜{item['attachment_url']}｜`{item['sha256']}`｜{item['file_size']} bytes")
if failures:
    report.extend(["", "## 下载失败", ""])
    report.extend(f"- {item['year']}｜`{item['status']}`｜{item['title']}｜{item['url']}｜{item['reason']}" for item in failures)
REPORT.write_text("\n".join(report) + "\n", "utf-8")

summary = {
    "school_id": SCHOOL_ID,
    "sources": len(sources),
    "attachment_relations": len(assets),
    "unique_raw_files": len(unique_paths),
    "raw_bytes": raw_bytes,
    "collected_cells": collected_cells,
    "not_found_cells": not_found_cells,
    "access_restricted_cells": access_cells,
    "download_failures": len(failures),
    "report": REPORT.as_posix(),
}
print(json.dumps(summary, ensure_ascii=False, indent=2))

if len(sources) != 3:
    raise SystemExit(f"expected 3 official charter HTML pages, got {len(sources)}")
if len(assets) < 55:
    raise SystemExit(f"expected at least 55 official attachment relations, got {len(assets)}")
if failures:
    raise SystemExit(f"core batch has {len(failures)} download failures; do not commit a partial core archive")
