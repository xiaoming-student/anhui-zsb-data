from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "acquire_wxc_p0_raw.py"
SPEC = importlib.util.spec_from_file_location("acquire_wxc_p0_raw", MODULE_PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class WxcCollectorTests(unittest.TestCase):
    def test_official_domain_allowlist(self) -> None:
        self.assertTrue(MODULE.is_official_url("https://zsb.wxc.edu.cn/a.pdf"))
        self.assertTrue(MODULE.is_official_url("https://www.wxc.edu.cn/"))
        self.assertTrue(MODULE.is_official_url("https://www.ahzsks.cn/zyyx/8108.htm"))
        self.assertFalse(MODULE.is_official_url("https://wxc.edu.cn.example.com/a.pdf"))
        self.assertFalse(MODULE.is_official_url("https://example.com/"))

    def test_strict_year_binding(self) -> None:
        self.assertTrue(MODULE.year_bound("2026年普通专升本考试大纲", "https://zsb.wxc.edu.cn/x", 2026))
        self.assertFalse(MODULE.year_bound("2025年普通专升本考试大纲", "https://zsb.wxc.edu.cn/x", 2026))
        self.assertTrue(MODULE.year_bound("附件", "https://zsb.wxc.edu.cn/_upload/a.pdf", 2026, inherited_from_parent=True))

    def test_topic_inference(self) -> None:
        topics = MODULE.infer_topics("2026年专升本招生计划、考试大纲、参考书目和退役士兵调剂通知")
        for topic in ("enrollment_plan", "exam_syllabus", "reference_books", "retired_soldier", "adjustment"):
            self.assertIn(topic, topics)

    def test_public_official_record_is_preserved_and_tagged(self) -> None:
        self.assertTrue(MODULE.contains_public_record_fields("2026年拟录取名单（含考生号）"))
        self.assertFalse(MODULE.contains_public_record_fields("2026年招生章程"))

    def test_seed_candidates_have_official_urls_and_valid_topics(self) -> None:
        for candidate in MODULE.SEED_CANDIDATES:
            self.assertTrue(MODULE.is_official_url(candidate.url))
            self.assertIn(candidate.year, MODULE.YEARS)
            self.assertTrue(set(candidate.topics).issubset(set(MODULE.TOPICS)))

    def test_preaudited_matrix_is_complete(self) -> None:
        self.assertEqual(len(MODULE.PREAUDITED_STATUS), 3 * 28)
        self.assertEqual(MODULE.PREAUDITED_STATUS[(2026, "exam_syllabus")], "access_restricted")
        self.assertEqual(MODULE.PREAUDITED_STATUS[(2025, "exam_syllabus")], "access_restricted")
        self.assertEqual(MODULE.PREAUDITED_STATUS[(2025, "admission_policy")], "access_restricted")


    def test_embedded_attachment_discovery(self) -> None:
        parser = MODULE.LinkParser()
        parser.feed(
            '<html><head><title>2026专升本</title></head><body>'
            '<iframe src="/_upload/a.pdf" title="考试大纲"></iframe>'
            '<embed src="/_upload/b.pdf" type="application/pdf">'
            '<object data="/_upload/c.pdf" type="application/pdf"></object>'
            '</body></html>'
        )
        hrefs = {href for href, _ in parser.links}
        self.assertEqual(hrefs, {"/_upload/a.pdf", "/_upload/b.pdf", "/_upload/c.pdf"})

    def test_save_document_preserves_exact_bytes(self) -> None:
        raw = b"%PDF-1.7\x00\xffofficial-raw-bytes\n%%EOF"
        candidate = MODULE.Candidate(
            2026,
            "https://zsb.wxc.edu.cn/_upload/raw.pdf",
            "2026年专升本考试大纲",
            ("exam_syllabus",),
            kind="attachment",
            expected_filename="2026年考试大纲.pdf",
        )
        result = MODULE.FetchResult(
            True,
            candidate.url,
            candidate.url,
            200,
            {"content-type": "application/pdf"},
            raw,
        )
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            evidence_root = repo_root / "anhui_zsb_data" / "evidence" / "full_raw_30_schools" / "WXC"
            record, _ = MODULE.save_document(repo_root, evidence_root, candidate, result, "")
            saved = repo_root / record["local_path"]
            self.assertEqual(saved.read_bytes(), raw)
            self.assertEqual(record["sha256"], MODULE.sha256_bytes(raw))
            self.assertEqual(record["file_size"], len(raw))




    def test_exact_2025_official_candidates_are_seeded(self) -> None:
        urls = {candidate.url for candidate in MODULE.SEED_CANDIDATES if candidate.year == 2025}
        self.assertIn("https://www.ahzsks.cn/zyyx/8108.htm", urls)
        self.assertIn(
            "https://zsb.wxc.edu.cn/_upload/article/files/61/dc/c7c861c34e73a0b4a234a93c7f94/3b31146a-9b4a-4995-ba14-ab7eadc8c7c1.pdf",
            urls,
        )
        self.assertIn(
            "https://zsb.wxc.edu.cn/_upload/article/files/61/dc/c7c861c34e73a0b4a234a93c7f94/e4b3b43c-f1b7-4124-ba75-502aca08422d.pdf",
            urls,
        )

    def test_https_has_official_http_fallback(self) -> None:
        self.assertEqual(
            MODULE.transport_candidates("https://zsb.wxc.edu.cn/a.pdf"),
            ["https://zsb.wxc.edu.cn/a.pdf", "http://zsb.wxc.edu.cn/a.pdf"],
        )
        self.assertEqual(MODULE.transport_candidates("https://example.com/a.pdf"), ["https://example.com/a.pdf"])

    def test_attachment_soft_block_is_not_mislabeled_as_pdf_or_collected(self) -> None:
        html = b"<!doctype html><html><title>Access verification</title><body>captcha</body></html>"
        candidate = MODULE.Candidate(
            2026,
            "https://zsb.wxc.edu.cn/_upload/protected.pdf",
            "2026年专升本考试大纲",
            ("exam_syllabus",),
            kind="attachment",
            expected_filename="考试大纲.pdf",
        )
        result = MODULE.FetchResult(
            True, candidate.url, candidate.url, 200, {"content-type": "text/html; charset=utf-8"}, html
        )
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            evidence_root = repo_root / "anhui_zsb_data" / "evidence" / "full_raw_30_schools" / "WXC"
            record, _ = MODULE.save_document(repo_root, evidence_root, candidate, result, "")
            self.assertEqual(record["file_type"], "html")
            self.assertEqual(record["status"], "awaiting_manual_review")
            self.assertTrue((repo_root / record["local_path"]).read_bytes().startswith(b"<!doctype html>"))

    def test_cross_year_identical_bytes_keep_distinct_source_relationships(self) -> None:
        digest = MODULE.sha256_bytes(b"same")
        records = [
            {"year": 2024, "final_url": "https://zsb.wxc.edu.cn/a.pdf", "sha256": digest, "parent_page": "p2024"},
            {"year": 2025, "final_url": "https://zsb.wxc.edu.cn/a.pdf", "sha256": digest, "parent_page": "p2025"},
            {"year": 2025, "final_url": "https://zsb.wxc.edu.cn/a.pdf", "sha256": digest, "parent_page": "p2025"},
        ]
        deduped = MODULE.dedup_records(records)
        self.assertEqual(len(deduped), 2)
        self.assertEqual({row["year"] for row in deduped}, {2024, 2025})

    def test_seed_only_preserves_secondary_discovery_leads(self) -> None:
        import json
        import shutil

        source_root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            source = source_root / "anhui_zsb_data"
            shutil.copytree(source, repo_root / "anhui_zsb_data")
            discovery_path = (
                repo_root
                / "anhui_zsb_data"
                / "evidence"
                / "full_raw_30_schools"
                / "WXC"
                / "source_discovery.json"
            )
            before = json.loads(discovery_path.read_text(encoding="utf-8"))["secondary_leads"]
            MODULE.run_collection(repo_root, timeout=0.1, max_bytes=1024, retries=1, max_pages=1, seed_only=True)
            after = json.loads(discovery_path.read_text(encoding="utf-8"))["secondary_leads"]
            self.assertEqual(after, before)

    def test_distinct_failures_are_not_collapsed(self) -> None:
        rows = [
            {"year": 2024, "url": "https://zsb.wxc.edu.cn/a", "status": "access_restricted", "reason": "timeout"},
            {"year": 2025, "url": "https://zsb.wxc.edu.cn/b", "status": "access_restricted", "reason": "dns"},
        ]
        self.assertEqual(len(MODULE.dedup_records(rows)), 2)


if __name__ == "__main__":
    unittest.main()
