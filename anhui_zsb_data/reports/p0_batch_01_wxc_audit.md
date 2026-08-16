# P0 Batch 01：WXC 皖西学院原始数据审计

## 本批数据审计

- 本批学校数：1
- 新增 source document 数：0
- 新增/现存原始文件数：0
- 原始文件总字节数：0
- `collected` 覆盖格数：0
- `public_official_record` 覆盖格数：0
- `not_found`：21
- `access_restricted`：18
- `manual_download_required`：0
- `awaiting_manual_review`：45

## 覆盖状态分布

| status | 单元数 |
|---|---:|
| `access_restricted` | 18 |
| `awaiting_manual_review` | 45 |
| `not_found` | 21 |

## 逐年缺失审计

| 年份 | 已采主题 | 已定位但待取主题 | 仍待深检主题 | 原因 |
|---:|---|---|---|---|
| 2024 | — | major_catalog, exam_subjects, exam_syllabus, reference_books, other_official_notice | admission_policy, enrollment_plan, training_location, tuition_and_duration, eligibility, exam_schedule, exam_location, admission_rules, score_formula, control_line, admission_min_score, admission_max_score, admission_average_score, application_statistics, qualified_statistics, admitted_statistics, registered_statistics, plan_adjustment, adjustment, exemption, retired_soldier, registered_poor_family, skill_competition | 官方页面/附件深链已锁定，但当前执行网络无法取得原始字节 |
| 2025 | — | admission_policy, major_catalog, training_location, exam_subjects, exam_syllabus, reference_books, other_official_notice | enrollment_plan, tuition_and_duration, eligibility, exam_schedule, exam_location, admission_rules, score_formula, control_line, admission_min_score, admission_max_score, admission_average_score, application_statistics, qualified_statistics, admitted_statistics, registered_statistics, plan_adjustment, adjustment, exemption, retired_soldier, registered_poor_family, skill_competition | 官方页面/附件深链已锁定，但当前执行网络无法取得原始字节 |
| 2026 | — | major_catalog, training_location, exam_subjects, exam_syllabus, reference_books, other_official_notice | admission_policy, enrollment_plan, tuition_and_duration, eligibility, exam_schedule, exam_location, admission_rules, score_formula, control_line, admission_min_score, admission_max_score, admission_average_score, application_statistics, qualified_statistics, admitted_statistics, registered_statistics, plan_adjustment, adjustment, exemption, retired_soldier, registered_poor_family, skill_competition | 官方页面/附件深链已锁定，但当前执行网络无法取得原始字节 |

## 下一步

1. 直取已锁定的 2024 页面、2025 省考试院章程、2025 两个 PDF、2026 页面及两个 PDF。
2. 从招生站栏目页恢复 2025 考试大纲通知父页面 URL，补齐页面级证据。
3. 从相邻日期公告继续发现考试通知、控制线、调剂、计划调整和统计资料。
4. 每次成功下载后校验原始字节 SHA-256，并重建 42 校总审计。
