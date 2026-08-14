#!/usr/bin/env python3
"""Verify the committed Stage 1 evidence package without network access."""
from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INVENTORY = ROOT / "config" / "phase1_evidence_inventory.json"
REFERENCE_REPORT = ROOT / "reports" / "hfnu_reference_books_check.json"
REQUIRED_PILOT_B_CATEGORIES = {
    "招生章程",
    "招生计划",
    "专业及培养地点",
    "考试科目",
    "考试大纲",
    "参考教材",
    "报考范围",
    "录取规则",
    "录取分数",
    "调剂信息",
    "报名人数或报录数据",
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def check_magic(path: Path, asset_type: str) -> str | None:
    head = path.read_bytes()[:8]
    if asset_type == "pdf" and not head.startswith(b"%PDF-"):
        return "invalid PDF magic"
    if asset_type == "html_snapshot":
        sample = path.read_bytes()[:4096].lower()
        if b"<html" not in sample and b"<!doctype html" not in sample:
            return "invalid HTML snapshot"
    if asset_type == "docx":
        try:
            with zipfile.ZipFile(path) as archive:
                if not any(name.startswith("word/") for name in archive.namelist()):
                    return "DOCX archive has no word/ entries"
        except zipfile.BadZipFile:
            return "invalid DOCX ZIP container"
    return None


def main() -> int:
    errors: list[str] = []
    if not INVENTORY.is_file():
        print(f"FAIL: missing {INVENTORY.relative_to(ROOT)}")
        return 1

    payload = json.loads(INVENTORY.read_text(encoding="utf-8"))
    assets = payload.get("assets", [])
    seen_ids: set[str] = set()
    seen_paths: set[str] = set()
    pilot_b_coverage: set[str] = set()

    for asset in assets:
        asset_id = str(asset.get("asset_id", ""))
        relative = str(asset.get("local_path", ""))
        status = asset.get("status")
        required = bool(asset.get("required"))

        if not asset_id or asset_id in seen_ids:
            errors.append(f"missing or duplicate asset_id: {asset_id!r}")
        seen_ids.add(asset_id)
        if not relative or relative in seen_paths:
            errors.append(f"missing or duplicate local_path: {relative!r}")
        seen_paths.add(relative)
        if relative.startswith("raw/"):
            errors.append(f"Stage 1 evidence must not be stored in canonical raw/: {relative}")
        if required and status != "collected":
            errors.append(f"required asset not collected: {asset_id}")
        if status != "collected":
            continue

        path = ROOT / relative
        if not path.is_file():
            errors.append(f"missing file: {relative}")
            continue
        expected_size = asset.get("file_size")
        if expected_size is not None and path.stat().st_size != int(expected_size):
            errors.append(f"size mismatch: {relative}")
        expected_sha = str(asset.get("sha256", ""))
        if expected_sha and sha256_file(path) != expected_sha:
            errors.append(f"SHA-256 mismatch: {relative}")
        magic_error = check_magic(path, str(asset.get("asset_type", "")))
        if magic_error:
            errors.append(f"{magic_error}: {relative}")
        if asset.get("school_id") == "AHUA":
            pilot_b_coverage.update(asset.get("categories", []))

    missing_categories = sorted(REQUIRED_PILOT_B_CATEGORIES - pilot_b_coverage)
    if missing_categories:
        errors.append("Pilot B missing categories: " + ", ".join(missing_categories))

    if not REFERENCE_REPORT.is_file():
        errors.append("missing HFNU reference-book verification report")
    else:
        reference = json.loads(REFERENCE_REPORT.read_text(encoding="utf-8"))
        if not reference.get("ok"):
            errors.append("HFNU reference-book verification did not pass")
        verified_years = {item.get("year") for item in reference.get("results", []) if item.get("ok")}
        if verified_years != {2024, 2025, 2026}:
            errors.append(f"HFNU reference-book years incomplete: {sorted(verified_years)}")

    if errors:
        print("Stage 1 evidence verification: FAIL")
        for error in errors:
            print(f"- {error}")
        return 1

    print(
        "Stage 1 evidence verification: PASS "
        f"({len(assets)} assets, {len(seen_paths)} unique files, "
        f"{len(pilot_b_coverage)} Pilot B categories)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
