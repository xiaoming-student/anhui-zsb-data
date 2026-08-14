#!/usr/bin/env python3
"""Move fetched Stage 1 evidence out of canonical ``raw/`` before QA.

The current canonical builder intentionally rejects every file under ``raw/``
that is not registered in ``config/source_assets.json``. Stage 1 is an evidence
acquisition task, not a canonical-data promotion task, so fetched bytes are
committed under ``evidence/stage1/raw/`` until their source and asset metadata
are reviewed and registered in a later stage.
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from fetch_stage1_evidence import REPORT_JSON, REPORT_MD, ROOT, write_text_if_changed

ARCHIVE_ROOT = Path("evidence") / "stage1"
README_PATH = ROOT / ARCHIVE_ROOT / "README.md"


def archived_path(relative_path: str) -> str:
    path = Path(relative_path)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError(f"Unsafe evidence path: {relative_path}")
    archive_parts = ARCHIVE_ROOT.parts
    if path.parts[: len(archive_parts)] == archive_parts:
        return path.as_posix()
    if not path.parts or path.parts[0] != "raw":
        raise ValueError(f"Stage 1 evidence must use a raw-relative layout: {relative_path}")
    return (ARCHIVE_ROOT / path).as_posix()


def move_file(relative_path: str) -> tuple[str, bool]:
    target_relative = archived_path(relative_path)
    if target_relative == relative_path:
        return target_relative, False

    source = ROOT / relative_path
    target = ROOT / target_relative
    if not source.is_file():
        if target.is_file():
            return target_relative, False
        raise FileNotFoundError(f"Missing fetched evidence file: {relative_path}")

    target.parent.mkdir(parents=True, exist_ok=True)
    if target.is_file():
        if target.read_bytes() != source.read_bytes():
            raise RuntimeError(f"Archive collision with different content: {target_relative}")
        source.unlink()
    else:
        shutil.move(str(source), str(target))
    return target_relative, True


def iter_file_records(report: dict[str, Any]):
    for source in report.get("sources", []):
        for key in ("page", "parsed_text"):
            record = source.get(key)
            if isinstance(record, dict) and record.get("local_path"):
                yield record
        for record in source.get("assets", []):
            if isinstance(record, dict) and record.get("local_path"):
                yield record


def update_removed_paths(report: dict[str, Any], replacements: dict[str, str]) -> None:
    for group in report.get("filtered_shared_images", []):
        updated: list[str] = []
        for old_path in group.get("removed_paths", []):
            new_path = archived_path(str(old_path))
            replacements[str(old_path)] = new_path
            updated.append(new_path)
        group["removed_paths"] = updated


def remove_empty_directories(root: Path) -> None:
    if not root.exists():
        return
    for directory in sorted(
        (path for path in root.rglob("*") if path.is_dir()),
        key=lambda path: len(path.parts),
        reverse=True,
    ):
        try:
            directory.rmdir()
        except OSError:
            pass


def readme_text(report: dict[str, Any]) -> str:
    generated_at = report.get("generated_at", "unknown")
    return f"""# Stage 1 官方证据收件区

本目录保存阶段 1 已获取、但尚未提升为 canonical 输入的官方证据。

- 抓取批次：`{generated_at}`
- Pilot A：合肥师范学院（HFNU）
- Pilot B：安徽艺术学院（AHUA）
- 原始层级：`evidence/stage1/raw/<year>/<school>/`
- 完整文件清单、URL、字节数和 SHA-256：`../../reports/stage1_evidence_fetch_report.json`

## 为什么不直接放入 canonical `raw/`

项目当前约束要求 `raw/` 下每一个文件都必须先登记到
`config/source_assets.json`，否则质量门禁会拒绝构建。本阶段只负责证据
获取与审计，不提前修改 staging、normalized、SQLite 或 Schema，因此先
进入独立收件区。

下一阶段完成来源复核后，应按以下顺序提升：

1. 为官方页面和附件建立稳定的 source/document/asset 标识；
2. 登记文件大小、MIME、SHA-256、父资产和解析关系；
3. 将通过复核的文件移动至 canonical `raw/`；
4. 更新 staging 与 source locator；
5. 执行完整质量门禁并检查 canonical 差异。

## 隐私边界

本目录不包含需要身份证号、考生号或登录验证才能访问的查询结果，也不
归档含考生姓名、考生号等个人信息的名单型页面。
"""


def main() -> int:
    if not REPORT_JSON.is_file():
        raise SystemExit(f"Missing fetch report: {REPORT_JSON}")

    report: dict[str, Any] = json.loads(REPORT_JSON.read_text(encoding="utf-8"))
    replacements: dict[str, str] = {}
    moved_count = 0

    for record in iter_file_records(report):
        old_path = str(record["local_path"])
        new_path, moved = move_file(old_path)
        record["local_path"] = new_path
        replacements[old_path] = new_path
        moved_count += int(moved)

    update_removed_paths(report, replacements)
    report["archive"] = {
        "root": ARCHIVE_ROOT.as_posix(),
        "canonical_raw_promoted": False,
        "reason": (
            "Stage 1 acquires and audits evidence only; canonical raw promotion "
            "requires source_assets registration and staging review."
        ),
    }

    write_text_if_changed(
        REPORT_JSON,
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    )

    markdown = REPORT_MD.read_text(encoding="utf-8") if REPORT_MD.is_file() else ""
    for old_path, new_path in sorted(replacements.items(), key=lambda item: len(item[0]), reverse=True):
        markdown = markdown.replace(old_path, new_path)
    storage_section = (
        "## 存储位置与提升状态\n\n"
        "- 当前归档根目录：`evidence/stage1/raw/`；\n"
        "- 尚未提升到 canonical `raw/`；\n"
        "- 尚未修改 staging、normalized、SQLite 或 Schema；\n"
        "- 下一阶段需先登记 source/document/asset 元数据，再执行 canonical 提升。\n\n"
    )
    if "## 存储位置与提升状态" not in markdown:
        markdown = markdown.replace("## 边界\n", storage_section + "## 边界\n", 1)
    write_text_if_changed(REPORT_MD, markdown)
    write_text_if_changed(README_PATH, readme_text(report))

    for raw_root in (ROOT / "raw").glob("*"):
        if raw_root.is_dir():
            remove_empty_directories(raw_root)

    print(
        "Stage 1 evidence relocation: "
        f"moved={moved_count}, archive_root={ARCHIVE_ROOT.as_posix()}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
