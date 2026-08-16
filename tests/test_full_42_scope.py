from __future__ import annotations

import csv
import importlib.util
import json
import sys
import unittest
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "audit_full_42_raw_evidence.py"
SPEC = importlib.util.spec_from_file_location("audit_full_42_raw_evidence", MODULE_PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class Full42ScopeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.config = json.loads(
            (ROOT / "anhui_zsb_data" / "config" / "full_42_school_scope.json").read_text(encoding="utf-8")
        )

    def test_scope_shape_and_unique_ids(self) -> None:
        self.assertEqual(self.config["school_count"], 42)
        self.assertEqual(len(self.config["schools"]), 42)
        self.assertEqual(len({item["school_id"] for item in self.config["schools"]}), 42)
        self.assertEqual(self.config["years"], [2024, 2025, 2026])
        self.assertEqual(len(self.config["topics"]), 28)
        self.assertEqual(self.config["coverage_cell_count"], 3528)

    def test_priority_split(self) -> None:
        priorities = Counter(item["priority"] for item in self.config["schools"])
        self.assertEqual(priorities, Counter({"P1": 25, "P0-B": 12, "P0-A": 5}))

    def test_status_vocabulary_matches_task(self) -> None:
        self.assertEqual(set(self.config["status_vocabulary"]), MODULE.VALID_STATUSES)

    def test_wxc_coverage_has_all_84_cells(self) -> None:
        path = ROOT / "anhui_zsb_data" / "evidence" / "full_raw_30_schools" / "WXC" / "school_coverage.csv"
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.DictReader(handle))
        self.assertEqual(len(rows), 84)
        keys = {(int(row["year"]), row["topic"]) for row in rows}
        self.assertEqual(len(keys), 84)
        self.assertTrue({row["status"] for row in rows}.issubset(MODULE.VALID_STATUSES))

    def test_audit_builds_42_school_records(self) -> None:
        audit = MODULE.build_audit(ROOT)
        self.assertEqual(audit["school_count"], 42)
        self.assertEqual(audit["expected_coverage_cells"], 3528)
        wxc = next(item for item in audit["schools"] if item["school_id"] == "WXC")
        self.assertEqual(wxc["coverage_cells"], 84)
        self.assertEqual(wxc["status_counts"].get("access_restricted"), 18)
        self.assertEqual(wxc["status_counts"].get("manual_download_required", 0), 0)


if __name__ == "__main__":
    unittest.main()
