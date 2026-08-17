#!/usr/bin/env python3
"""Run the complete deterministic Pilot pipeline."""

from __future__ import annotations

import argparse
import json
from build_database import build_database
from build_normalized import CanonicalBuilder
from common import REPORTS_DIR
from generate_report import main as generate_report_main
from validate import Validator, print_result


def run_pipeline(*, strict_state: bool = True) -> int:
    counts = CanonicalBuilder().build()
    core_result = Validator(strict_state=False).run()
    if not core_result.ok:
        print_result(core_result)
        return 1

    build_database()
    generate_report_main()

    final_result = Validator(strict_state=strict_state).run()
    print_result(final_result)
    (REPORTS_DIR / "validation_report.json").write_text(
        json.dumps(final_result.to_dict(), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    if final_result.ok:
        print("\nPipeline complete:")
        for table, count in counts.items():
            print(f"  {table}: {count}")
    return 0 if final_result.ok else 1


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-strict-state", action="store_true")
    args = parser.parse_args()
    return run_pipeline(strict_state=not args.no_strict_state)


if __name__ == "__main__":
    raise SystemExit(main())
