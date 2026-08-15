#!/usr/bin/env python3
"""Collect the audited Stage 1 official evidence into ``evidence/`` only.

The inventory is the immutable contract. A successful refresh must reproduce the
same bytes, size, SHA-256 and final URL that were reviewed in Gate 0. The
collector never writes to or deletes from canonical ``raw/``.
"""
from __future__ import annotations

import argparse
import hashlib
import http.cookiejar
import json
import re
import shutil
import ssl
import subprocess
import tempfile
import time
import zipfile
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import HTTPCookieProcessor, HTTPSHandler, Request, build_opener

ROOT = Path(__file__).resolve().parent.parent
INVENTORY_PATH = ROOT / "config" / "phase1_evidence_inventory.json"
USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "Chrome/127 Safari/537.36 anhui-zsb-stage1-archiver/2.0"
)
RETRYABLE_HTTP_STATUS = {408, 425, 429, 500, 502, 503, 504}
MAX_DOWNLOAD_BYTES = 100 * 1024 * 1024


class CollectionError(RuntimeError):
    """Raised when official evidence cannot be reproduced exactly."""


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load_inventory() -> dict:
    if not INVENTORY_PATH.is_file():
        raise CollectionError(f"missing inventory: {INVENTORY_PATH.relative_to(ROOT)}")
    inventory = json.loads(INVENTORY_PATH.read_text(encoding="utf-8"))
    if inventory.get("schema_version") != "stage1-evidence-v2":
        raise CollectionError("unsupported Stage 1 evidence inventory version")
    return inventory


def safe_evidence_path(relative: str) -> Path:
    path = Path(relative)
    if path.is_absolute() or ".." in path.parts:
        raise CollectionError(f"unsafe evidence path: {relative}")
    if not relative.startswith("evidence/") or relative.startswith("evidence/../"):
        raise CollectionError(f"collector may only write inside evidence/: {relative}")
    resolved = (ROOT / path).resolve()
    evidence_root = (ROOT / "evidence").resolve()
    if resolved != evidence_root and evidence_root not in resolved.parents:
        raise CollectionError(f"path escapes evidence/: {relative}")
    raw_root = (ROOT / "raw").resolve()
    if resolved == raw_root or raw_root in resolved.parents:
        raise CollectionError(f"collector must not write canonical raw/: {relative}")
    return resolved


def host_allowed(inventory: dict, school_id: str, url: str, method: str) -> bool:
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.hostname:
        return False
    host = parsed.hostname.lower()
    official = {
        str(item).lower()
        for item in inventory.get("allowed_domains", {}).get(school_id, [])
    }
    if host in official:
        return True
    archives = {
        str(item).lower()
        for item in inventory.get("allowed_domains", {}).get("archive_fallback", [])
    }
    return method == "web_archive_official_bytes" and host in archives


def make_opener():
    context = ssl.create_default_context()
    return build_opener(
        HTTPCookieProcessor(http.cookiejar.CookieJar()),
        HTTPSHandler(context=context),
    )


def fetch(opener, url: str, referer: str = "", attempts: int = 3):
    last_error = None
    for attempt in range(1, attempts + 1):
        headers = {
            "User-Agent": USER_AGENT,
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.5",
            "Cache-Control": "no-cache",
        }
        if referer:
            headers["Referer"] = referer
        try:
            with opener.open(Request(url, headers=headers), timeout=45) as response:
                data = response.read(MAX_DOWNLOAD_BYTES + 1)
                if len(data) > MAX_DOWNLOAD_BYTES:
                    raise CollectionError(f"response exceeds {MAX_DOWNLOAD_BYTES} bytes")
                return data, response.geturl(), getattr(response, "status", 200)
        except HTTPError as exc:
            last_error = exc
            if exc.code not in RETRYABLE_HTTP_STATUS or attempt == attempts:
                raise
        except (URLError, TimeoutError, OSError) as exc:
            last_error = exc
            if attempt == attempts:
                raise
        time.sleep(min(2 ** (attempt - 1), 5))
    raise CollectionError(f"fetch failed: {url}: {last_error}")


def asset_dependencies(assets: list[dict]) -> list[dict]:
    by_id = {item["asset_id"]: item for item in assets}
    ordered: list[dict] = []
    visited: set[str] = set()
    visiting: set[str] = set()

    def visit(asset: dict) -> None:
        asset_id = asset["asset_id"]
        if asset_id in visited:
            return
        if asset_id in visiting:
            raise CollectionError(f"asset dependency cycle: {asset_id}")
        visiting.add(asset_id)
        parent = asset.get("parent_asset_id") or ""
        if parent:
            if parent not in by_id:
                raise CollectionError(f"unknown parent asset: {asset_id} -> {parent}")
            visit(by_id[parent])
        visiting.remove(asset_id)
        visited.add(asset_id)
        ordered.append(asset)

    for item in assets:
        visit(item)
    return ordered


def validate_inventory(inventory: dict) -> None:
    sources = inventory.get("sources")
    assets = inventory.get("assets")
    if not isinstance(sources, list) or not sources:
        raise CollectionError("sources must be a non-empty list")
    if not isinstance(assets, list) or not assets:
        raise CollectionError("assets must be a non-empty list")

    source_ids = {item.get("source_id") for item in sources}
    if len(source_ids) != len(sources) or None in source_ids or "" in source_ids:
        raise CollectionError("source_id values must be non-empty and unique")
    asset_ids = {item.get("asset_id") for item in assets}
    paths = {item.get("local_path") for item in assets}
    if len(asset_ids) != len(assets) or None in asset_ids or "" in asset_ids:
        raise CollectionError("asset_id values must be non-empty and unique")
    if len(paths) != len(assets) or None in paths or "" in paths:
        raise CollectionError("local_path values must be non-empty and unique")

    for source in sources:
        school_id = source["school_id"]
        if not host_allowed(inventory, school_id, source["document_url"], "official_direct"):
            raise CollectionError(f"invalid official source URL: {source['source_id']}")
    for asset in assets:
        if asset["source_id"] not in source_ids:
            raise CollectionError(f"unknown source_id: {asset['asset_id']}")
        safe_evidence_path(asset["local_path"])
        method = asset.get("retrieval_method", "")
        for key in ("source_url", "retrieval_url"):
            if not host_allowed(inventory, asset["school_id"], asset[key], method):
                raise CollectionError(f"invalid {key}: {asset['asset_id']}")
        expected = asset.get("sha256", "")
        if not re.fullmatch(r"[0-9a-f]{64}", expected):
            raise CollectionError(f"invalid SHA-256: {asset['asset_id']}")
    asset_dependencies(assets)


def verify_payload(asset: dict, data: bytes, final_url: str) -> None:
    if len(data) != int(asset["file_size"]):
        raise CollectionError(
            f"size changed for {asset['asset_id']}: {len(data)} != {asset['file_size']}"
        )
    digest = sha256_bytes(data)
    if digest != asset["sha256"]:
        raise CollectionError(
            f"SHA-256 changed for {asset['asset_id']}: {digest} != {asset['sha256']}"
        )
    expected_final = asset["retrieval_url"]
    if final_url != expected_final:
        raise CollectionError(
            f"final URL changed for {asset['asset_id']}: {final_url} != {expected_final}"
        )


def derive_text(asset: dict, by_id: dict[str, dict], target: Path) -> None:
    parent = by_id[asset["parent_asset_id"]]
    parent_path = safe_evidence_path(parent["local_path"])
    if not parent_path.is_file():
        raise CollectionError(f"parent file missing: {parent_path}")
    parser_name = asset.get("parser_name", "")
    if parser_name == "pdftotext":
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "parsed.txt"
            process = subprocess.run(
                ["pdftotext", "-layout", str(parent_path), str(output)],
                check=False,
                capture_output=True,
            )
            if process.returncode:
                raise CollectionError(
                    process.stderr.decode("utf-8", errors="replace").strip()
                )
            data = output.read_bytes()
    elif parser_name == "stage1-html-text-extractor":
        from html.parser import HTMLParser

        class Parser(HTMLParser):
            def __init__(self) -> None:
                super().__init__(convert_charrefs=True)
                self.skip = 0
                self.text: list[str] = []

            def handle_starttag(self, tag: str, attrs) -> None:
                del attrs
                if tag.lower() in {"script", "style", "noscript", "svg"}:
                    self.skip += 1
                elif tag.lower() in {"br", "p", "div", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6"}:
                    self.text.append("\n")

            def handle_endtag(self, tag: str) -> None:
                if tag.lower() in {"script", "style", "noscript", "svg"} and self.skip:
                    self.skip -= 1
                elif tag.lower() in {"p", "div", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6"}:
                    self.text.append("\n")

            def handle_data(self, value: str) -> None:
                if not self.skip:
                    self.text.append(value)

        raw = parent_path.read_bytes()
        decoded = None
        encodings = ["utf-8-sig", "utf-8", "gb18030", "big5"]
        for encoding in encodings:
            try:
                decoded = raw.decode(encoding)
                break
            except UnicodeDecodeError:
                continue
        if decoded is None:
            decoded = raw.decode("utf-8", errors="replace")
        parser = Parser()
        parser.feed(decoded)
        parser.close()
        lines: list[str] = []
        for raw_line in "".join(parser.text).replace("\r", "\n").splitlines():
            line = " ".join(raw_line.split())
            if line and (not lines or lines[-1] != line):
                lines.append(line)
        data = ("\n".join(lines).strip() + "\n").encode("utf-8")
    else:
        raise CollectionError(f"unsupported parser: {asset['asset_id']}: {parser_name}")

    verify_payload(asset, data, asset["retrieval_url"])
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)


def clean_evidence_namespaces() -> None:
    for relative in ("evidence/pilot_a", "evidence/pilot_b"):
        target = safe_evidence_path(relative)
        if target.exists():
            shutil.rmtree(target)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check-config", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--clean",
        action="store_true",
        help="remove only evidence/pilot_a and evidence/pilot_b before refresh",
    )
    args = parser.parse_args()

    inventory = load_inventory()
    validate_inventory(inventory)
    assets = asset_dependencies(inventory["assets"])
    if args.check_config:
        print(
            "Stage 1 collector configuration: PASS "
            f"({len(inventory['sources'])} sources, {len(assets)} assets)"
        )
        return 0

    if args.clean and not args.dry_run:
        clean_evidence_namespaces()

    opener = make_opener()
    by_id = {item["asset_id"]: item for item in assets}
    for asset in assets:
        destination = safe_evidence_path(asset["local_path"])
        if asset["asset_type"] == "parsed_text":
            if args.dry_run:
                print(f"[DRY-RUN] derive {asset['asset_id']} -> {asset['local_path']}")
                continue
            derive_text(asset, by_id, destination)
            print(f"[PASS] {asset['asset_id']} derived")
            continue

        if args.dry_run:
            print(f"[DRY-RUN] fetch {asset['asset_id']} <- {asset['source_url']}")
            continue
        data, final_url, status = fetch(
            opener,
            asset["source_url"],
            referer=asset.get("document_url", ""),
        )
        if status != int(asset.get("http_status") or 200):
            raise CollectionError(
                f"HTTP status changed for {asset['asset_id']}: {status}"
            )
        verify_payload(asset, data, final_url)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(data)
        print(f"[PASS] {asset['asset_id']} fetched")

    print(f"Stage 1 collection: PASS ({len(assets)} assets)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
