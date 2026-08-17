#!/usr/bin/env python3
"""Guard the exact Stage 1 evidence tree and metadata relationships.

This module deliberately stays network-free. It supplements the byte/hash
verifier with closed-world checks that are easy to miss when only inventory
entries are iterated:

* every file under the managed pilot namespaces must be declared;
* every declared file must exist and must not be a symlink;
* every source document has exactly one HTML snapshot;
* parsed text and blank official forms have valid parent relationships;
* ``--clean`` callers can remove only inventory-managed files.
"""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parent.parent
INVENTORY_PATH = ROOT / "config" / "phase1_evidence_inventory.json"
MANAGED_NAMESPACES = ("evidence/pilot_a", "evidence/pilot_b")


class EvidenceGuardError(RuntimeError):
    """Raised when a managed evidence path is unsafe or malformed."""


def normalize_relative_path(value: str) -> str:
    path = Path(value)
    if not value or path.is_absolute() or ".." in path.parts:
        raise EvidenceGuardError(f"unsafe relative path: {value!r}")
    return path.as_posix()


def inventory_paths(assets: Iterable[dict[str, Any]]) -> set[str]:
    paths: set[str] = set()
    for asset in assets:
        relative = normalize_relative_path(str(asset.get("local_path", "")))
        if not any(
            relative.startswith(f"{namespace}/")
            for namespace in MANAGED_NAMESPACES
        ):
            raise EvidenceGuardError(
                f"asset is outside managed evidence namespaces: "
                f"{asset.get('asset_id', '<unknown>')}: {relative}"
            )
        if relative in paths:
            raise EvidenceGuardError(f"duplicate inventory path: {relative}")
        paths.add(relative)
    return paths


def actual_managed_files(root: Path) -> set[str]:
    files: set[str] = set()
    for namespace in MANAGED_NAMESPACES:
        base = root / namespace
        if not base.exists():
            continue
        if not base.is_dir():
            files.add(namespace)
            continue
        for path in base.rglob("*"):
            if path.is_file() or path.is_symlink():
                files.add(path.relative_to(root).as_posix())
    return files


def _asset_relationship_errors(
    sources: list[dict[str, Any]],
    assets: list[dict[str, Any]],
) -> list[str]:
    errors: list[str] = []
    source_ids = {str(source.get("source_id", "")) for source in sources}
    asset_by_id = {
        str(asset.get("asset_id", "")): asset
        for asset in assets
        if str(asset.get("asset_id", ""))
    }
    html_by_source: dict[str, list[str]] = defaultdict(list)

    for asset in assets:
        asset_id = str(asset.get("asset_id", ""))
        source_id = str(asset.get("source_id", ""))
        asset_type = str(asset.get("asset_type", ""))
        parent_id = str(asset.get("parent_asset_id", ""))

        if source_id not in source_ids:
            errors.append(f"asset references unknown source: {asset_id} -> {source_id}")
        if asset_type == "html_snapshot":
            html_by_source[source_id].append(asset_id)

        if asset_type == "parsed_text":
            parent = asset_by_id.get(parent_id)
            if parent is None:
                errors.append(f"parsed text has no valid parent: {asset_id} -> {parent_id}")
            else:
                parent_type = str(parent.get("asset_type", ""))
                if parent_type not in {"html_snapshot", "pdf"}:
                    errors.append(
                        f"parsed text parent must be HTML or PDF: "
                        f"{asset_id} -> {parent_id} ({parent_type})"
                    )
                if parent.get("source_id") != source_id:
                    errors.append(
                        f"parsed text parent/source mismatch: {asset_id} -> {parent_id}"
                    )

        if asset.get("privacy_classification") == "blank_official_form":
            parent = asset_by_id.get(parent_id)
            if bool(asset.get("required")):
                errors.append(f"blank official form must not be required: {asset_id}")
            if asset_type not in {"doc", "docx"}:
                errors.append(
                    f"blank official form must be DOC/DOCX: {asset_id} ({asset_type})"
                )
            if parent is None:
                errors.append(
                    f"blank official form has no valid parent HTML: "
                    f"{asset_id} -> {parent_id}"
                )
            else:
                if parent.get("asset_type") != "html_snapshot":
                    errors.append(
                        f"blank official form parent must be HTML: "
                        f"{asset_id} -> {parent_id}"
                    )
                if parent.get("source_id") != source_id:
                    errors.append(
                        f"blank official form parent/source mismatch: "
                        f"{asset_id} -> {parent_id}"
                    )

    for source in sources:
        source_id = str(source.get("source_id", ""))
        snapshots = html_by_source.get(source_id, [])
        if len(snapshots) != 1:
            errors.append(
                f"source must have exactly one HTML snapshot: "
                f"{source_id}: {sorted(snapshots)}"
            )
    return errors


def audit_inventory_closure(
    inventory: dict[str, Any],
    *,
    root: Path = ROOT,
) -> list[str]:
    errors: list[str] = []
    sources = inventory.get("sources")
    assets = inventory.get("assets")
    if not isinstance(sources, list) or not isinstance(assets, list):
        return ["inventory sources/assets must both be lists"]

    try:
        expected = inventory_paths(assets)
    except EvidenceGuardError as exc:
        return [str(exc)]

    actual = actual_managed_files(root)
    for relative in sorted(expected - actual):
        errors.append(f"declared evidence file is missing: {relative}")
    for relative in sorted(actual - expected):
        errors.append(f"untracked file exists in managed evidence tree: {relative}")

    for relative in sorted(expected & actual):
        if (root / relative).is_symlink():
            errors.append(f"evidence asset must not be a symlink: {relative}")

    errors.extend(_asset_relationship_errors(sources, assets))
    return errors


def _safe_managed_target(root: Path, relative: str) -> Path:
    normalized = normalize_relative_path(relative)
    if not any(
        normalized.startswith(f"{namespace}/")
        for namespace in MANAGED_NAMESPACES
    ):
        raise EvidenceGuardError(
            f"refusing to clean outside managed evidence namespaces: {normalized}"
        )

    target = root / normalized
    parent = target.parent.resolve()
    evidence_root = (root / "evidence").resolve()
    if parent != evidence_root and evidence_root not in parent.parents:
        raise EvidenceGuardError(f"path parent escapes evidence/: {normalized}")
    return target


def clean_managed_evidence(
    assets: Iterable[dict[str, Any]],
    *,
    root: Path = ROOT,
) -> int:
    """Delete only files explicitly named by the inventory.

    Untracked files are intentionally preserved. The closed-world audit then
    reports them, forcing a reviewer to either inventory or remove them
    explicitly instead of silently deleting potentially important evidence.
    """

    paths = inventory_paths(assets)
    removed = 0
    parent_candidates: set[Path] = set()

    for relative in sorted(paths):
        target = _safe_managed_target(root, relative)
        parent_candidates.add(target.parent)
        if target.is_symlink() or target.is_file():
            target.unlink()
            removed += 1
        elif target.exists():
            raise EvidenceGuardError(
                f"inventory path is not a regular file: {relative}"
            )

    namespace_roots = {(root / namespace).resolve() for namespace in MANAGED_NAMESPACES}
    for directory in sorted(
        parent_candidates,
        key=lambda item: len(item.parts),
        reverse=True,
    ):
        current = directory
        while current.exists() and current.resolve() not in namespace_roots:
            try:
                current.rmdir()
            except OSError:
                break
            current = current.parent

    return removed


def load_inventory(path: Path = INVENTORY_PATH) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != "stage1-evidence-v2":
        raise EvidenceGuardError("unsupported Stage 1 evidence inventory version")
    return payload


def main() -> int:
    try:
        inventory = load_inventory()
        errors = audit_inventory_closure(inventory)
    except (OSError, json.JSONDecodeError, EvidenceGuardError) as exc:
        errors = [str(exc)]

    if errors:
        print("Stage 1 evidence tree guard: FAIL")
        for error in errors:
            print(f"- {error}")
        return 1

    assets = inventory["assets"]
    print(
        "Stage 1 evidence tree guard: PASS "
        f"({len(assets)} declared files, exact tree closure)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
