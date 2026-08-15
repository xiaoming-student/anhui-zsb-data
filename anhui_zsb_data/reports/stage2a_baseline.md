# Stage 2A 基线报告

> 生成时间：2026-08-15T04:00:06+00:00
> 实际 main base：`5d16b24801979c070699514698d4ff9877575593`
> 分支基线提交：`f59030c37014194689a047c6f355c69fbcf49283`

## 版本与门禁

- Schema version：`0.3.0`
- Stage 1 inventory SHA-256：`fcaadc1d3b2d226226c333e8fd79be885612d42c5fe1c01dce1da23b26b1d16a`
- P0：0
- P1：0
- Unit tests：19
- Stage 1 guard：PASS
- Stage 1 verifier：PASS
- Idempotence：PASS
- Clean-room rebuild：PASS
- Quality gate：PASS

## 输入层计数

- 正式 source documents：5
- 正式 source assets：3
- Raw 文件：3
- Staging 文件：14
- Missing total/open：47 / 47

## Normalized 记录数

| 表 | 记录数 |
|---|---:|
| adjustments | 0 |
| admission_rules | 15 |
| admission_scores | 305 |
| application_statistics | 0 |
| dim_major_alias | 0 |
| dim_school_alias | 4 |
| dim_subject_alias | 38 |
| documents | 5 |
| eligibility_rule_items | 295 |
| eligibility_rule_sets | 82 |
| enrollment_plans | 356 |
| exam_sessions | 246 |
| exam_subjects | 328 |
| fact_sources | 1585 |
| institutions | 5 |
| major_eligibility | 82 |
| program_offerings | 89 |
| program_years | 82 |
| reference_books | 0 |
| school_years | 3 |
| schools | 1 |
| source_assets | 3 |
| source_documents | 5 |
| source_sites | 1 |
| sources | 5 |
| syllabus | 0 |

## SQLite 记录数

| 表 | 记录数 |
|---|---:|
| admission_rules | 15 |
| admission_scores | 305 |
| eligibility_rule_items | 295 |
| eligibility_rule_sets | 82 |
| enrollment_plans | 356 |
| exam_sessions | 246 |
| exam_subjects | 328 |
| fact_sources | 1585 |
| institutions | 5 |
| major_eligibility | 82 |
| program_offerings | 89 |
| program_years | 82 |
| schema_metadata | 2 |
| source_assets | 3 |
| source_documents | 5 |
| source_sites | 1 |

## Stable ID 快照

完整快照：`reports/stage2a_stable_ids_baseline.json`
SHA-256：`17f0e8a59a2188bdd26fca69805c139a67980c7b5ebd56fb97a0c607f2f52a73`

本报告生成于任何 HFNU Stage 2A 业务修改之前。
