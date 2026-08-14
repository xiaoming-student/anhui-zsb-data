#!/usr/bin/env python3
"""Prove the project can rebuild from inputs in a clean temporary directory."""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from common import BASE_DIR, REPORTS_DIR, load_json, sha256_file


def canonical_paths(root: Path) -> list[Path]:
    manifest = load_json(root / "schema" / "canonical_tables.json")
    names = manifest["canonical_tables"] + manifest.get("compatibility_exports", [])
    return [root / "normalized" / name for name in names] + [root / "raw_manifest.csv"]


def hashes_for(root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): sha256_file(path)
        for path in sorted(canonical_paths(root))
    }


def main() -> int:
    source_hashes = hashes_for(BASE_DIR)
    with tempfile.TemporaryDirectory(prefix="anhui_zsb_clean_rebuild_") as temp_name:
        target = Path(temp_name) / "anhui_zsb_data"
        target.mkdir(parents=True)
        for directory in ("raw", "staging", "config", "schema", "scripts"):
            shutil.copytree(BASE_DIR / directory, target / directory)
        for filename in ("run_pipeline.py", "normalize.py", "extract.py"):
            shutil.copy2(BASE_DIR / filename, target / filename)

        process = subprocess.run(
            [sys.executable, "run_pipeline.py"],
            cwd=target,
            check=False,
            capture_output=True,
            text=True,
        )
        if process.returncode != 0:
            report = {
                "ok": False,
                "returncode": process.returncode,
                "stdout": process.stdout,
                "stderr": process.stderr,
            }
            (REPORTS_DIR / "clean_rebuild_report.json").write_text(
                json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
            )
            print(process.stdout)
            print(process.stderr, file=sys.stderr)
            return 1

        rebuilt_hashes = hashes_for(target)
        changed = {
            name: {"current": source_hashes.get(name), "clean_rebuild": rebuilt_hashes.get(name)}
            for name in sorted(set(source_hashes) | set(rebuilt_hashes))
            if source_hashes.get(name) != rebuilt_hashes.get(name)
        }
        ok = not changed
        report = {
            "ok": ok,
            "checked_file_count": len(source_hashes),
            "changed_files": changed,
            "pipeline_stdout": process.stdout,
        }
        REPORTS_DIR.mkdir(parents=True, exist_ok=True)
        (REPORTS_DIR / "clean_rebuild_report.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        lines = [
            "# Pilot 2.3 Clean-room 重建测试",
            "",
            f"- 结果：{'PASS' if ok else 'FAIL'}",
            f"- 对比文件：{len(source_hashes)} 个 canonical/compatibility 文件",
            f"- 内容变化：{len(changed)} 个",
            "",
        ]
        if changed:
            lines.extend(["## 不一致文件", ""] + [f"- `{name}`" for name in changed])
        else:
            lines.append("只复制 raw、staging、config、schema 和代码到空目录后，完整流水线成功重建出字节完全一致的 canonical 数据。")
        (REPORTS_DIR / "clean_rebuild_test_pilot_2_3.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(f"Clean rebuild: {'PASS' if ok else 'FAIL'} ({len(source_hashes)} files)")
        return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
