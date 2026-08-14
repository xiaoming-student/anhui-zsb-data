#!/usr/bin/env python3
"""Compatibility entry point for canonical normalization.

Prefer ``python run_pipeline.py`` for build + QA + report. This command only
rebuilds canonical CSV tables from staging JSON.
"""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "scripts"))
from build_normalized import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
