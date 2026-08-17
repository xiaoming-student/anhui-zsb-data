from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from stage1_evidence_guard import (  # noqa: E402
    audit_inventory_closure,
    clean_managed_evidence,
)


def minimal_inventory() -> dict:
    source_id = "SRC-HFNU-2024-ZC"
    return {
        "schema_version": "stage1-evidence-v2",
        "sources": [{"source_id": source_id}],
        "assets": [
            {
                "asset_id": "ASSET-HFNU-2024-ZC-HTML",
                "source_id": source_id,
                "asset_type": "html_snapshot",
                "local_path": "evidence/pilot_a/HFNU/2024/page.html",
                "privacy_classification": "aggregate_or_policy",
                "required": True,
                "parent_asset_id": "",
            },
            {
                "asset_id": "ASSET-HFNU-2024-ZC-HTML-TXT",
                "source_id": source_id,
                "asset_type": "parsed_text",
                "local_path": "evidence/pilot_a/HFNU/2024/page_parsed.txt",
                "privacy_classification": "aggregate_or_policy",
                "required": False,
                "parent_asset_id": "ASSET-HFNU-2024-ZC-HTML",
            },
        ],
    }


def write_declared_files(root: Path, inventory: dict) -> None:
    for asset in inventory["assets"]:
        path = root / asset["local_path"]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("fixture\n", encoding="utf-8")


class Stage1EvidenceGuardTestCase(unittest.TestCase):
    def test_exact_inventory_tree_passes(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            inventory = minimal_inventory()
            write_declared_files(root, inventory)
            self.assertEqual(audit_inventory_closure(inventory, root=root), [])

    def test_untracked_file_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            inventory = minimal_inventory()
            write_declared_files(root, inventory)
            extra = root / "evidence/pilot_a/HFNU/2024/untracked.txt"
            extra.write_text("not inventoried\n", encoding="utf-8")
            errors = audit_inventory_closure(inventory, root=root)
            self.assertTrue(
                any("untracked file exists" in error for error in errors),
                errors,
            )

    def test_source_requires_exactly_one_html_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            inventory = minimal_inventory()
            duplicate = {
                "asset_id": "ASSET-HFNU-2024-ZC-HTML-2",
                "source_id": "SRC-HFNU-2024-ZC",
                "asset_type": "html_snapshot",
                "local_path": "evidence/pilot_a/HFNU/2024/page-2.html",
                "privacy_classification": "aggregate_or_policy",
                "required": False,
                "parent_asset_id": "",
            }
            inventory["assets"].append(duplicate)
            write_declared_files(root, inventory)
            errors = audit_inventory_closure(inventory, root=root)
            self.assertTrue(
                any("exactly one HTML snapshot" in error for error in errors),
                errors,
            )

    def test_blank_form_must_be_optional_child_of_source_html(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            inventory = minimal_inventory()
            inventory["assets"].append(
                {
                    "asset_id": "ASSET-HFNU-2024-ZC-FORM",
                    "source_id": "SRC-HFNU-2024-ZC",
                    "asset_type": "docx",
                    "local_path": "evidence/pilot_a/HFNU/2024/form.docx",
                    "privacy_classification": "blank_official_form",
                    "required": True,
                    "parent_asset_id": "",
                }
            )
            write_declared_files(root, inventory)
            errors = audit_inventory_closure(inventory, root=root)
            self.assertTrue(
                any("blank official form must not be required" in error for error in errors),
                errors,
            )
            self.assertTrue(
                any("no valid parent HTML" in error for error in errors),
                errors,
            )

    def test_clean_removes_only_inventory_managed_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            inventory = minimal_inventory()
            write_declared_files(root, inventory)
            extra = root / "evidence/pilot_a/HFNU/2024/untracked.txt"
            extra.write_text("preserve me\n", encoding="utf-8")

            removed = clean_managed_evidence(inventory["assets"], root=root)

            self.assertEqual(removed, 2)
            self.assertFalse(
                (root / "evidence/pilot_a/HFNU/2024/page.html").exists()
            )
            self.assertFalse(
                (root / "evidence/pilot_a/HFNU/2024/page_parsed.txt").exists()
            )
            self.assertTrue(extra.is_file())


if __name__ == "__main__":
    unittest.main(verbosity=2)
