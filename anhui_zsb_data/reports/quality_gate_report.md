# 安徽专升本数据系统质量门禁报告

> 生成时间：2026-08-15T05:47:04+00:00
> Python：3.12.13
> 平台：Linux-6.17.0-1022-azure-x86_64-with-glibc2.39

## 总结：PASS

| 检查项 | 结果 | 耗时 |
|---|---:|---:|
| Python 语法编译 | PASS | 0.070s |
| Staging 只读验证 | PASS | 0.043s |
| 完整 canonical 流水线 | PASS | 0.547s |
| 单元与集成测试 | PASS | 1.978s |
| 连续重建幂等测试 | PASS | 0.679s |
| Clean-room 完整重建测试 | PASS | 0.626s |

## 执行详情

### Python 语法编译 — PASS

```text
$ /opt/hostedtoolcache/Python/3.12.13/x64/bin/python3 -m compileall -q run_pipeline.py normalize.py extract.py scripts tests

```

### Staging 只读验证 — PASS

```text
$ /opt/hostedtoolcache/Python/3.12.13/x64/bin/python3 extract.py
HFNU/2024: staging checked
HFNU/2025: staging checked
HFNU/2026: staging checked
Staging verification passed: 22 JSON files checked; no files were modified.
```

### 完整 canonical 流水线 — PASS

```text
$ /opt/hostedtoolcache/Python/3.12.13/x64/bin/python3 run_pipeline.py
QA/report generated: conflicts=0, missing=9
========================================================================
安徽专升本数据系统验证报告
========================================================================
[INFO] Raw manifest verified: 29 assets
[INFO] PK unique: source_sites.csv.source_site_id (1 rows)
[INFO] PK unique: source_documents.csv.source_document_id (10 rows)
[INFO] PK unique: source_assets.csv.asset_id (29 rows)
[INFO] FK valid: source_documents.csv.source_site_id -> source_sites.csv.source_site_id
[INFO] FK valid: source_assets.csv.source_document_id -> source_documents.csv.source_document_id
[INFO] PK unique: institutions.csv.institution_id (5 rows)
[INFO] PK unique: program_years.csv.program_year_id (82 rows)
[INFO] PK unique: program_offerings.csv.offering_id (89 rows)
[INFO] PK unique: enrollment_plans.csv.enrollment_plan_id (356 rows)
[INFO] PK unique: exam_subjects.csv.exam_subject_id (328 rows)
[INFO] PK unique: exam_sessions.csv.exam_session_id (246 rows)
[INFO] PK unique: major_eligibility.csv.eligibility_id (82 rows)
[INFO] PK unique: eligibility_rule_sets.csv.eligibility_rule_set_id (82 rows)
[INFO] PK unique: eligibility_rule_items.csv.eligibility_rule_item_id (295 rows)
[INFO] PK unique: admission_scores.csv.admission_score_id (445 rows)
[INFO] PK unique: admission_rules.csv.rule_id (15 rows)
[INFO] PK unique: syllabus.csv.syllabus_id (164 rows)
[INFO] PK unique: reference_books.csv.reference_book_id (199 rows)
[INFO] PK unique: application_statistics.csv.application_statistic_id (30 rows)
[INFO] PK unique: fact_sources.csv.fact_source_id (2118 rows)
[INFO] FK valid: program_years.csv.admission_school_id -> institutions.csv.institution_id
[INFO] FK valid: program_offerings.csv.program_year_id -> program_years.csv.program_year_id
[INFO] FK valid: program_offerings.csv.training_institution_id -> institutions.csv.institution_id
[INFO] FK valid: enrollment_plans.csv.offering_id -> program_offerings.csv.offering_id
[INFO] FK valid: exam_subjects.csv.program_year_id -> program_years.csv.program_year_id
[INFO] FK valid: exam_sessions.csv.program_year_id -> program_years.csv.program_year_id
[INFO] FK valid: major_eligibility.csv.program_year_id -> program_years.csv.program_year_id
[INFO] FK valid: eligibility_rule_sets.csv.program_year_id -> program_years.csv.program_year_id
[INFO] FK valid: eligibility_rule_items.csv.eligibility_rule_set_id -> eligibility_rule_sets.csv.eligibility_rule_set_id
[INFO] FK valid: admission_scores.csv.offering_id -> program_offerings.csv.offering_id
[INFO] FK valid: syllabus.csv.program_year_id -> program_years.csv.program_year_id
[INFO] FK valid: reference_books.csv.program_year_id -> program_years.csv.program_year_id
[INFO] FK valid: application_statistics.csv.offering_id -> program_offerings.csv.offering_id
------------------------------------------------------------------------
P0 errors: 0 | P1 warnings: 0
PASS

Pipeline complete:
  institutions: 5
  program_years: 82
  program_offerings: 89
  enrollment_plans: 356
  exam_subjects: 328
  exam_sessions: 246
  major_eligibility: 82
  eligibility_rule_items: 295
  admission_scores: 445
  admission_rules: 15
  syllabus: 164
  reference_books: 199
  application_statistics: 30
```

### 单元与集成测试 — PASS

```text
$ /opt/hostedtoolcache/Python/3.12.13/x64/bin/python3 -m unittest discover -s tests -v
QA/report generated: conflicts=0, missing=9
========================================================================
安徽专升本数据系统验证报告
========================================================================
[INFO] Raw manifest verified: 29 assets
[INFO] PK unique: source_sites.csv.source_site_id (1 rows)
[INFO] PK unique: source_documents.csv.source_document_id (10 rows)
[INFO] PK unique: source_assets.csv.asset_id (29 rows)
[INFO] FK valid: source_documents.csv.source_site_id -> source_sites.csv.source_site_id
[INFO] FK valid: source_assets.csv.source_document_id -> source_documents.csv.source_document_id
[INFO] PK unique: institutions.csv.institution_id (5 rows)
[INFO] PK unique: program_years.csv.program_year_id (82 rows)
[INFO] PK unique: program_offerings.csv.offering_id (89 rows)
[INFO] PK unique: enrollment_plans.csv.enrollment_plan_id (356 rows)
[INFO] PK unique: exam_subjects.csv.exam_subject_id (328 rows)
[INFO] PK unique: exam_sessions.csv.exam_session_id (246 rows)
[INFO] PK unique: major_eligibility.csv.eligibility_id (82 rows)
[INFO] PK unique: eligibility_rule_sets.csv.eligibility_rule_set_id (82 rows)
[INFO] PK unique: eligibility_rule_items.csv.eligibility_rule_item_id (295 rows)
[INFO] PK unique: admission_scores.csv.admission_score_id (445 rows)
[INFO] PK unique: admission_rules.csv.rule_id (15 rows)
[INFO] PK unique: syllabus.csv.syllabus_id (164 rows)
[INFO] PK unique: reference_books.csv.reference_book_id (199 rows)
[INFO] PK unique: application_statistics.csv.application_statistic_id (30 rows)
[INFO] PK unique: fact_sources.csv.fact_source_id (2118 rows)
[INFO] FK valid: program_years.csv.admission_school_id -> institutions.csv.institution_id
[INFO] FK valid: program_offerings.csv.program_year_id -> program_years.csv.program_year_id
[INFO] FK valid: program_offerings.csv.training_institution_id -> institutions.csv.institution_id
[INFO] FK valid: enrollment_plans.csv.offering_id -> program_offerings.csv.offering_id
[INFO] FK valid: exam_subjects.csv.program_year_id -> program_years.csv.program_year_id
[INFO] FK valid: exam_sessions.csv.program_year_id -> program_years.csv.program_year_id
[INFO] FK valid: major_eligibility.csv.program_year_id -> program_years.csv.program_year_id
[INFO] FK valid: eligibility_rule_sets.csv.program_year_id -> program_years.csv.program_year_id
[INFO] FK valid: eligibility_rule_items.csv.eligibility_rule_set_id -> eligibility_rule_sets.csv.eligibility_rule_set_id
[INFO] FK valid: admission_scores.csv.offering_id -> program_offerings.csv.offering_id
[INFO] FK valid: syllabus.csv.program_year_id -> program_years.csv.program_year_id
[INFO] FK valid: reference_books.csv.program_year_id -> program_years.csv.program_year_id
[INFO] FK valid: application_statistics.csv.offering_id -> program_offerings.csv.offering_id
------------------------------------------------------------------------
P0 errors: 0 | P1 warnings: 0
PASS

Pipeline complete:
  institutions: 5
  program_years: 82
  program_offerings: 89
  enrollment_plans: 356
  exam_subjects: 328
  exam_sessions: 246
  major_eligibility: 82
  eligibility_rule_items: 295
  admission_scores: 445
  admission_rules: 15
  syllabus: 164
  reference_books: 199
  application_statistics: 30
QA/report generated: conflicts=0, missing=9
========================================================================
安徽专升本数据系统验证报告
========================================================================
[INFO] Raw manifest verified: 29 assets
[INFO] PK unique: source_sites.csv.source_site_id (1 rows)
[INFO] PK unique: source_documents.csv.source_document_id (10 rows)
[INFO] PK unique: source_assets.csv.asset_id (29 rows)
[INFO] FK valid: source_documents.csv.source_site_id -> source_sites.csv.source_site_id
[INFO] FK valid: source_assets.csv.source_document_id -> source_documents.csv.source_document_id
[INFO] PK unique: institutions.csv.institution_id (5 rows)
[INFO] PK unique: program_years.csv.program_year_id (82 rows)
[INFO] PK unique: program_offerings.csv.offering_id (89 rows)
[INFO] PK unique: enrollment_plans.csv.enrollment_plan_id (356 rows)
[INFO] PK unique: exam_subjects.csv.exam_subject_id (328 rows)
[INFO] PK unique: exam_sessions.csv.exam_session_id (246 rows)
[INFO] PK unique: major_eligibility.csv.eligibility_id (82 rows)
[INFO] PK unique: eligibility_rule_sets.csv.eligibility_rule_set_id (82 rows)
[INFO] PK unique: eligibility_rule_items.csv.eligibility_rule_item_id (295 rows)
[INFO] PK unique: admission_scores.csv.admission_score_id (445 rows)
[INFO] PK unique: admission_rules.csv.rule_id (15 rows)
[INFO] PK unique: syllabus.csv.syllabus_id (164 rows)
[INFO] PK unique: reference_books.csv.reference_book_id (199 rows)
[INFO] PK unique: application_statistics.csv.application_statistic_id (30 rows)
[INFO] PK unique: fact_sources.csv.fact_source_id (2118 rows)
[INFO] FK valid: program_years.csv.admission_school_id -> institutions.csv.institution_id
[INFO] FK valid: program_offerings.csv.program_year_id -> program_years.csv.program_year_id
[INFO] FK valid: program_offerings.csv.training_institution_id -> institutions.csv.institution_id
[INFO] FK valid: enrollment_plans.csv.offering_id -> program_offerings.csv.offering_id
[INFO] FK valid: exam_subjects.csv.program_year_id -> program_years.csv.program_year_id
[INFO] FK valid: exam_sessions.csv.program_year_id -> program_years.csv.program_year_id
[INFO] FK valid: major_eligibility.csv.program_year_id -> program_years.csv.program_year_id
[INFO] FK valid: eligibility_rule_sets.csv.program_year_id -> program_years.csv.program_year_id
[INFO] FK valid: eligibility_rule_items.csv.eligibility_rule_set_id -> eligibility_rule_sets.csv.eligibility_rule_set_id
[INFO] FK valid: admission_scores.csv.offering_id -> program_offerings.csv.offering_id
[INFO] FK valid: syllabus.csv.program_year_id -> program_years.csv.program_year_id
[INFO] FK valid: reference_books.csv.program_year_id -> program_years.csv.program_year_id
[INFO] FK valid: application_statistics.csv.offering_id -> program_offerings.csv.offering_id
------------------------------------------------------------------------
P0 errors: 0 | P1 warnings: 0
PASS

Pipeline complete:
  institutions: 5
  program_years: 82
  program_offerings: 89
  enrollment_plans: 356
  exam_subjects: 328
  exam_sessions: 246
  major_eligibility: 82
  eligibility_rule_items: 295
  admission_scores: 445
  admission_rules: 15
  syllabus: 164
  reference_books: 199
  application_statistics: 30

[stderr]
test_canonical_manifest_has_no_ghost_tables (test_pipeline.PipelineTestCase.test_canonical_manifest_has_no_ghost_tables) ... ok
test_core_counts (test_pipeline.PipelineTestCase.test_core_counts) ... ok
test_eligibility_exact_coverage_and_foreign_keys (test_pipeline.PipelineTestCase.test_eligibility_exact_coverage_and_foreign_keys) ... ok
test_exam_session_model (test_pipeline.PipelineTestCase.test_exam_session_model) ... ok
test_fact_source_links_are_complete (test_pipeline.PipelineTestCase.test_fact_source_links_are_complete) ... ok
test_main_school_training_semantics (test_pipeline.PipelineTestCase.test_main_school_training_semantics) ... ok
test_plan_slots_and_business_english_regression (test_pipeline.PipelineTestCase.test_plan_slots_and_business_english_regression) ... ok
test_score_matrix_ids_and_numeric_values (test_pipeline.PipelineTestCase.test_score_matrix_ids_and_numeric_values) ... ok
test_score_parser (test_pipeline.PipelineTestCase.test_score_parser) ... ok
test_source_assets_hashes_and_all_locators_resolve (test_pipeline.PipelineTestCase.test_source_assets_hashes_and_all_locators_resolve) ... ok
test_sqlite_integrity_and_views (test_pipeline.PipelineTestCase.test_sqlite_integrity_and_views) ... ok
test_stable_ids_and_idempotent_canonical_build (test_pipeline.PipelineTestCase.test_stable_ids_and_idempotent_canonical_build) ... ok
test_validator_and_staging_verifier (test_pipeline.PipelineTestCase.test_validator_and_staging_verifier) ... ok
test_yearly_counts (test_pipeline.PipelineTestCase.test_yearly_counts) ... ok
test_blank_form_must_be_optional_child_of_source_html (test_stage1_evidence_guard.Stage1EvidenceGuardTestCase.test_blank_form_must_be_optional_child_of_source_html) ... ok
test_clean_removes_only_inventory_managed_files (test_stage1_evidence_guard.Stage1EvidenceGuardTestCase.test_clean_removes_only_inventory_managed_files) ... ok
test_exact_inventory_tree_passes (test_stage1_evidence_guard.Stage1EvidenceGuardTestCase.test_exact_inventory_tree_passes) ... ok
test_source_requires_exactly_one_html_snapshot (test_stage1_evidence_guard.Stage1EvidenceGuardTestCase.test_source_requires_exactly_one_html_snapshot) ... ok
test_untracked_file_is_rejected (test_stage1_evidence_guard.Stage1EvidenceGuardTestCase.test_untracked_file_is_rejected) ... ok
test_2026_admission_scores_use_official_pdf_and_preserve_blanks (test_stage2a_hfnu.Stage2AHFNUIntegrationTestCase.test_2026_admission_scores_use_official_pdf_and_preserve_blanks) ... ok
test_application_statistics_are_official_and_plan_reconciled (test_stage2a_hfnu.Stage2AHFNUIntegrationTestCase.test_application_statistics_are_official_and_plan_reconciled) ... ok
test_evidence_raw_promotion_is_byte_identical_and_closed (test_stage2a_hfnu.Stage2AHFNUIntegrationTestCase.test_evidence_raw_promotion_is_byte_identical_and_closed) ... ok
test_existing_business_ids_and_rows_do_not_drift (test_stage2a_hfnu.Stage2AHFNUIntegrationTestCase.test_existing_business_ids_and_rows_do_not_drift) ... ok
test_fact_sources_and_sqlite_include_stage2a_tables (test_stage2a_hfnu.Stage2AHFNUIntegrationTestCase.test_fact_sources_and_sqlite_include_stage2a_tables) ... ok
test_no_candidate_personal_records_were_introduced (test_stage2a_hfnu.Stage2AHFNUIntegrationTestCase.test_no_candidate_personal_records_were_introduced) ... ok
test_promotion_and_staging_tools_are_reproducible (test_stage2a_hfnu.Stage2AHFNUIntegrationTestCase.test_promotion_and_staging_tools_are_reproducible) ... ok
test_qa_and_progress_reflect_stage2a_without_claiming_completion (test_stage2a_hfnu.Stage2AHFNUIntegrationTestCase.test_qa_and_progress_reflect_stage2a_without_claiming_completion) ... ok
test_source_catalog_and_assets_are_formally_registered (test_stage2a_hfnu.Stage2AHFNUIntegrationTestCase.test_source_catalog_and_assets_are_formally_registered) ... ok
test_syllabus_and_reference_books_map_to_professional_subjects (test_stage2a_hfnu.Stage2AHFNUIntegrationTestCase.test_syllabus_and_reference_books_map_to_professional_subjects) ... ok

----------------------------------------------------------------------
Ran 29 tests in 1.894s

OK
```

### 连续重建幂等测试 — PASS

```text
$ /opt/hostedtoolcache/Python/3.12.13/x64/bin/python3 scripts/check_idempotence.py
Idempotence: PASS (27 files)
```

### Clean-room 完整重建测试 — PASS

```text
$ /opt/hostedtoolcache/Python/3.12.13/x64/bin/python3 scripts/check_clean_rebuild.py
Clean rebuild: PASS (27 files)
```

