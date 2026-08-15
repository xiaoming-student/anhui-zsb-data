#!/usr/bin/env python3
"""One-time patcher: invoke the Stage 2A extension after base normalization."""
from __future__ import annotations

import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PIPELINE = ROOT / "run_pipeline.py"
IMPORT_LINE = "from scripts.stage2a_hfnu_extension import apply_stage2a_normalized"
CALL_LINE = "apply_stage2a_normalized()"


def call_name(node: ast.Call) -> str:
    if isinstance(node.func, ast.Name):
        return node.func.id
    if isinstance(node.func, ast.Attribute):
        return node.func.attr
    return ""


def main() -> int:
    text = PIPELINE.read_text(encoding="utf-8")
    if IMPORT_LINE in text and CALL_LINE in text:
        print("Stage 2A pipeline hook already installed.")
        return 0

    tree = ast.parse(text)
    candidates = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and (
            "normal" in call_name(node).lower()
            or call_name(node).lower() in {"build_all", "build_normalized"}
        )
    ]
    if not candidates:
        raise RuntimeError("no normalization call found in run_pipeline.py")
    candidates.sort(
        key=lambda node: (
            0 if "normal" in call_name(node).lower() else 1,
            node.lineno,
        )
    )
    target = candidates[0]
    lines = text.splitlines()
    end_line = target.end_lineno or target.lineno
    indentation = re.match(r"\s*", lines[target.lineno - 1]).group(0)
    lines.insert(end_line, f"{indentation}{CALL_LINE}")

    body = list(tree.body)
    insert_at = 0
    if (
        body
        and isinstance(body[0], ast.Expr)
        and isinstance(getattr(body[0], "value", None), ast.Constant)
        and isinstance(body[0].value.value, str)
    ):
        insert_at = body[0].end_lineno or 1
    while insert_at < len(lines) and (
        lines[insert_at].startswith("from __future__")
        or lines[insert_at].startswith("import ")
        or lines[insert_at].startswith("from ")
        or not lines[insert_at].strip()
    ):
        insert_at += 1
    lines.insert(insert_at, IMPORT_LINE)

    patched = "\n".join(lines) + "\n"
    ast.parse(patched)
    if patched.count(IMPORT_LINE) != 1 or patched.count(CALL_LINE) != 1:
        raise RuntimeError("Stage 2A hook insertion is not unique")
    PIPELINE.write_text(patched, encoding="utf-8")
    print(
        "Stage 2A pipeline hook installed after normalization call "
        f"{call_name(target)} at line {target.lineno}."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
