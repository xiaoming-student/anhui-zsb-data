# Stage 2A HFNU 官方证据正式入库报告

> 生成时间：2026-08-15T05:47:05+00:00
> Base SHA：`5d16b24801979c070699514698d4ff9877575593`
> Implementation Head：`pending_draft_pr`
> Schema：v0.3.0（未修改）

## Evidence / Source / Asset

- HFNU evidence assets：26
- Promoted raw assets：26
- SHA mismatches：0
- Unmanaged raw files：0
- Source documents：5 → 10
- Source assets：3 → 29

## Canonical 记录数

| 表 | Before | After | Added | Updated | Deleted |
|---|---:|---:|---:|---:|---:|
| adjustments | 0 | 0 | 0 | 0 | 0 |
| admission_rules | 15 | 15 | 0 | 0 | 0 |
| admission_scores | 305 | 445 | 140 | 0 | 0 |
| application_statistics | 0 | 30 | 30 | 0 | 0 |
| dim_major_alias | 0 | 0 | 0 | 0 | 0 |
| dim_school_alias | 4 | 4 | 0 | 0 | 0 |
| dim_subject_alias | 38 | 38 | 0 | 0 | 0 |
| documents | 5 | 10 | 5 | 3 | 0 |
| eligibility_rule_items | 295 | 295 | 0 | 0 | 0 |
| eligibility_rule_sets | 82 | 82 | 0 | 0 | 0 |
| enrollment_plans | 356 | 356 | 0 | 0 | 0 |
| exam_sessions | 246 | 246 | 0 | 0 | 0 |
| exam_subjects | 328 | 328 | 0 | 0 | 0 |
| fact_sources | 1585 | 2118 | 533 | 0 | 0 |
| institutions | 5 | 5 | 0 | 0 | 0 |
| major_eligibility | 82 | 82 | 0 | 0 | 0 |
| program_offerings | 89 | 89 | 0 | 0 | 0 |
| program_years | 82 | 82 | 0 | 0 | 0 |
| reference_books | 0 | 199 | 199 | 0 | 0 |
| school_years | 3 | 3 | 0 | 0 | 0 |
| schools | 1 | 1 | 0 | 0 | 0 |
| source_assets | 3 | 29 | 26 | 0 | 0 |
| source_documents | 5 | 10 | 5 | 3 | 0 |
| source_sites | 1 | 1 | 0 | 0 | 0 |
| sources | 5 | 10 | 5 | 3 | 0 |
| syllabus | 0 | 164 | 164 | 0 | 0 |

## 关键事实

- 2026 admission score observations：140
- 2026 published score values：81
- Syllabus：164
- Reference books：199
- Application statistics：30

## Stable ID

- Existing ID drift：0
- New IDs：533

## QA

- Closed missing：38
- Remaining missing：9
- Conflicts：0
- P0：0
- P1：0

## 测试

- Local quality gate：PASS
- Unit tests：PASS (29 tests)
- Idempotence：PASS
- Clean-room rebuild：PASS
- GitHub Actions：PENDING_DRAFT_PR

## 边界

- Schema 未修改。
- AHUA 未进入 canonical。
- Batch Ready 仍为 false。
- HFNU 仍在 partial_schools，不标记为 completed。

## 未解决问题

- 2024-2026 historical adjustments remain not_found
- 2025 and 2026 official application statistics remain unpublished
- four 2025 offerings remain blank in the official score source
- AHUA Pilot B has not entered canonical data
