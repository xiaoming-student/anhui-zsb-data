#!/usr/bin/env python3
"""Run the complete local quality gate and write a reproducible test report."""
from __future__ import annotations

import json
import os
import platform
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
REPORTS = ROOT / "reports"


def run_step(name: str, command: list[str], *, extra_env: dict[str, str] | None = None) -> dict[str, Any]:
    env = os.environ.copy()
    if extra_env:
        env.update(extra_env)
    started = time.perf_counter()
    process = subprocess.run(
        command,
        cwd=ROOT,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )
    duration = round(time.perf_counter() - started, 3)
    return {
        "name": name,
        "command": command,
        "returncode": process.returncode,
        "ok": process.returncode == 0,
        "duration_seconds": duration,
        "stdout": process.stdout,
        "stderr": process.stderr,
    }


def main() -> int:
    pythonpath = str(ROOT / "scripts")
    steps = [
        ("Python 语法编译", [sys.executable, "-m", "compileall", "-q", "run_pipeline.py", "normalize.py", "extract.py", "scripts", "tests"], None),
        ("Staging 只读验证", [sys.executable, "extract.py"], None),
        ("完整 canonical 流水线", [sys.executable, "run_pipeline.py"], None),
        ("单元与集成测试", [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"], None),
        ("连续重建幂等测试", [sys.executable, "scripts/check_idempotence.py"], {"PYTHONPATH": pythonpath}),
        ("Clean-room 完整重建测试", [sys.executable, "scripts/check_clean_rebuild.py"], {"PYTHONPATH": pythonpath}),
    ]

    results = [run_step(name, command, extra_env=env) for name, command, env in steps]
    ok = all(item["ok"] for item in results)
    generated_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    payload = {
        "ok": ok,
        "generated_at": generated_at,
        "python_version": platform.python_version(),
        "platform": platform.platform(),
        "steps": results,
    }
    REPORTS.mkdir(parents=True, exist_ok=True)
    (REPORTS / "quality_gate_report.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    lines = [
        "# 安徽专升本数据系统质量门禁报告",
        "",
        f"> 生成时间：{generated_at}",
        f"> Python：{platform.python_version()}",
        f"> 平台：{platform.platform()}",
        "",
        f"## 总结：{'PASS' if ok else 'FAIL'}",
        "",
        "| 检查项 | 结果 | 耗时 |",
        "|---|---:|---:|",
    ]
    for item in results:
        lines.append(
            f"| {item['name']} | {'PASS' if item['ok'] else 'FAIL'} | {item['duration_seconds']:.3f}s |"
        )
    lines.extend(["", "## 执行详情", ""])
    for item in results:
        lines.extend(
            [
                f"### {item['name']} — {'PASS' if item['ok'] else 'FAIL'}",
                "",
                "```text",
                "$ " + " ".join(item["command"]),
                item["stdout"].rstrip(),
            ]
        )
        if item["stderr"].strip():
            lines.extend(["", "[stderr]", item["stderr"].rstrip()])
        lines.extend(["```", ""])

    (REPORTS / "quality_gate_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    for item in results:
        print(f"[{'PASS' if item['ok'] else 'FAIL'}] {item['name']} ({item['duration_seconds']:.3f}s)")
    print(f"Quality gate: {'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
