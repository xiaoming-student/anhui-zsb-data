#!/usr/bin/env python3
"""Shared utilities for the Anhui zhuanshengben data pipeline.

The module intentionally uses only Python's standard library so the project can
run in WorkBuddy, macOS, Windows and Linux without installing dependencies.
"""

from __future__ import annotations

import csv
import hashlib
import json
import re
import unicodedata
import uuid
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

BASE_DIR = Path(__file__).resolve().parent.parent
STAGING_DIR = BASE_DIR / "staging"
NORMALIZED_DIR = BASE_DIR / "normalized"
RAW_DIR = BASE_DIR / "raw"
QA_DIR = BASE_DIR / "qa"
REPORTS_DIR = BASE_DIR / "reports"
PROGRESS_DIR = BASE_DIR / "progress"
SCHEMA_DIR = BASE_DIR / "schema"
CONFIG_DIR = BASE_DIR / "config"
DB_DIR = BASE_DIR / "db"

SCHEMA_VERSION = "0.3.0"
SCHOOL_ID = "HFNU"
YEARS = (2024, 2025, 2026)

# Fixed namespace: changing this value would change every deterministic ID.
ID_NAMESPACE = uuid.UUID("465e77c8-7b65-4f02-88ee-f6f71b9d5d38")

TRACK_CODE_MAP = {
    "文": "liberal",
    "理": "science",
    "艺术": "arts_liberal",
    "艺术(文)": "arts_liberal",
    "艺术（文）": "arts_liberal",
    "体育": "sports_liberal",
    "体育(文)": "sports_liberal",
    "体育（文）": "sports_liberal",
}

PLAN_FIELDS = (
    ("total", "plan_total"),
    ("retired_soldier_culture_exam_exempt", "plan_retired_soldier_culture_exam_exempt"),
    ("retired_soldier_non_exempt", "plan_retired_soldier_non_exempt"),
    ("registered_poor_family", "plan_registered_poor_family"),
)

SCORE_FIELDS = (
    ("normal", "score_normal_raw"),
    ("retired_soldier_culture_exam_exempt", "score_retired_culture_exam_exempt_raw"),
    ("retired_soldier_non_exempt", "score_retired_non_exempt_raw"),
    ("registered_poor_family", "score_registered_poor_family_raw"),
    ("skill_competition", "score_skill_competition_raw"),
)


def ensure_directories() -> None:
    for directory in (
        NORMALIZED_DIR,
        QA_DIR,
        REPORTS_DIR,
        PROGRESS_DIR,
        SCHEMA_DIR,
        DB_DIR,
    ):
        directory.mkdir(parents=True, exist_ok=True)


def normalize_text(value: Any) -> str:
    """Normalize human text without changing its semantic punctuation."""
    if value is None:
        return ""
    text = unicodedata.normalize("NFKC", str(value)).strip()
    return re.sub(r"\s+", " ", text)


def normalize_major_name(value: Any) -> str:
    text = normalize_text(value)
    text = re.sub(r"[（(]\s*师范\s*[）)]", "", text)
    return text.strip()


def normalize_track_raw(value: Any) -> str:
    text = normalize_text(value)
    if text == "艺术":
        return "艺术(文)"
    if text == "体育":
        return "体育(文)"
    return text


def track_code(value: Any) -> str:
    raw = normalize_track_raw(value)
    return TRACK_CODE_MAP.get(raw, "unknown")


def stable_id(prefix: str, *parts: Any) -> str:
    normalized = [normalize_text(part).casefold() for part in parts]
    token = "|".join(normalized)
    return f"{prefix}-{uuid.uuid5(ID_NAMESPACE, token)}"


def stable_major_id(major_name: str) -> str:
    return stable_id("MAJOR", normalize_major_name(major_name))


def stable_subject_id(subject_name: str) -> str:
    return stable_id("SUBJ", normalize_text(subject_name))


def json_compact(value: Any) -> str:
    if value in (None, ""):
        return ""
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return ""
        # Accept already valid JSON, otherwise preserve it as a string.
        try:
            parsed = json.loads(stripped)
        except (json.JSONDecodeError, TypeError):
            return json.dumps(stripped, ensure_ascii=False, separators=(",", ":"))
        return json.dumps(parsed, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def dump_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, fieldnames: Sequence[str], rows: Iterable[Mapping[str, Any]]) -> None:
    """Write deterministic UTF-8 BOM CSV output.

    `extrasaction="raise"` deliberately rejects silent schema drift.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    materialized: list[dict[str, Any]] = []
    for source_row in rows:
        row = dict(source_row)
        for key, value in list(row.items()):
            if isinstance(value, (dict, list, tuple)):
                row[key] = json_compact(value)
            elif value is None:
                row[key] = ""
            elif isinstance(value, bool):
                row[key] = "true" if value else "false"
        materialized.append(row)

    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(fieldnames), extrasaction="raise")
        writer.writeheader()
        writer.writerows(materialized)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def as_decimal_string(value: Any) -> str:
    if value in (None, ""):
        return ""
    try:
        decimal = Decimal(str(value).strip())
    except (InvalidOperation, ValueError):
        raise ValueError(f"Not a numeric value: {value!r}") from None
    normalized = decimal.normalize()
    # Decimal('0E+1') should be written as 0.
    if normalized == normalized.to_integral():
        return str(normalized.quantize(Decimal(1)))
    return format(normalized, "f").rstrip("0").rstrip(".")


_SCORE_RE = re.compile(
    r"^\s*(?P<score>\d+(?:\.\d+)?)"
    r"(?:\s*/\s*(?P<max>\d+(?:\.\d+)?))?"
    r"(?:\s*[（(]\s*(?P<label>[^:：()（）]+)\s*[:：]\s*(?P<detail>\d+(?:\.\d+)?)\s*[）)])?\s*$"
)


def parse_score(raw_value: Any) -> dict[str, str]:
    raw = normalize_text(raw_value)
    if not raw:
        return {
            "score_value_numeric": "",
            "score_max_from_raw": "",
            "threshold_detail_json": "",
        }
    match = _SCORE_RE.match(raw)
    if not match:
        raise ValueError(f"Unsupported score format: {raw!r}")

    detail: dict[str, Any] = {}
    label = normalize_text(match.group("label"))
    detail_score = match.group("detail")
    if label and detail_score:
        label_map = {
            "专业课1": "professional_1",
            "专业课一": "professional_1",
            "职测": "vocational_assessment",
        }
        detail = {
            "tie_break_label_raw": label,
            "tie_break_metric": label_map.get(label, label),
            "tie_break_score": as_decimal_string(detail_score),
        }

    return {
        "score_value_numeric": as_decimal_string(match.group("score")),
        "score_max_from_raw": as_decimal_string(match.group("max")) if match.group("max") else "",
        "threshold_detail_json": json_compact(detail) if detail else "",
    }


def score_semantics(candidate_category: str) -> dict[str, str]:
    if candidate_category in {"normal", "registered_poor_family", "retired_soldier_non_exempt"}:
        return {
            "score_metric": "admission_min_score",
            "score_basis": "four_subject_total",
            "score_max": "600",
            "assessment_name": "",
        }
    if candidate_category == "retired_soldier_culture_exam_exempt":
        return {
            "score_metric": "admission_min_score",
            "score_basis": "vocational_assessment",
            "score_max": "100",
            "assessment_name": "职业适应性或职业技能综合考查",
        }
    if candidate_category == "skill_competition":
        return {
            "score_metric": "interview_score",
            "score_basis": "interview",
            "score_max": "100",
            "assessment_name": "技能大赛面试",
        }
    raise ValueError(f"Unknown candidate category: {candidate_category}")


def extract_joint_institution(remarks: Any) -> str:
    text = normalize_text(remarks)
    match = re.search(r"与(.+?)联合培养", text)
    return match.group(1).strip() if match else ""


def split_top_level_rules(text: str) -> list[str]:
    """Split eligibility categories on Chinese separators outside parentheses."""
    text = normalize_text(text).replace("；", "、")
    parts: list[str] = []
    buffer: list[str] = []
    depth = 0
    for char in text:
        if char in "（(":
            depth += 1
        elif char in "）)" and depth:
            depth -= 1
        if char in "、，," and depth == 0:
            value = "".join(buffer).strip()
            if value:
                parts.append(value)
            buffer = []
        else:
            buffer.append(char)
    value = "".join(buffer).strip()
    if value:
        parts.append(value)
    return parts


def parse_eligibility_item(item: str) -> dict[str, str]:
    item = normalize_text(item)
    match = re.match(r"^(?P<scope>[^（(]+?)(?:[（(](?P<condition>.+)[）)])?$", item)
    if not match:
        return {"scope_name_raw": item, "condition_raw": ""}
    return {
        "scope_name_raw": match.group("scope").strip(),
        "condition_raw": normalize_text(match.group("condition")),
    }


def source_id(year: int | str, document_type: str) -> str:
    code = {"admission_policy": "ZC", "admission_scores": "LQ"}[document_type]
    return f"SRC-HFNU-{year}-{code}"


def source_url_for(year: int | str, document_type: str) -> str:
    catalog = load_json(CONFIG_DIR / "source_catalog.json")
    expected = source_id(year, document_type)
    for document in catalog["documents"]:
        if document["source_document_id"] == expected:
            return document["url"]
    raise KeyError(expected)


def normalized_locator(
    locator: Any,
    *,
    year: int | str,
    document_type: str,
    row_key: str = "",
    section: str = "",
) -> str:
    data: dict[str, Any]
    if isinstance(locator, dict):
        data = dict(locator)
    elif locator:
        try:
            parsed = json.loads(str(locator))
            data = dict(parsed) if isinstance(parsed, dict) else {"value": parsed}
        except json.JSONDecodeError:
            data = {"value": str(locator)}
    else:
        data = {}

    # Normalize legacy locator IDs (DOC-...-PDF was a document/file label,
    # while canonical evidence locators must reference source_assets.asset_id).
    asset_id = normalize_text(data.get("asset_id"))
    if asset_id.startswith("DOC-"):
        data["asset_id"] = "ASSET-" + asset_id[4:]

    # 2024 source is HTML, so a fake PDF page locator must not survive.
    if str(year) == "2024" and document_type in {"admission_policy", "admission_scores"}:
        data.pop("asset_id", None)
        data.pop("page", None)
        data["url"] = source_url_for(year, document_type)
    if section:
        data.setdefault("section", section)
    if row_key:
        data["row_key"] = row_key
    return json_compact(data)


def canonical_file_hashes(paths: Iterable[Path]) -> dict[str, str]:
    return {str(path.relative_to(BASE_DIR)): sha256_file(path) for path in sorted(paths)}
