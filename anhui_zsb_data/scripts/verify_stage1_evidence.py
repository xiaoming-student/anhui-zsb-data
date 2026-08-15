#!/usr/bin/env python3
"""Verify the committed Stage 1 evidence package without network access."""
from __future__ import annotations

import hashlib
import io
import json
import re
import zipfile
from collections import defaultdict
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent.parent
INVENTORY_PATH = ROOT / "config" / "phase1_evidence_inventory.json"
SOURCE_ID_RE = re.compile(r"^SRC-(HFNU|AHUA)-(20\d{2})-[A-Z0-9-]+$")
ASSET_ID_RE = re.compile(r"^ASSET-(HFNU|AHUA)-(20\d{2})-[A-Z0-9-]+$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
CHINESE_ID_RE = re.compile(r"(?<!\d)\d{17}[\dXx](?!\d)")
LONG_NUMBER_RE = re.compile(r"(?<!\d)\d{12,16}(?!\d)")
ALLOWED_PRIVACY = {
    "aggregate_or_policy",
    "aggregate_scores_and_query_notice",
    "blank_official_form",
}


class VisibleTextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._skip_depth = 0
        self._text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        del attrs
        tag = tag.lower()
        if tag in {"script", "style", "noscript", "svg"}:
            self._skip_depth += 1
            return
        if tag in {"br", "p", "div", "li", "tr", "td", "th", "h1", "h2", "h3"}:
            self._text.append("\n")

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in {"script", "style", "noscript", "svg"}:
            if self._skip_depth:
                self._skip_depth -= 1
            return
        if tag in {"p", "div", "li", "tr", "td", "th", "h1", "h2", "h3"}:
            self._text.append("\n")

    def handle_data(self, data: str) -> None:
        if not self._skip_depth:
            self._text.append(data)

    def text(self) -> str:
        return "\n".join(
            line for line in (" ".join(raw.split()) for raw in "".join(self._text).splitlines())
            if line
        )


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def decode_text(data: bytes) -> str:
    head = data[:8192].decode("ascii", errors="ignore")
    encodings: list[str] = []
    match = re.search(r"charset\s*=\s*[\"']?\s*([A-Za-z0-9._-]+)", head, re.I)
    if match:
        encodings.append(match.group(1))
    encodings.extend(["utf-8-sig", "utf-8", "gb18030", "big5"])
    seen: set[str] = set()
    for encoding in encodings:
        key = encoding.lower()
        if key in seen:
            continue
        seen.add(key)
        try:
            return data.decode(encoding)
        except (LookupError, UnicodeDecodeError):
            continue
    return data.decode("utf-8", errors="replace")


def visible_text(path: Path, asset_type: str) -> str:
    data = path.read_bytes()
    if asset_type == "html_snapshot":
        parser = VisibleTextParser()
        parser.feed(decode_text(data))
        parser.close()
        return parser.text()
    if asset_type == "parsed_text":
        return decode_text(data)
    if asset_type == "docx":
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                xml = "\n".join(
                    archive.read(name).decode("utf-8", errors="replace")
                    for name in archive.namelist()
                    if name.startswith("word/") and name.endswith(".xml")
                )
            return re.sub(r"<[^>]+>", " ", xml)
        except zipfile.BadZipFile:
            return ""
    return ""


def check_magic(path: Path, asset_type: str) -> str | None:
    data = path.read_bytes()
    if asset_type == "pdf" and not data.startswith(b"%PDF-"):
        return "invalid PDF magic"
    if asset_type == "doc" and not data.startswith(b"\xd0\xcf\x11\xe0"):
        return "invalid OLE DOC magic"
    if asset_type == "docx":
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                if not any(name.startswith("word/") for name in archive.namelist()):
                    return "DOCX container has no word/ entries"
        except zipfile.BadZipFile:
            return "invalid DOCX ZIP container"
    if asset_type == "html_snapshot":
        sample = data[:8192].lower()
        if b"<html" not in sample and b"<!doctype html" not in sample:
            return "invalid HTML snapshot"
    if asset_type == "parsed_text":
        try:
            data.decode("utf-8")
        except UnicodeDecodeError:
            return "parsed text is not UTF-8"
    return None


def host_allowed(
    inventory: dict[str, Any],
    school_id: str,
    url: str,
    retrieval_method: str,
) -> bool:
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
    archive = {
        str(item).lower()
        for item in inventory.get("allowed_domains", {}).get("archive_fallback", [])
    }
    return retrieval_method == "web_archive_official_bytes" and host in archive


def personal_record_error(text: str) -> str | None:
    identity_numbers = set(CHINESE_ID_RE.findall(text))
    if identity_numbers:
        return f"contains {len(identity_numbers)} apparent Chinese identity number(s)"

    headings = sum(
        marker in text
        for marker in ("姓名", "身份证号", "考生号", "准考证号", "联系电话")
    )
    long_numbers = set(LONG_NUMBER_RE.findall(text))
    if headings >= 2 and len(long_numbers) >= 3:
        return (
            "appears to contain a populated personal candidate list "
            f"({headings} personal headings, {len(long_numbers)} long identifiers)"
        )
    return None


def main() -> int:
    errors: list[str] = []
    warnings: list[str] = []
    if not INVENTORY_PATH.is_file():
        print(f"Stage 1 evidence verification: FAIL\n- missing {INVENTORY_PATH.relative_to(ROOT)}")
        return 1

    try:
        inventory = json.loads(INVENTORY_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(f"Stage 1 evidence verification: FAIL\n- invalid inventory JSON: {exc}")
        return 1

    if inventory.get("schema_version") != "stage1-evidence-v2":
        errors.append("inventory schema_version must be stage1-evidence-v2")

    sources = inventory.get("sources")
    assets = inventory.get("assets")
    if not isinstance(sources, list) or not sources:
        errors.append("sources must be a non-empty list")
        sources = []
    if not isinstance(assets, list) or not assets:
        errors.append("assets must be a non-empty list")
        assets = []

    source_by_id: dict[str, dict[str, Any]] = {}
    for source in sources:
        source_id = str(source.get("source_id", ""))
        match = SOURCE_ID_RE.fullmatch(source_id)
        if not match:
            errors.append(f"invalid source_id format: {source_id!r}")
            continue
        if source_id in source_by_id:
            errors.append(f"duplicate source_id: {source_id}")
            continue
        school_from_id, year_from_id = match.groups()
        school_id = str(source.get("school_id", ""))
        year = int(source.get("year", 0) or 0)
        if school_id != school_from_id or year != int(year_from_id):
            errors.append(
                f"source school/year mismatch: {source_id} vs {school_id}/{year}"
            )
        method = "official_direct"
        document_url = str(source.get("document_url", ""))
        if not host_allowed(inventory, school_id, document_url, method):
            errors.append(f"source document URL is not an allowed official HTTPS URL: {source_id}")
        markers = source.get("expected_markers")
        if not isinstance(markers, list) or not markers:
            errors.append(f"source has no expected_markers: {source_id}")
        if source.get("privacy_classification") not in ALLOWED_PRIVACY:
            errors.append(f"invalid source privacy classification: {source_id}")
        source_by_id[source_id] = source

    asset_by_id: dict[str, dict[str, Any]] = {}
    path_owner: dict[str, str] = {}
    sha_groups: dict[str, list[str]] = defaultdict(list)
    source_html: dict[str, tuple[dict[str, Any], Path]] = {}

    for asset in assets:
        asset_id = str(asset.get("asset_id", ""))
        match = ASSET_ID_RE.fullmatch(asset_id)
        if not match:
            errors.append(f"invalid asset_id format: {asset_id!r}")
            continue
        if asset_id in asset_by_id:
            errors.append(f"duplicate asset_id: {asset_id}")
            continue

        school_from_id, year_from_id = match.groups()
        source_id = str(asset.get("source_id", ""))
        source = source_by_id.get(source_id)
        school_id = str(asset.get("school_id", ""))
        year = int(asset.get("year", 0) or 0)
        if source is None:
            errors.append(f"asset references unknown source: {asset_id} -> {source_id}")
        else:
            if school_id != source.get("school_id") or year != int(source.get("year", 0)):
                errors.append(f"asset/source school-year mismatch: {asset_id}")
            if str(asset.get("document_url", "")) != str(source.get("document_url", "")):
                errors.append(f"asset document_url differs from source: {asset_id}")
        if school_id != school_from_id or year != int(year_from_id):
            errors.append(f"asset ID school/year mismatch: {asset_id}")

        relative = str(asset.get("local_path", ""))
        path = Path(relative)
        if path.is_absolute() or ".." in path.parts:
            errors.append(f"unsafe local_path: {asset_id}: {relative}")
        expected_prefix = (
            f"evidence/pilot_a/{school_id}/"
            if school_id == "HFNU"
            else f"evidence/pilot_b/{school_id}/"
        )
        if not relative.startswith(expected_prefix):
            errors.append(
                f"evidence path is outside the school pilot namespace: {asset_id}: {relative}"
            )
        if relative.startswith("raw/") or "/raw/" in relative:
            errors.append(f"inventory must not point to canonical raw/: {asset_id}")
        if relative in path_owner:
            errors.append(
                f"duplicate local_path: {relative} ({path_owner[relative]}, {asset_id})"
            )
        path_owner[relative] = asset_id

        expected_sha = str(asset.get("sha256", ""))
        if not SHA256_RE.fullmatch(expected_sha):
            errors.append(f"invalid SHA-256: {asset_id}")
        else:
            sha_groups[expected_sha].append(asset_id)

        method = str(asset.get("retrieval_method", ""))
        for key in ("source_url", "retrieval_url"):
            url = str(asset.get(key, ""))
            if not host_allowed(inventory, school_id, url, method):
                errors.append(f"{key} is not an allowed URL: {asset_id}: {url}")

        required = bool(asset.get("required"))
        if required and asset.get("status") != "collected":
            errors.append(f"required asset is not collected: {asset_id}")
        local = ROOT / relative
        if not local.is_file():
            errors.append(f"missing evidence file: {asset_id}: {relative}")
        else:
            expected_size = asset.get("file_size")
            if expected_size is None or local.stat().st_size != int(expected_size):
                errors.append(f"file size mismatch: {asset_id}")
            if SHA256_RE.fullmatch(expected_sha) and sha256_file(local) != expected_sha:
                errors.append(f"SHA-256 mismatch: {asset_id}")
            magic_error = check_magic(local, str(asset.get("asset_type", "")))
            if magic_error:
                errors.append(f"{magic_error}: {asset_id}: {relative}")

            asset_type = str(asset.get("asset_type", ""))
            if asset_type in {"html_snapshot", "parsed_text", "docx"}:
                text = visible_text(local, asset_type)
                privacy_error = personal_record_error(text)
                if privacy_error:
                    errors.append(f"{privacy_error}: {asset_id}")
            if asset_type == "html_snapshot":
                source_html[source_id] = (asset, local)

        privacy = str(asset.get("privacy_classification", ""))
        if privacy not in ALLOWED_PRIVACY:
            errors.append(f"invalid asset privacy classification: {asset_id}")
        parent = str(asset.get("parent_asset_id", ""))
        parser_name = str(asset.get("parser_name", ""))
        parser_version = str(asset.get("parser_version", ""))
        generated_at = str(asset.get("generated_at", ""))
        if asset.get("asset_type") == "parsed_text":
            if not parent or not parser_name or not parser_version or not generated_at:
                errors.append(f"parsed text lacks parent/parser metadata: {asset_id}")
        elif parser_name or parser_version or generated_at:
            warnings.append(f"non-derived asset has parser metadata: {asset_id}")

        asset_by_id[asset_id] = asset

    duplicate_groups = {
        digest: ids for digest, ids in sha_groups.items() if len(ids) > 1
    }
    declared_groups = inventory.get("duplicate_sha256_groups", [])
    declared = {
        item.get("sha256"): sorted(item.get("asset_ids", []))
        for item in declared_groups
    }
    for digest, ids in duplicate_groups.items():
        if declared.get(digest) != sorted(ids):
            errors.append(
                f"undeclared or mismatched duplicate SHA-256 group: {digest}: {sorted(ids)}"
            )
    for digest in declared:
        if digest not in duplicate_groups:
            errors.append(f"declared duplicate group is not duplicated: {digest}")

    for asset_id, asset in asset_by_id.items():
        parent = str(asset.get("parent_asset_id", ""))
        if parent:
            parent_asset = asset_by_id.get(parent)
            if parent_asset is None:
                errors.append(f"parent asset does not exist: {asset_id} -> {parent}")
            elif parent_asset.get("source_id") != asset.get("source_id"):
                errors.append(f"parent/source mismatch: {asset_id} -> {parent}")

    for source_id, source in source_by_id.items():
        if bool(source.get("required")) and source_id not in source_html:
            errors.append(f"required source has no HTML snapshot: {source_id}")
            continue
        relation = source_html.get(source_id)
        if not relation:
            continue
        asset, path = relation
        text = visible_text(path, "html_snapshot")
        missing = [str(marker) for marker in source.get("expected_markers", []) if str(marker) not in text]
        if missing:
            errors.append(
                f"HTML does not contain expected topic markers: {asset['asset_id']}: {missing}"
            )

    if errors:
        print("Stage 1 evidence verification: FAIL")
        for error in errors:
            print(f"- {error}")
        if warnings:
            print("Warnings:")
            for warning in warnings:
                print(f"- {warning}")
        return 1

    print(
        "Stage 1 evidence verification: PASS "
        f"({len(asset_by_id)} assets, {len(path_owner)} unique files, "
        f"{len(source_by_id)} sources, {len(duplicate_groups)} duplicate groups)"
    )
    if warnings:
        for warning in warnings:
            print(f"Warning: {warning}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
