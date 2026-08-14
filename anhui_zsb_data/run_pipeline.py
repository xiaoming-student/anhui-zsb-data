#!/usr/bin/env python3
"""Convenience entry point: run the full canonical pipeline."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "scripts"))
from pipeline import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
