#!/usr/bin/env python3
"""Acquire public official 2024-2026 BZU (亳州学院) raw evidence.

Only original bytes returned from the allow-listed official domain are persisted.
Search engines are discovery-only. Candidate-level personal records are excluded.
Every unsuccessful retrieval remains an explicit auditable status.
"""
from __future__ import annotations

import csv
import hashlib
import html
import itertools
import json
import os
import re
import struct
import subprocess
import tempfile
import time
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qs, unquote, urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

SCHOOL_ID = "BZU"
SCHOOL_NAME = "亳州学院"
DOMAIN = "bzuu.edu.cn"
YEARS = (2024, 2025, 2026)
ROOT = Path("anhui_zsb_data/evidence/full_raw_30_schools/BZU")
REPORT = Path("anhui_zsb_data/reports/p0_batch_02_bzu_audit.md")
ROOT.mkdir(parents=True, exist_ok=True)
REPORT.parent.mkdir(parents=True, exist_ok=True)
MAX_PAGES = int(os.environ.get("BZU_MAX_PAGES", "100"))
DEADLINE = time.monotonic() + int(os.environ.get("BZU_TOTAL_TIMEOUT", "900"))
REQUEST_TIMEOUT = int(os.environ.get("BZU_REQUEST_TIMEOUT", "30"))
MAX_FILE = 100 * 1024 * 1024

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
    "admission_policy": ["招生章程", "招生简章"],
    "enrollment_plan": ["招生计划", "拟招生方案"],
    "major_catalog": ["招生专业", "专业招生范围"],
    "training_location": ["联合培养", "培养地点", "培养校区"],
    "tuition_and_duration": ["学费", "学制"],
    "eligibility": ["报名条件", "报考范围", "资格条件"],
    "exam_subjects": ["考试科目", "专业课", "公共课"],
    "exam_syllabus": ["考试大纲", "测试大纲", "考查大纲"],
    "reference_books": ["参考书目", "参考教材"],
    "exam_schedule": ["考试时间", "考试安排"],
    "exam_location": ["考试地点", "考点", "考场"],
    "admission_rules": ["录取规则", "录取细则", "同分排序"],
    "score_formula": ["计分公式", "综合成绩", "总成绩"],
    "control_line": ["合格线", "控制线", "专业课合格"],
    "admission_min_score": ["最低录取分", "最低投档分", "录取分数线", "预录取分数线"],
    "admission_max_score": ["最高录取分", "录取最高分"],
    "admission_average_score": ["平均录取分", "录取平均分"],
    "application_statistics": ["报考人数", "报名人数", "报考志愿数"],
    "qualified_statistics": ["资格审核通过人数", "资格通过人数"],
    "admitted_statistics": ["录取人数", "录取统计"],
    "registered_statistics": ["报到人数", "注册人数"],
    "plan_adjustment": ["计划调整", "调整计划", "扩招", "缩招"],
    "adjustment": ["调剂", "补录", "征集志愿"],
    "exemption": ["免试", "免文化课"],
    "retired_soldier": ["退役大学生士兵", "退役士兵"],
    "registered_poor_family": ["建档立卡"],
    "skill_competition": ["技能大赛", "职业技能大赛"],
    "other_official_notice": ["专升本"],
}
RELEVANT = sorted({word for values in TOPIC_KW.values() for word in values}, key=len, reverse=True)
PRIVACY = [
    "拟录取名单", "预录取名单", "录取名单", "考生名单", "面试名单",
    "审核名单", "免试名单", "成绩名单", "成绩查询", "录取查询",
    "考生号", "准考证号", "身份证号",
]
FILE_EXTS = {".pdf", ".doc", ".docx", ".xls", ".xlsx", ".csv", ".zip"}
SEEDS = [
    "https://www.bzuu.edu.cn/zzzs/",
    "https://www.bzuu.edu.cn/",
    "https://www.bzuu.edu.cn/sitemap.xml",
    "https://www.bzuu.edu.cn/robots.txt",
    "http://www.bzuu.edu.cn/zzzs/",
]

session = requests.Session()
retry = Retry(total=1, connect=1, read=1, backoff_factor=.5,
              status_forcelist=[429, 500, 502, 503, 504], allowed_methods=["GET"])
session.mount("https://", HTTPAdapter(max_retries=retry))
session.mount("http://", HTTPAdapter(max_retries=retry))
session.headers.update({
    "User-Agent": "Mozilla/5.0 (compatible; AnhuiZSBDataResearch/1.2; public research)",
    "Accept": "*/*",
})

attempts: list[dict] = []
sources: list[dict] = []
assets: list[dict] = []
failures: list[dict] = []
discovery: list[dict] = []
privacy_exclusions: list[dict] = []
coverage = {(year, topic): "not_found" for year in YEARS for topic in TOPICS}
saved_urls: set[tuple[int, str]] = set()
doh_cache: dict[str, list[str]] = {}


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def short(value: str) -> str:
    return hashlib.sha1(value.encode("utf-8", "replace")).hexdigest()[:10]


def compact(value: str) -> str:
    return re.sub(r"\s+", "", value or "")


def clean_url(value: str) -> str:
    value = html.unescape(value or "").strip().split("#", 1)[0]
    if value.startswith("//"):
        value = "https:" + value
    return value


def allowed(url: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    return host == DOMAIN or host.endswith("." + DOMAIN)


def privacy_hit(value: str) -> str | None:
    text = compact(value)
    return next((keyword for keyword in PRIVACY if keyword in text), None)


def detect_year(value: str, url: str) -> int | None:
    merged = compact(value) + url
    found = {year for year in YEARS if str(year) in merged}
    return next(iter(found)) if len(found) == 1 else None


def detect_topics(value: str) -> list[str]:
    text = compact(value)
    result = [topic for topic, keywords in TOPIC_KW.items() if any(k in text for k in keywords)]
    return result or (["other_official_notice"] if "专升本" in text else [])


def primary_topic(topics: list[str]) -> str:
    return next((topic for topic in TOPICS if topic in topics and topic != "other_official_notice"),
                "other_official_notice")


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


def resolve_ipv4(host: str) -> list[str]:
    if host in doh_cache:
        return doh_cache[host]
    addresses: list[str] = []
    providers = [
        f"https://cloudflare-dns.com/dns-query?name={host}&type=A",
        f"https://dns.google/resolve?name={host}&type=A",
    ]
    for endpoint in providers:
        try:
            response = requests.get(endpoint, headers={"Accept": "application/dns-json"}, timeout=10)
            payload = response.json()
            for answer in payload.get("Answer", []):
                value = str(answer.get("data", ""))
                if re.fullmatch(r"\d{1,3}(?:\.\d{1,3}){3}", value):
                    addresses.append(value)
        except Exception:
            continue
    doh_cache[host] = list(dict.fromkeys(addresses))
    return doh_cache[host]


def curl_fetch(url: str, ip: str | None = None) -> tuple[bytes | None, dict]:
    parsed = urlparse(url)
    host = parsed.hostname or ""
    port = 443 if parsed.scheme == "https" else 80
    with tempfile.TemporaryDirectory() as tmp:
        body_path = Path(tmp) / "body"
        meta_path = Path(tmp) / "meta"
        command = [
            "curl", "--location", "--silent", "--show-error", "--http1.1",
            "--connect-timeout", "10", "--max-time", str(REQUEST_TIMEOUT),
            "--max-filesize", str(MAX_FILE),
            "--user-agent", session.headers["User-Agent"],
            "--output", str(body_path),
            "--write-out", "%{http_code}\n%{url_effective}\n%{content_type}\n%{size_download}\n",
            url,
        ]
        if ip:
            command[1:1] = ["--resolve", f"{host}:{port}:{ip}"]
        started = time.monotonic()
        result = subprocess.run(command, capture_output=True, text=True, timeout=REQUEST_TIMEOUT + 8)
        elapsed = round(time.monotonic() - started, 3)
        lines = result.stdout.splitlines()
        meta = {
            "transport": "curl-resolve" if ip else "curl",
            "resolved_ip": ip or "",
            "status": int(lines[0]) if lines and lines[0].isdigit() else "error",
            "final_url": lines[1] if len(lines) > 1 else url,
            "content_type": lines[2] if len(lines) > 2 else "",
            "size": int(float(lines[3])) if len(lines) > 3 and lines[3] else 0,
            "elapsed_seconds": elapsed,
            "stderr": result.stderr[-2000:],
        }
        if result.returncode != 0 or not body_path.exists():
            return None, meta
        data = body_path.read_bytes()
        meta["size"] = len(data)
        meta["sha256"] = sha256(data)
        if isinstance(meta["status"], int) and meta["status"] >= 400:
            return None, meta
        return data, meta


def fetch(url: str) -> tuple[bytes | None, dict]:
    if time.monotonic() >= DEADLINE:
        return None, {"status": "deadline", "final_url": url, "error": "wall-clock deadline reached"}
    transports: list[tuple[str, str | None]] = [("requests", None), ("curl", None)]
    host = urlparse(url).hostname or ""
    for address in resolve_ipv4(host):
        transports.append(("curl-resolve", address))
    last: dict = {"status": "error", "final_url": url, "error": "no transport attempted"}
    for transport, address in transports:
        started = time.monotonic()
        try:
            if transport == "requests":
                response = session.get(url, timeout=(10, REQUEST_TIMEOUT), allow_redirects=True)
                data = response.content
                meta = {
                    "transport": transport,
                    "resolved_ip": "",
                    "status": response.status_code,
                    "final_url": response.url,
                    "content_type": response.headers.get("Content-Type", ""),
                    "content_disposition": response.headers.get("Content-Disposition", ""),
                    "size": len(data),
                    "sha256": sha256(data),
                    "elapsed_seconds": round(time.monotonic() - started, 3),
                }
                if response.status_code >= 400:
                    data = None
            else:
                data, meta = curl_fetch(url, address)
        except Exception as exc:
            data = None
            meta = {
                "transport": transport,
                "resolved_ip": address or "",
                "status": "error",
                "final_url": url,
                "error": repr(exc),
                "elapsed_seconds": round(time.monotonic() - started, 3),
            }
        record = {"retrieved_at": now(), "url": url, **meta}
        attempts.append(record)
        last = meta
        final_url = str(meta.get("final_url") or url)
        if data is not None and allowed(final_url) and len(data) <= MAX_FILE:
            return data, meta
        if time.monotonic() >= DEADLINE:
            break
    return None, last


def search_discovery_urls() -> list[str]:
    found: list[str] = []
    for year in YEARS:
        queries = [
            f"site:bzuu.edu.cn 专升本 {year} 亳州学院",
            f"site:bzuu.edu.cn/zzzs 专升本 {year}",
        ]
        for query in queries:
            if time.monotonic() >= DEADLINE:
                break
            endpoint = "https://www.bing.com/search?q=" + requests.utils.quote(query)
            try:
                response = requests.get(endpoint, headers={"User-Agent": session.headers["User-Agent"]}, timeout=15)
                soup = BeautifulSoup(response.content, "html.parser")
                for anchor in soup.find_all("a", href=True):
                    href = clean_url(anchor.get("href", ""))
                    if href.startswith("https://www.bing.com/ck/a"):
                        query_values = parse_qs(urlparse(href).query)
                        href = query_values.get("u", [href])[0]
                    if allowed(href):
                        found.append(href)
                discovery.append({
                    "source": "search_engine_discovery_only", "query": query,
                    "status": response.status_code, "retrieved_at": now(),
                })
            except Exception as exc:
                discovery.append({
                    "source": "search_engine_discovery_only", "query": query,
                    "status": "error", "reason": repr(exc), "retrieved_at": now(),
                })
    return list(dict.fromkeys(found))


queue: deque[tuple[str, str, str]] = deque((seed, "", "seed") for seed in SEEDS)
for discovered in search_discovery_urls():
    queue.append((discovered, "", "search_discovery"))
visited: set[str] = set()
pages = 0

while queue and pages < MAX_PAGES and time.monotonic() < DEADLINE:
    url, parent, origin = queue.popleft()
    url = clean_url(url)
    if not url or url in visited or not allowed(url):
        continue
    visited.add(url)
    data, meta = fetch(url)
    if data is None:
        failures.append({
            "school_id": SCHOOL_ID, "school_name": SCHOOL_NAME,
            "year": detect_year(url, url), "url": url, "parent_url": parent,
            "status": "access_restricted", "http_status": meta.get("status"),
            "reason": meta.get("error") or meta.get("stderr") or f"HTTP {meta.get('status')}",
            "transport": meta.get("transport", ""), "retrieved_at": now(),
        })
        continue
    final_url = str(meta.get("final_url") or url)
    if not allowed(final_url):
        failures.append({
            "url": url, "parent_url": parent, "status": "removed_or_unavailable",
            "reason": f"redirected outside official allowlist: {final_url}", "retrieved_at": now(),
        })
        continue

    ext = Path(urlparse(final_url).path).suffix.lower()
    content_type = str(meta.get("content_type", "")).lower()
    looks_html = "html" in content_type or data.lstrip()[:100].lower().startswith((b"<!doctype", b"<html", b"<?xml"))
    is_attachment = ext in FILE_EXTS or not looks_html

    if is_attachment:
        label = unquote(Path(urlparse(final_url).path).name)
        context = f"{label} {parent} {url}"
        hit = privacy_hit(context)
        year = detect_year(context, final_url)
        topics = detect_topics(context)
        if hit:
            privacy_exclusions.append({"url": final_url, "parent_url": parent, "reason": hit, "retrieved_at": now()})
            continue
        if not year or not topics:
            discovery.append({"url": final_url, "parent_url": parent, "status": "unbound_official_attachment", "retrieved_at": now()})
            continue
        topic = primary_topic(topics)
        suffix = ext if ext else ".bin"
        relative = Path(str(year)) / topic_dir(topic) / f"ASSET-{SCHOOL_ID}-{year}-{topic}-{short(final_url)}{suffix}"
        path = ROOT / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        assets.append({
            "school_id": SCHOOL_ID, "school_name": SCHOOL_NAME, "year": year,
            "asset_id": f"ASSET-{SCHOOL_ID}-{year}-{short(final_url)}",
            "document_type": suffix.lstrip("."), "topics": "|".join(topics), "title": label,
            "official_url": url, "final_url": final_url, "parent_page_url": parent,
            "retrieved_at": now(), "official_domain": urlparse(final_url).hostname,
            "source_level": "school_official", "http_status": meta.get("status"),
            "content_type": meta.get("content_type", ""), "status": "collected", "notes": origin,
            "local_path": str(Path("anhui_zsb_data/evidence/full_raw_30_schools/BZU") / relative),
            "sha256": sha256(data), "file_size": len(data),
        })
        for topic_name in topics:
            coverage[(year, topic_name)] = "collected"
        saved_urls.add((year, final_url))
        continue

    pages += 1
    text = data.decode("utf-8", "replace")
    soup = BeautifulSoup(text, "html.parser")
    title = soup.title.get_text(" ", strip=True) if soup.title else ""
    visible = soup.get_text(" ", strip=True)
    context = f"{title} {visible[:18000]}"
    hit = privacy_hit(context)
    year = detect_year(context, final_url)
    topics = detect_topics(context)
    relevant = "专升本" in compact(context) or any(word in compact(context) for word in RELEVANT)

    if hit:
        privacy_exclusions.append({"url": final_url, "parent_url": parent, "reason": hit, "retrieved_at": now()})
    elif year and topics and relevant and (year, final_url) not in saved_urls:
        topic = primary_topic(topics)
        relative = Path(str(year)) / topic_dir(topic) / f"DOC-{SCHOOL_ID}-{year}-{topic}-{short(final_url)}.html"
        path = ROOT / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        parsed = path.with_name(path.stem + "_parsed.txt")
        parsed.write_text(visible, encoding="utf-8")
        sources.append({
            "school_id": SCHOOL_ID, "school_name": SCHOOL_NAME, "year": year,
            "source_id": f"SRC-{SCHOOL_ID}-{year}-{short(final_url)}", "document_type": "html",
            "topics": "|".join(topics), "title": title, "official_url": url,
            "final_url": final_url, "parent_page_url": parent, "publish_date": "",
            "retrieved_at": now(), "official_domain": urlparse(final_url).hostname,
            "source_level": "school_official", "http_status": meta.get("status"),
            "content_type": meta.get("content_type", ""), "status": "collected", "notes": origin,
            "local_path": str(Path("anhui_zsb_data/evidence/full_raw_30_schools/BZU") / relative),
            "sha256": sha256(data), "file_size": len(data),
        })
        for topic_name in topics:
            coverage[(year, topic_name)] = "collected"
        saved_urls.add((year, final_url))

    links: list[tuple[int, str]] = []
    for anchor in soup.find_all("a", href=True):
        href = clean_url(urljoin(final_url, anchor.get("href", "")))
        if not href or href in visited or not allowed(href):
            continue
        label = anchor.get_text(" ", strip=True)
        combined = compact(label + " " + href)
        score = 0
        if "专升本" in combined:
            score += 100
        if any(str(year_value) in combined for year_value in YEARS):
            score += 40
        if any(keyword in combined for keyword in RELEVANT):
            score += 30
        if Path(urlparse(href).path).suffix.lower() in FILE_EXTS:
            score += 20
        if "/zzzs/" in href:
            score += 10
        links.append((score, href))
    for _, href in sorted(links, key=lambda item: item[0], reverse=True):
        queue.append((href, final_url, "official_crawl"))

# Preserve truthful unresolved states. A reachable crawl with no matching publication is not
# proof that a record never existed; such cells require manual review.
if attempts:
    for key, value in list(coverage.items()):
        if value == "not_found":
            coverage[key] = "awaiting_manual_review"

with (ROOT / "school_coverage.csv").open("w", encoding="utf-8-sig", newline="") as handle:
    writer = csv.writer(handle)
    writer.writerow(["school_id", "school_name", "year", "topic", "status"])
    for year in YEARS:
        for topic in TOPICS:
            writer.writerow([SCHOOL_ID, SCHOOL_NAME, year, topic, coverage[(year, topic)]])

manifest = {
    "school_id": SCHOOL_ID, "school_name": SCHOOL_NAME, "official_domains": [DOMAIN],
    "sources": sources, "assets": assets, "failures": failures,
    "privacy_exclusions": privacy_exclusions, "discovery": discovery,
    "sanitized": True, "generated_at": now(),
}
(ROOT / "school_manifest.json").write_text(
    json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
)
(ROOT / "source_discovery.json").write_text(
    json.dumps({"school_id": SCHOOL_ID, "entries": discovery,
                "privacy_exclusions": privacy_exclusions}, ensure_ascii=False, indent=2) + "\n",
    encoding="utf-8",
)
with (ROOT / "retrieval_attempts.jsonl").open("w", encoding="utf-8") as handle:
    for item in attempts:
        handle.write(json.dumps(item, ensure_ascii=False) + "\n")

status_counts: dict[str, int] = {}
for status in coverage.values():
    status_counts[status] = status_counts.get(status, 0) + 1
notes = [
    f"# {SCHOOL_NAME} ({SCHOOL_ID}) P0 原始证据采集", "",
    f"- 采集时间：{now()}", f"- 官方域名：`{DOMAIN}`",
    f"- 已保存官方来源页面：{len(sources)}", f"- 已保存官方附件：{len(assets)}",
    f"- 检索尝试：{len(attempts)}", f"- 访问失败：{len(failures)}",
    f"- 隐私排除：{len(privacy_exclusions)}", "",
    "仅实际取得官方原始字节的资料标记为 `collected`；发现线索、访问失败和候选人名单不冒充正式原件。", "",
]
(ROOT / "school_notes.md").write_text("\n".join(notes), encoding="utf-8")
report_lines = [
    "# BZU P0 原始数据采集审计", "",
    f"- 学校：{SCHOOL_NAME}（{SCHOOL_ID}）", "- 年份：2024–2026",
    f"- 覆盖单元：{len(coverage)}", f"- 官方页面原件：{len(sources)}",
    f"- 官方附件原件：{len(assets)}", f"- 检索尝试：{len(attempts)}",
    f"- 访问失败：{len(failures)}", "", "## 状态统计", "",
]
report_lines.extend(f"- `{key}`：{value}" for key, value in sorted(status_counts.items()))
report_lines.extend([
    "", "## 审计结论", "",
    "所有 `collected` 项均具有官方 URL、抓取时间、本地原始文件、文件大小和 SHA-256；其余单元保留真实未完成状态。", "",
])
REPORT.write_text("\n".join(report_lines), encoding="utf-8")
print(json.dumps({
    "school_id": SCHOOL_ID, "pages_visited": pages, "sources": len(sources),
    "assets": len(assets), "attempts": len(attempts), "failures": len(failures),
    "privacy_exclusions": len(privacy_exclusions), "coverage": status_counts,
}, ensure_ascii=False, indent=2))
