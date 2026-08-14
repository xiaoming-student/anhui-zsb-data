#!/usr/bin/env python3
"""Archive official Stage 1 evidence pages and their direct public assets.

The fetcher deliberately stays within the configured official hosts. It does not
follow result-query portals, candidate-list pages, login flows, CAPTCHAs, or
other access controls. Every saved byte stream is hashed and listed in the
generated report.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import mimetypes
import re
import ssl
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from email.message import Message
from html.parser import HTMLParser
from http.cookiejar import CookieJar
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import unquote, urldefrag, urljoin, urlparse
from urllib.request import HTTPCookieProcessor, HTTPSHandler, Request, build_opener

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG = ROOT / "config" / "stage1_sources.json"
REPORT_JSON = ROOT / "reports" / "stage1_evidence_fetch_report.json"
REPORT_MD = ROOT / "reports" / "stage1_evidence_fetch_report.md"

USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36 "
    "anhui-zsb-data-evidence-archiver/1.0"
)
MAX_DOWNLOAD_BYTES = 80 * 1024 * 1024
MAX_ASSETS_PER_SOURCE = 30
RETRYABLE_HTTP_STATUS = {408, 425, 429, 500, 502, 503, 504}

DOCUMENT_EXTENSIONS = {
    ".pdf",
    ".doc",
    ".docx",
    ".xls",
    ".xlsx",
    ".csv",
    ".txt",
    ".zip",
    ".rar",
    ".7z",
}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".tif", ".tiff"}
ALL_ASSET_EXTENSIONS = DOCUMENT_EXTENSIONS | IMAGE_EXTENSIONS
DOCUMENT_CONTENT_TYPES = {
    "application/pdf": ".pdf",
    "application/msword": ".doc",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
    "application/vnd.ms-excel": ".xls",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ".xlsx",
    "text/csv": ".csv",
    "text/plain": ".txt",
    "application/zip": ".zip",
    "application/x-rar-compressed": ".rar",
    "application/x-7z-compressed": ".7z",
}
IMAGE_CONTENT_TYPES = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/gif": ".gif",
    "image/webp": ".webp",
    "image/bmp": ".bmp",
    "image/tiff": ".tif",
}
ACCESS_CONTROL_MARKERS = (
    "请输入验证码下载附件",
    "请输入验证码",
    "验证码错误",
    "访问过于频繁",
    "请先登录",
    "无权访问",
    "access denied",
)
PERSONAL_DATA_MARKERS = (
    "身份证号查询",
    "输入身份证",
    "考生号",
    "拟录取名单公示",
    "录取名单公示",
)
SKIP_ASSET_PATH_MARKERS = (
    "/_upload/tpl/",
    "/images/logo",
    "/images/banner",
    "/images/ewm",
    "/images/qrcode",
    "/favicon",
)
CONTENT_ASSET_PATH_MARKERS = (
    "/__local/",
    "/system/_content/download.jsp",
    "/_upload/article/",
    "/upload/article/",
    "/uploads/article/",
    "/attachment/",
    "/attachments/",
)


@dataclass(frozen=True)
class LinkCandidate:
    url: str
    label: str
    kind: str  # "link" or "image"


@dataclass
class FetchResponse:
    requested_url: str
    final_url: str
    status: int
    headers: Message
    data: bytes

    @property
    def content_type(self) -> str:
        return (self.headers.get_content_type() or "application/octet-stream").lower()


class EvidenceHTMLParser(HTMLParser):
    """Collect readable text plus direct link/image candidates."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.links: list[LinkCandidate] = []
        self._anchor_href: str | None = None
        self._anchor_text: list[str] = []
        self._skip_depth = 0
        self._text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_map = {key.lower(): value or "" for key, value in attrs}
        tag = tag.lower()
        if tag in {"script", "style", "noscript", "svg"}:
            self._skip_depth += 1
            return
        if tag == "a":
            href = attrs_map.get("href", "").strip()
            if href:
                self._anchor_href = href
                self._anchor_text = []
        elif tag == "img":
            src = (attrs_map.get("src") or attrs_map.get("data-src") or "").strip()
            if src:
                label = (
                    attrs_map.get("alt")
                    or attrs_map.get("title")
                    or Path(urlparse(src).path).name
                    or "image"
                ).strip()
                self.links.append(LinkCandidate(src, label, "image"))
        if tag in {"br", "p", "div", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6"}:
            self._text.append("\n")

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in {"script", "style", "noscript", "svg"}:
            if self._skip_depth:
                self._skip_depth -= 1
            return
        if tag == "a" and self._anchor_href:
            label = " ".join("".join(self._anchor_text).split())
            self.links.append(LinkCandidate(self._anchor_href, label or "attachment", "link"))
            self._anchor_href = None
            self._anchor_text = []
        if tag in {"p", "div", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6"}:
            self._text.append("\n")

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return
        self._text.append(data)
        if self._anchor_href:
            self._anchor_text.append(data)

    def readable_text(self) -> str:
        normalized_lines: list[str] = []
        for raw_line in "".join(self._text).replace("\r", "\n").splitlines():
            line = " ".join(raw_line.split())
            if line and (not normalized_lines or normalized_lines[-1] != line):
                normalized_lines.append(line)
        return "\n".join(normalized_lines).strip() + "\n"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def write_bytes_if_changed(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_file() and path.read_bytes() == data:
        return
    path.write_bytes(data)


def write_text_if_changed(path: Path, text: str) -> None:
    write_bytes_if_changed(path, text.encode("utf-8"))


def normalize_host(host: str | None) -> str:
    value = (host or "").lower().split(":", 1)[0]
    return value[4:] if value.startswith("www.") else value


def decode_html(data: bytes, headers: Message) -> tuple[str, str]:
    candidates: list[str] = []
    header_charset = headers.get_content_charset()
    if header_charset:
        candidates.append(header_charset)

    head = data[:8192].decode("ascii", errors="ignore")
    meta_match = re.search(r"charset\s*=\s*[\"']?\s*([A-Za-z0-9._-]+)", head, flags=re.I)
    if meta_match:
        candidates.append(meta_match.group(1))

    candidates.extend(["utf-8-sig", "utf-8", "gb18030", "big5"])
    seen: set[str] = set()
    for encoding in candidates:
        normalized = encoding.lower()
        if normalized in seen:
            continue
        seen.add(normalized)
        try:
            return data.decode(encoding), encoding
        except (LookupError, UnicodeDecodeError):
            continue
    return data.decode("utf-8", errors="replace"), "utf-8-replace"


def make_opener() -> Any:
    cookie_jar = CookieJar()
    context = ssl.create_default_context()
    return build_opener(HTTPCookieProcessor(cookie_jar), HTTPSHandler(context=context))


def fetch(
    opener: Any,
    url: str,
    *,
    referer: str | None = None,
    attempts: int = 3,
) -> FetchResponse:
    last_error: BaseException | None = None
    for attempt in range(1, attempts + 1):
        headers = {
            "User-Agent": USER_AGENT,
            "Accept": (
                "text/html,application/xhtml+xml,application/pdf,"
                "application/msword,application/vnd.openxmlformats-officedocument."
                "wordprocessingml.document,image/avif,image/webp,image/apng,image/*,*/*;q=0.8"
            ),
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.6",
            "Cache-Control": "no-cache",
        }
        if referer:
            headers["Referer"] = referer
        request = Request(url, headers=headers)
        try:
            with opener.open(request, timeout=45) as response:
                data = response.read(MAX_DOWNLOAD_BYTES + 1)
                if len(data) > MAX_DOWNLOAD_BYTES:
                    raise RuntimeError(f"response exceeds {MAX_DOWNLOAD_BYTES} bytes")
                return FetchResponse(
                    requested_url=url,
                    final_url=response.geturl(),
                    status=getattr(response, "status", 200),
                    headers=response.headers,
                    data=data,
                )
        except HTTPError as exc:
            last_error = exc
            if exc.code not in RETRYABLE_HTTP_STATUS or attempt == attempts:
                raise
        except (URLError, TimeoutError, ConnectionError, OSError) as exc:
            last_error = exc
            if attempt == attempts:
                raise
        time.sleep(min(2 ** (attempt - 1), 5))
    raise RuntimeError(f"failed to fetch {url}: {last_error}")


def validate_config(config: dict[str, Any]) -> None:
    if config.get("schema_version") != "1.0":
        raise ValueError("stage1_sources.json schema_version must be 1.0")
    sources = config.get("sources")
    if not isinstance(sources, list) or not sources:
        raise ValueError("sources must be a non-empty list")

    ids: set[str] = set()
    paths: set[str] = set()
    for index, source in enumerate(sources, start=1):
        missing = [
            key
            for key in (
                "source_id",
                "school_id",
                "school_name",
                "year",
                "document_type",
                "title",
                "url",
                "output_path",
            )
            if not source.get(key)
        ]
        if missing:
            raise ValueError(f"source #{index} missing fields: {', '.join(missing)}")
        source_id = str(source["source_id"])
        if source_id in ids:
            raise ValueError(f"duplicate source_id: {source_id}")
        ids.add(source_id)

        parsed = urlparse(str(source["url"]))
        if parsed.scheme != "https" or not parsed.hostname:
            raise ValueError(f"{source_id}: official URL must use https")
        output_path = Path(str(source["output_path"]))
        if output_path.is_absolute() or ".." in output_path.parts:
            raise ValueError(f"{source_id}: unsafe output_path")
        if not output_path.as_posix().startswith("raw/") or output_path.suffix.lower() != ".html":
            raise ValueError(f"{source_id}: output_path must be raw/.../*.html")
        output_key = output_path.as_posix()
        if output_key in paths:
            raise ValueError(f"duplicate output_path: {output_key}")
        paths.add(output_key)

        title_and_url = f"{source['title']} {source['url']}".lower()
        if any(marker.lower() in title_and_url for marker in PERSONAL_DATA_MARKERS):
            raise ValueError(f"{source_id}: candidate-list/query pages are not allowed")


def content_disposition_filename(headers: Message) -> str:
    disposition = headers.get("Content-Disposition", "")
    if not disposition:
        return ""
    utf8_match = re.search(r"filename\*\s*=\s*UTF-8''([^;]+)", disposition, flags=re.I)
    if utf8_match:
        return unquote(utf8_match.group(1)).strip("\"' ")
    plain_match = re.search(r"filename\s*=\s*(?:\"([^\"]+)\"|([^;]+))", disposition, flags=re.I)
    if plain_match:
        return (plain_match.group(1) or plain_match.group(2) or "").strip("\"' ")
    return ""


def infer_extension(response: FetchResponse, label: str) -> str:
    disposition_name = content_disposition_filename(response.headers)
    for value in (disposition_name, label, Path(urlparse(response.final_url).path).name):
        suffix = Path(value).suffix.lower()
        if suffix in ALL_ASSET_EXTENSIONS:
            return ".jpg" if suffix == ".jpeg" else suffix

    content_type = response.content_type.split(";", 1)[0].strip()
    if content_type in DOCUMENT_CONTENT_TYPES:
        return DOCUMENT_CONTENT_TYPES[content_type]
    if content_type in IMAGE_CONTENT_TYPES:
        return IMAGE_CONTENT_TYPES[content_type]

    data = response.data
    if data.startswith(b"%PDF-"):
        return ".pdf"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png"
    if data.startswith(b"\xff\xd8\xff"):
        return ".jpg"
    if data.startswith((b"GIF87a", b"GIF89a")):
        return ".gif"
    if data.startswith(b"PK\x03\x04"):
        # Office Open XML and ZIP share the same signature. Prefer the label.
        lowered = label.lower()
        for suffix in (".docx", ".xlsx", ".zip"):
            if suffix in lowered:
                return suffix
        return ".zip"

    guessed = mimetypes.guess_extension(content_type) or ""
    return guessed.lower()


def looks_access_controlled(text: str) -> bool:
    normalized = text.lower()
    return any(marker.lower() in normalized for marker in ACCESS_CONTROL_MARKERS)


def asset_candidate_allowed(
    candidate: LinkCandidate,
    *,
    page_url: str,
    allowed_hosts: set[str],
) -> tuple[bool, str]:
    raw_url = candidate.url.strip()
    if not raw_url or raw_url.startswith(("javascript:", "mailto:", "tel:", "data:", "#")):
        return False, "unsupported_scheme"
    absolute, _fragment = urldefrag(urljoin(page_url, raw_url))
    parsed = urlparse(absolute)
    if parsed.scheme not in {"http", "https"}:
        return False, "unsupported_scheme"
    if normalize_host(parsed.hostname) not in allowed_hosts:
        return False, "external_host"

    lower_path = parsed.path.lower()
    lower_url = absolute.lower()
    if any(marker in lower_path for marker in SKIP_ASSET_PATH_MARKERS):
        return False, "site_chrome"
    suffix = Path(lower_path).suffix.lower()
    special_content_path = any(marker in lower_path for marker in CONTENT_ASSET_PATH_MARKERS)
    attachment_query = "wbfileid=" in lower_url or "downloadattachurl" in lower_url

    if candidate.kind == "image":
        if suffix in IMAGE_EXTENSIONS and (special_content_path or "/article/" in lower_path):
            return True, absolute
        return False, "non_content_image"

    if suffix in ALL_ASSET_EXTENSIONS or special_content_path or attachment_query:
        return True, absolute
    return False, "not_direct_asset"


def parse_page(html_text: str) -> EvidenceHTMLParser:
    parser = EvidenceHTMLParser()
    parser.feed(html_text)
    parser.close()
    return parser


def file_record(
    path: Path,
    *,
    source_id: str,
    source_url: str,
    final_url: str,
    content_type: str,
    kind: str,
    label: str = "",
) -> dict[str, Any]:
    data = path.read_bytes()
    return {
        "source_id": source_id,
        "kind": kind,
        "label": label,
        "local_path": path.relative_to(ROOT).as_posix(),
        "source_url": source_url,
        "final_url": final_url,
        "content_type": content_type,
        "size_bytes": len(data),
        "sha256": sha256_bytes(data),
    }


def download_source(opener: Any, source: dict[str, Any]) -> dict[str, Any]:
    source_id = str(source["source_id"])
    page_url = str(source["url"])
    output_path = ROOT / str(source["output_path"])
    started = time.perf_counter()
    result: dict[str, Any] = {
        "source_id": source_id,
        "school_id": source["school_id"],
        "school_name": source["school_name"],
        "year": source["year"],
        "document_type": source["document_type"],
        "title": source["title"],
        "url": page_url,
        "covers": source.get("covers", []),
        "required_page": bool(source.get("required_page", True)),
        "page": None,
        "assets": [],
        "blocked_assets": [],
        "skipped_asset_count": 0,
        "errors": [],
        "status": "failed",
    }

    try:
        page_response = fetch(opener, page_url)
    except Exception as exc:  # noqa: BLE001 - report exact network failure
        result["errors"].append(f"page fetch failed: {type(exc).__name__}: {exc}")
        result["duration_seconds"] = round(time.perf_counter() - started, 3)
        return result

    page_text, encoding = decode_html(page_response.data, page_response.headers)
    if looks_access_controlled(page_text):
        result["errors"].append("page response was blocked by access control")
        result["duration_seconds"] = round(time.perf_counter() - started, 3)
        return result

    write_bytes_if_changed(output_path, page_response.data)
    parsed_page = parse_page(page_text)
    parsed_text_path = output_path.with_name(output_path.stem + "_parsed.txt")
    write_text_if_changed(parsed_text_path, parsed_page.readable_text())

    result["page"] = file_record(
        output_path,
        source_id=source_id,
        source_url=page_url,
        final_url=page_response.final_url,
        content_type=page_response.content_type,
        kind="html_snapshot",
    )
    result["page"]["http_status"] = page_response.status
    result["page"]["detected_encoding"] = encoding
    result["parsed_text"] = file_record(
        parsed_text_path,
        source_id=source_id,
        source_url=page_url,
        final_url=page_response.final_url,
        content_type="text/plain; charset=utf-8",
        kind="parsed_text",
    )

    if source.get("discover_assets", False):
        allowed_hosts = {
            normalize_host(urlparse(page_url).hostname),
            *{
                normalize_host(host)
                for host in source.get("allowed_hosts", [])
                if isinstance(host, str) and host
            },
        }
        seen_urls: set[str] = set()
        candidates: list[tuple[LinkCandidate, str]] = []
        for candidate in parsed_page.links:
            allowed, normalized_or_reason = asset_candidate_allowed(
                candidate,
                page_url=page_response.final_url,
                allowed_hosts=allowed_hosts,
            )
            if not allowed:
                result["skipped_asset_count"] += 1
                continue
            absolute = normalized_or_reason
            if absolute in seen_urls:
                continue
            seen_urls.add(absolute)
            candidates.append((candidate, absolute))

        for asset_index, (candidate, asset_url) in enumerate(
            candidates[:MAX_ASSETS_PER_SOURCE],
            start=1,
        ):
            try:
                asset_response = fetch(opener, asset_url, referer=page_response.final_url)
            except Exception as exc:  # noqa: BLE001
                result["blocked_assets"].append(
                    {
                        "url": asset_url,
                        "label": candidate.label,
                        "status": "fetch_error",
                        "error": f"{type(exc).__name__}: {exc}",
                    }
                )
                continue

            asset_text = ""
            if asset_response.content_type.startswith("text/html") or asset_response.data.lstrip().startswith(
                (b"<!DOCTYPE html", b"<html", b"<HTML")
            ):
                asset_text, _asset_encoding = decode_html(asset_response.data, asset_response.headers)
                if looks_access_controlled(asset_text):
                    result["blocked_assets"].append(
                        {
                            "url": asset_url,
                            "final_url": asset_response.final_url,
                            "label": candidate.label,
                            "status": "blocked_by_access_control",
                            "http_status": asset_response.status,
                            "content_type": asset_response.content_type,
                        }
                    )
                    continue

            extension = infer_extension(asset_response, candidate.label)
            if extension not in ALL_ASSET_EXTENSIONS:
                result["blocked_assets"].append(
                    {
                        "url": asset_url,
                        "final_url": asset_response.final_url,
                        "label": candidate.label,
                        "status": "unexpected_content",
                        "http_status": asset_response.status,
                        "content_type": asset_response.content_type,
                    }
                )
                continue

            asset_path = output_path.with_name(
                f"{output_path.stem}-ATT-{asset_index:02d}{extension}"
            )
            write_bytes_if_changed(asset_path, asset_response.data)
            result["assets"].append(
                file_record(
                    asset_path,
                    source_id=source_id,
                    source_url=asset_url,
                    final_url=asset_response.final_url,
                    content_type=asset_response.content_type,
                    kind="document" if extension in DOCUMENT_EXTENSIONS else "image",
                    label=candidate.label,
                )
            )

    expected = source.get("expected_assets", {})
    min_documents = int(expected.get("min_documents", 0) or 0)
    document_count = sum(1 for item in result["assets"] if item["kind"] == "document")
    expected_met = document_count >= min_documents
    result["expected_assets"] = {
        "min_documents": min_documents,
        "document_count": document_count,
        "met": expected_met,
        "preferred_extensions": expected.get("preferred_extensions", []),
    }

    if result["page"] and expected_met:
        result["status"] = "complete"
    elif result["page"]:
        result["status"] = "partial"
    result["duration_seconds"] = round(time.perf_counter() - started, 3)
    return result


def markdown_escape(value: Any) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")


def build_markdown(report: dict[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# 阶段 1 官方证据文件抓取报告",
        "",
        f"> 生成时间：{report['generated_at']}",
        f"> Pilot B：{report['pilot_b_selection']['school_name']}（{report['pilot_b_selection']['school_id']}）",
        "",
        "## 汇总",
        "",
        f"- 配置来源：{summary['source_count']} 个",
        f"- 完整：{summary['complete_count']} 个",
        f"- 部分完成：{summary['partial_count']} 个",
        f"- 失败：{summary['failed_count']} 个",
        f"- HTML 快照：{summary['html_snapshot_count']} 个",
        f"- 解析文本：{summary['parsed_text_count']} 个",
        f"- 附件/内容图片：{summary['asset_count']} 个",
        f"- 受访问控制或内容异常的附件：{summary['blocked_asset_count']} 个",
        f"- 必需页面失败：{summary['fatal_required_page_failures']} 个",
        "",
        "## 来源结果",
        "",
        "| 院校 | 年份 | 来源 | 类型 | 状态 | 附件 | 阻断 | 本地 HTML |",
        "|---|---:|---|---|---:|---:|---:|---|",
    ]
    for item in report["sources"]:
        local_path = item["page"]["local_path"] if item.get("page") else ""
        lines.append(
            "| {school} | {year} | `{source}` | {dtype} | {status} | {assets} | {blocked} | `{path}` |".format(
                school=markdown_escape(item["school_name"]),
                year=item["year"],
                source=item["source_id"],
                dtype=markdown_escape(item["document_type"]),
                status=item["status"].upper(),
                assets=len(item.get("assets", [])),
                blocked=len(item.get("blocked_assets", [])),
                path=local_path,
            )
        )

    blocked_items = [
        (source["source_id"], blocked)
        for source in report["sources"]
        for blocked in source.get("blocked_assets", [])
    ]
    if blocked_items:
        lines.extend(["", "## 未绕过的访问控制与异常附件", ""])
        for source_id, blocked in blocked_items:
            lines.append(
                f"- `{source_id}`：{blocked.get('status')} — "
                f"{blocked.get('label') or blocked.get('url')} "
                f"({blocked.get('url', '')})"
            )

    unresolved = report.get("expected_but_not_found", [])
    if unresolved:
        lines.extend(["", "## 官方检索后仍未找到", ""])
        for item in unresolved:
            lines.append(
                f"- {item['school_id']} {item['year']} {item['document_type']}："
                f"{item['status']}。{item.get('notes', '')}"
            )

    failures = [source for source in report["sources"] if source.get("errors")]
    if failures:
        lines.extend(["", "## 抓取错误", ""])
        for source in failures:
            for error in source["errors"]:
                lines.append(f"- `{source['source_id']}`：{error}")

    lines.extend(
        [
            "",
            "## 边界",
            "",
            "- 本阶段只归档官方证据文件和抓取清单，未写入 staging、normalized、SQLite 或 Schema。",
            "- 未访问需要身份证号、考生号或个人身份验证的录取查询系统。",
            "- 未抓取含姓名、考生号等个人信息的名单型页面。",
            "- 遇到验证码、登录或其他访问控制时仅记录状态，不尝试绕过。",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument(
        "--check-config",
        action="store_true",
        help="validate the source configuration without making network requests",
    )
    args = parser.parse_args()

    config_path = args.config if args.config.is_absolute() else ROOT / args.config
    config = json.loads(config_path.read_text(encoding="utf-8"))
    validate_config(config)
    if args.check_config:
        print(f"Configuration valid: {len(config['sources'])} sources")
        return 0

    opener = make_opener()
    results: list[dict[str, Any]] = []
    for source in config["sources"]:
        result = download_source(opener, source)
        results.append(result)
        print(
            f"[{result['status'].upper()}] {result['source_id']} "
            f"assets={len(result.get('assets', []))} "
            f"blocked={len(result.get('blocked_assets', []))}"
        )

    fatal_required_page_failures = sum(
        1
        for source in results
        if source.get("required_page") and not source.get("page")
    )
    summary = {
        "source_count": len(results),
        "complete_count": sum(1 for item in results if item["status"] == "complete"),
        "partial_count": sum(1 for item in results if item["status"] == "partial"),
        "failed_count": sum(1 for item in results if item["status"] == "failed"),
        "html_snapshot_count": sum(1 for item in results if item.get("page")),
        "parsed_text_count": sum(1 for item in results if item.get("parsed_text")),
        "asset_count": sum(len(item.get("assets", [])) for item in results),
        "blocked_asset_count": sum(len(item.get("blocked_assets", [])) for item in results),
        "fatal_required_page_failures": fatal_required_page_failures,
    }
    report = {
        "schema_version": "1.0",
        "generated_at": utc_now(),
        "config_path": config_path.relative_to(ROOT).as_posix(),
        "scope": config["scope"],
        "pilot_b_selection": config["pilot_b_selection"],
        "summary": summary,
        "sources": results,
        "expected_but_not_found": config.get("expected_but_not_found", []),
    }

    REPORT_JSON.parent.mkdir(parents=True, exist_ok=True)
    write_text_if_changed(
        REPORT_JSON,
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    )
    write_text_if_changed(REPORT_MD, build_markdown(report))

    print(
        "Stage 1 evidence fetch: "
        f"pages={summary['html_snapshot_count']}/{summary['source_count']}, "
        f"assets={summary['asset_count']}, "
        f"blocked={summary['blocked_asset_count']}, "
        f"fatal={fatal_required_page_failures}"
    )
    return 1 if fatal_required_page_failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
