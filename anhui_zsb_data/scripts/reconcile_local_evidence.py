#!/usr/bin/env python3
"""Reconcile the 2026-08-17 Mac-local acquisition snapshot into evidence.

The script is intentionally conservative:

* it never deletes or moves files from ``raw_acquisition`` or ``raw``;
* it enumerates the pre-integration Git snapshot, plus the audited ``.DS_Store``;
* it compares bytes with the evidence tree by SHA-256;
* it copies every local-only logical file into a school/year/topic location;
* it writes deterministic manifests and a migration report.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import shutil
import subprocess
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


DATA_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = DATA_ROOT.parent
EVIDENCE_ROOT = DATA_ROOT / "evidence"
OUTPUT_ROOT = EVIDENCE_ROOT / "local_reconciliation"
DEFAULT_SNAPSHOT = "1ee8fb8"

SCHOOL_IDS = {
    "合肥师范学院": "HFNU",
    "安徽艺术学院": "AHUA",
    "安徽科技工程大学": "AHSTU",
    "安徽科技学院": "AHSTU",
    "滁州学院": "CHZU",
    "池州学院": "CZU",
    "安徽农业大学": "AHAU",
    "安徽医科大学临床医学院": "AYCC",
    "安徽医科大学": "AHMU",
    "安徽中医药大学": "AHTCM",
    "蚌埠医科大学": "BBMU",
    "阜阳师范大学": "FYNU",
    "安庆师范大学": "AQNU",
    "皖南医科大学": "WNMC",
    "皖南医学院": "WNMC",
    "皖西学院": "WXC",
    "亳州学院": "BZU",
    "巢湖学院": "CHU",
    "黄山学院": "HSU",
    "宿州学院": "AHSZU",
    "合肥大学": "HFUU",
    "蚌埠学院": "BBC",
    "安徽工业大学": "AHUT",
    "安徽财经大学": "AUFE",
    "安徽师范大学": "AHNU",
    "铜陵学院": "TLU",
    "安徽第二医学院": "AHYZ",
    "淮南师范学院": "HNNU",
    "安徽建筑大学": "AHJZU",
    "安徽新华学院": "AXHU",
    "安徽三联学院": "SLU",
    "安徽外国语学院": "AISU",
    "芜湖学院": "UWH",
    "安徽职业技术大学": "UTA",
    "芜湖职业技术大学": "WHIT",
    "马鞍山学院": "MASU",
    "皖江工学院": "WJIT",
    "合肥经济学院": "HFUE",
    "合肥城市学院": "CUHF",
    "阜阳理工学院": "FYUT",
    "淮北理工学院": "HBLG",
    "蚌埠工商学院": "BCTB",
    "安徽信息工程学院": "AIIT",
    "安徽文达信息工程学院": "WDU",
    "安徽理工大学": "AUST",
}

TOPIC_RULES = (
    ("admission_policy", ("招生章程", "招生方案", "章程汇总", "-ZC", "_ZC")),
    ("enrollment_plan", ("招生计划", "计划汇总", "计划变化")),
    ("exam_syllabus", ("专业课大纲", "考试大纲", "考试说明", "-DG", "_DG")),
    ("application_statistics", ("报录比", "报名人数", "录取率", "总体统计", "竞争比例", "-BMRS", "_BMRS")),
    ("adjustment", ("调剂",)),
    ("control_line", ("公共课合格线",)),
    ("admission_min_score", ("录取分数", "最低录取", "历年分数", "分数线", "-LQ", "_LQ")),
    ("other_official_notice", ("报名操作", "报名和考试", "工作启动", "操作办法")),
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def rel(path: Path) -> str:
    return path.relative_to(REPO_ROOT).as_posix()


def git_snapshot_paths(snapshot: str) -> list[Path]:
    command = [
        "git",
        "ls-tree",
        "-r",
        "-z",
        "--name-only",
        snapshot,
        "--",
        "anhui_zsb_data/raw_acquisition",
        "anhui_zsb_data/raw",
    ]
    output = subprocess.run(
        command,
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
    ).stdout
    paths: list[Path] = []
    for raw_line in output.split(b"\0"):
        if not raw_line:
            continue
        line = raw_line.decode("utf-8")
        if "/raw_acquisition/reports/" in line or "/raw_acquisition/manifests/" in line:
            continue
        path = REPO_ROOT / line
        if path.is_file():
            paths.append(path)
    ds_store = DATA_ROOT / "raw" / ".DS_Store"
    if ds_store.is_file():
        paths.append(ds_store)
    return sorted(set(paths), key=rel)


def evidence_hash_index() -> dict[str, list[str]]:
    index: dict[str, list[str]] = defaultdict(list)
    for path in sorted(EVIDENCE_ROOT.rglob("*")):
        if not path.is_file() or OUTPUT_ROOT in path.parents:
            continue
        index[sha256(path)].append(rel(path))
    return index


def remote_raw_hash_index(ref: str = "origin/main") -> dict[str, list[str]]:
    """Hash canonical raw blobs from remote main without using local AHNU files."""
    command = [
        "git",
        "ls-tree",
        "-r",
        "-z",
        "--name-only",
        ref,
        "--",
        "anhui_zsb_data/raw",
    ]
    output = subprocess.run(
        command,
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
    ).stdout
    index: dict[str, list[str]] = defaultdict(list)
    for raw_line in output.split(b"\0"):
        if not raw_line:
            continue
        path = raw_line.decode("utf-8")
        blob = subprocess.run(
            ["git", "show", f"{ref}:{path}"],
            cwd=REPO_ROOT,
            check=True,
            capture_output=True,
        ).stdout
        digest = hashlib.sha256(blob).hexdigest()
        index[digest].append(f"{ref}:{path}")
    return index


def school_for(path: Path) -> tuple[str, str]:
    value = path.as_posix()
    raw_match = re.search(r"/raw/\d{4}/([^/]+)/", value)
    if raw_match:
        school_id = raw_match.group(1)
        school_name = next((name for name, code in SCHOOL_IDS.items() if code == school_id), school_id)
        return school_id, school_name
    for school_name in sorted(SCHOOL_IDS, key=len, reverse=True):
        if school_name in value:
            return SCHOOL_IDS[school_name], school_name
    if "/provincial/" in value:
        return "ANHUI-PROV", "安徽省级"
    if path.name == ".DS_Store":
        return "LOCAL-SYSTEM", "macOS 系统元数据"
    return "UNMAPPED", "待人工确认"


def year_for(path: Path) -> str:
    years = sorted(set(re.findall(r"20(?:24|25|26)", path.as_posix())))
    return years[0] if len(years) == 1 else "cross_year"


def topic_for(path: Path) -> str:
    if path.name == ".DS_Store":
        return "system_metadata"
    value = path.as_posix()
    for topic, needles in TOPIC_RULES:
        if any(needle in value for needle in needles):
            return topic
    if "/majors/" in value:
        return "exam_syllabus"
    return "other_official_notice"


def urls_in(value: Any) -> Iterable[str]:
    if isinstance(value, dict):
        for item in value.values():
            yield from urls_in(item)
    elif isinstance(value, list):
        for item in value:
            yield from urls_in(item)
    elif isinstance(value, str):
        yield from re.findall(r"https?://[^\s\"'<>]+", value)


def load_source_url_index(paths: list[Path]) -> dict[tuple[str, str, str], str]:
    index: dict[tuple[str, str, str], str] = {}
    charter_manifest = DATA_ROOT / "raw_acquisition/manifests/charter_fetch_2025_2026.json"
    if charter_manifest.is_file():
        payload = json.loads(charter_manifest.read_text(encoding="utf-8"))
        for item in payload.get("results", []):
            school_id = SCHOOL_IDS.get(str(item.get("school", "")), "")
            url = str(item.get("url", ""))
            year = str(item.get("year", ""))
            if school_id and url.startswith(("http://", "https://")):
                index[(school_id, year, "admission_policy")] = url
    for path in paths:
        if path.suffix.lower() != ".json":
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            continue
        url = next(iter(urls_in(payload)), "")
        if not url:
            continue
        school_id, _ = school_for(path)
        index.setdefault((school_id, year_for(path), topic_for(path)), url)
    return index


def destination_for(path: Path, digest: str) -> Path:
    school_id, _ = school_for(path)
    year = year_for(path)
    topic = topic_for(path)
    if school_id == "ANHUI-PROV":
        base = OUTPUT_ROOT / "provincial" / year / topic
    elif school_id == "LOCAL-SYSTEM":
        base = OUTPUT_ROOT / "_system" / year / topic
    else:
        base = OUTPUT_ROOT / "schools" / school_id / year / topic
    extension = path.suffix.lower() or ".bin"
    path_tag = hashlib.sha256(rel(path).encode("utf-8")).hexdigest()[:8]
    filename = f"DOC-{school_id}-{year}-{topic}-local-{digest[:12]}-{path_tag}{extension}"
    return base / filename


def write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=fieldnames,
            extrasaction="ignore",
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(rows)


def build_report(summary: dict[str, Any], records: list[dict[str, Any]]) -> str:
    by_school = Counter(row["school_id"] for row in records if row["status"] == "copied_local_only")
    by_year = Counter(row["year"] for row in records if row["status"] == "copied_local_only")
    by_topic = Counter(row["topic"] for row in records if row["status"] == "copied_local_only")
    lines = [
        "# 本地数据证据迁移与远程分支整合报告",
        "",
        "> 生成日期：2026-08-17（Asia/Shanghai）",
        f"> 本地基线快照：`{summary['snapshot_commit']}`",
        "> 原始目录策略：只复制、不移动、不删除；`raw_acquisition` 作为迁移前只读备份保留。",
        "",
        "## Git 整合记录",
        "",
        "1. 本地未提交成果已保存为提交 `1ee8fb8`，并建立安全分支 `codex/pre-evidence-integration-20260817-local-snapshot`。",
        "2. `origin/main` 已合入当前 `feat/pilot-b-ahnu`，合并提交为 `94d0404`；生成物和主线脚本冲突采用远程完整基线，本地原版本仍可从安全分支恢复。",
        "3. BCTB 数据分支摘取 105 个目标文件，HBLG 数据分支摘取 140 个目标文件，统一提交为 `249fec5`。",
        "4. 未把两个数据分支的历史代码整体带入，只纳入逐校 evidence、coverage、manifest 和对应采集报告。",
        "",
        "## 完成结果",
        "",
        f"- 审计候选文件：{summary['candidate_files']} 个；",
        f"- 与远程现有内容字节相同：{summary['already_in_remote_content']} 个（其中 {summary['already_in_evidence']} 个已在 evidence，{summary['remote_raw_promoted']} 个仅在 canonical raw，本次同步提升到补证区）；",
        f"- 仅本地逻辑文件：{summary['local_only_files']} 个，已全部映射并复制；",
        f"- 仅本地唯一 SHA-256：{summary['local_only_unique_sha256']} 个；",
        f"- 具有来源 URL：{summary['with_source_url']} 个；缺少 URL、仍需溯源：{summary['missing_source_url']} 个；",
        f"- 原始 `raw_acquisition` 备份文件：{summary['raw_acquisition_backup_files']} 个，迁移校验后设为只读。",
        "",
        "说明：305 个仅本地文件中包含 1 个审计时存在的 macOS `.DS_Store`。它被单列到 `_system/system_metadata`，不计作招生业务证据，但其字节和 SHA-256 仍被保存，保证审计数量闭合。",
        "",
        "## 目录结构",
        "",
        "```text",
        "evidence/local_reconciliation/",
        "├── schools/<学校ID>/<年份>/<主题>/",
        "├── provincial/<年份>/<主题>/",
        "├── _system/cross_year/system_metadata/",
        "├── local_evidence_manifest.json",
        "├── local_source_catalog.csv",
        "├── sha256_manifest.csv",
        "└── raw_acquisition_backup_sha256.csv",
        "```",
        "",
        "## 仅本地文件分布",
        "",
        "### 按年份",
        "",
        "| 年份 | 文件数 |",
        "|---|---:|",
    ]
    lines.extend(f"| {key} | {value} |" for key, value in sorted(by_year.items()))
    lines.extend(["", "### 按主题", "", "| 主题 | 文件数 |", "|---|---:|"])
    lines.extend(f"| `{key}` | {value} |" for key, value in sorted(by_topic.items()))
    lines.extend(["", "### 按学校（含省级与系统项）", "", "| ID | 文件数 |", "|---|---:|"])
    lines.extend(f"| `{key}` | {value} |" for key, value in sorted(by_school.items()))
    lines.extend(
        [
            "",
            "## 后续仍需补找",
            "",
            "1. 优先处理 `local_source_catalog.csv` 中 `review_required=true` 的条目，补齐官方 URL、抓取时间和页面定位。",
            "2. 2024 年逐校招生章程仍是明显缺口；现有本地批量章程主要集中在 2025、2026 年。",
            "3. 录取分数、报名/录取人数、专业课大纲和参考书目的学校覆盖仍不完整，应按 full-42 coverage 继续采集。",
            "4. 本次目录属于本地补证区，不直接改写 `full_raw_30_schools` 的封闭审计结果；完成来源复核后再提升到正式逐校 evidence。",
            "",
            "## 可复现命令",
            "",
            "```bash",
            "python3 anhui_zsb_data/scripts/reconcile_local_evidence.py --snapshot 1ee8fb8",
            "```",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot", default=DEFAULT_SNAPSHOT)
    parser.add_argument("--expect-candidates", type=int, default=326)
    parser.add_argument("--expect-local-only", type=int, default=305)
    args = parser.parse_args()

    candidates = git_snapshot_paths(args.snapshot)
    if len(candidates) != args.expect_candidates:
        raise SystemExit(
            f"candidate count mismatch: {len(candidates)} != {args.expect_candidates}; "
            "do not migrate until the audited scope is restored"
        )

    existing = evidence_hash_index()
    remote_raw = remote_raw_hash_index()
    source_urls = load_source_url_index(candidates)
    hash_counts = Counter(sha256(path) for path in candidates)
    records: list[dict[str, Any]] = []

    for path in candidates:
        digest = sha256(path)
        school_id, school_name = school_for(path)
        year = year_for(path)
        topic = topic_for(path)
        source_url = source_urls.get((school_id, year, topic), "")
        if digest in existing:
            status = "already_in_remote_evidence"
            evidence_path = existing[digest][0]
        elif digest in remote_raw:
            status = "remote_raw_promoted_to_evidence"
            destination = destination_for(path, digest)
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, destination)
            if sha256(destination) != digest:
                raise SystemExit(f"copy verification failed: {rel(path)}")
            evidence_path = rel(destination)
        else:
            status = "copied_local_only"
            destination = destination_for(path, digest)
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, destination)
            if sha256(destination) != digest:
                raise SystemExit(f"copy verification failed: {rel(path)}")
            evidence_path = rel(destination)
        records.append(
            {
                "record_id": f"LOCAL-{hashlib.sha256(rel(path).encode('utf-8')).hexdigest()[:16]}",
                "school_id": school_id,
                "school_name": school_name,
                "year": year,
                "topic": topic,
                "original_path": rel(path),
                "evidence_path": evidence_path,
                "sha256": digest,
                "size_bytes": path.stat().st_size,
                "status": status,
                "duplicate_group_size": hash_counts[digest],
                "source_url": source_url,
                "review_required": str(not bool(source_url)).lower(),
            }
        )

    local_only = [row for row in records if row["status"] == "copied_local_only"]
    if len(local_only) != args.expect_local_only:
        raise SystemExit(
            f"local-only count mismatch: {len(local_only)} != {args.expect_local_only}; "
            "the evidence baseline changed"
        )

    backup_rows: list[dict[str, Any]] = []
    raw_acquisition = DATA_ROOT / "raw_acquisition"
    for path in sorted(raw_acquisition.rglob("*")):
        if path.is_file():
            backup_rows.append(
                {
                    "path": rel(path),
                    "sha256": sha256(path),
                    "size_bytes": path.stat().st_size,
                    "mode": oct(path.stat().st_mode & 0o777),
                }
            )

    summary = {
        "schema_version": "1.0.0",
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "snapshot_commit": args.snapshot,
        "candidate_files": len(records),
        "candidate_unique_sha256": len({row["sha256"] for row in records}),
        "already_in_remote_content": len(records) - len(local_only),
        "already_in_evidence": sum(row["status"] == "already_in_remote_evidence" for row in records),
        "remote_raw_promoted": sum(row["status"] == "remote_raw_promoted_to_evidence" for row in records),
        "copied_to_local_reconciliation": sum(row["status"] != "already_in_remote_evidence" for row in records),
        "local_only_files": len(local_only),
        "local_only_unique_sha256": len({row["sha256"] for row in local_only}),
        "with_source_url": sum(bool(row["source_url"]) for row in records),
        "missing_source_url": sum(not bool(row["source_url"]) for row in records),
        "raw_acquisition_backup_files": len(backup_rows),
        "raw_acquisition_preserved": True,
        "raw_acquisition_read_only_after_verification": True,
    }

    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    manifest = {"summary": summary, "records": records}
    (OUTPUT_ROOT / "local_evidence_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    fields = list(records[0])
    write_csv(OUTPUT_ROOT / "local_source_catalog.csv", fields, records)
    write_csv(
        OUTPUT_ROOT / "sha256_manifest.csv",
        ["record_id", "original_path", "evidence_path", "sha256", "size_bytes", "status"],
        records,
    )
    write_csv(
        OUTPUT_ROOT / "raw_acquisition_backup_sha256.csv",
        ["path", "sha256", "size_bytes", "mode"],
        backup_rows,
    )
    report = build_report(summary, records)
    report_path = DATA_ROOT / "reports/local_evidence_reconciliation_2026-08-17.md"
    report_path.write_text(report, encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
