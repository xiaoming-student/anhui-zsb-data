#!/usr/bin/env python3
"""Run the builder twice and prove canonical CSV outputs are byte-identical."""

from __future__ import annotations

import json
from pathlib import Path

from build_database import build_database
from build_normalized import CanonicalBuilder
from common import BASE_DIR, NORMALIZED_DIR, REPORTS_DIR, canonical_file_hashes, load_json
from validate import Validator


def canonical_paths() -> list[Path]:
    manifest = load_json(BASE_DIR / "schema" / "canonical_tables.json")
    names = manifest["canonical_tables"] + manifest.get("compatibility_exports", [])
    paths = [NORMALIZED_DIR / name for name in names]
    paths.append(BASE_DIR / "raw_manifest.csv")
    return paths


def main() -> int:
    CanonicalBuilder().build()
    first = canonical_file_hashes(canonical_paths())
    first_validation = Validator(strict_state=False).run()
    if not first_validation.ok:
        raise SystemExit("First build failed validation")

    CanonicalBuilder().build()
    second = canonical_file_hashes(canonical_paths())
    second_validation = Validator(strict_state=False).run()
    if not second_validation.ok:
        raise SystemExit("Second build failed validation")

    changed = {name: {"first": first[name], "second": second[name]} for name in first if first[name] != second[name]}
    ok = not changed
    build_database()
    report = {
        "ok": ok,
        "checked_file_count": len(first),
        "changed_files": changed,
        "hashes": second,
    }
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    (REPORTS_DIR / "idempotence_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    md = [
        "# Pilot 2.3 幂等性测试",
        "",
        f"- 结果：{'PASS' if ok else 'FAIL'}",
        f"- 检查文件：{len(first)} 个 canonical/compatibility 文件",
        f"- 发生变化：{len(changed)} 个",
        "",
    ]
    if changed:
        md.extend(["## 变化文件", ""] + [f"- `{name}`" for name in changed])
    else:
        md.append("在 staging/raw 未变化的情况下，连续两次重建产生了完全相同的 canonical 文件字节。")
    (REPORTS_DIR / "idempotence_test_pilot_2_3.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print(f"Idempotence: {'PASS' if ok else 'FAIL'} ({len(first)} files)")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
