# P0 Batch 02 — BCTB 原始证据采集审计

- 生成时间：2026-08-15T17:48:20.002382+00:00
- 学校：BCTB 蚌埠工商学院
- 年份：2024、2025、2026
- 主题矩阵：3 × 28 = 84

## 批次指标

- 本批学校数：1
- 新增 source document 数：11
- 新增原始附件/有效图片数：45
- 新增原始文件数：56
- 新增总字节数：2082128
- 新增 collected 覆盖格数：37
- 仍 not_found 数：47
- access_restricted 数：0
- manual_download_required 数：0
- privacy excluded 数：4

## 逐年已补主题

- 2024：admission_policy, enrollment_plan, skill_competition, other_official_notice
- 2025：admission_policy, enrollment_plan, major_catalog, training_location, exam_subjects, exam_syllabus, reference_books, exam_schedule, exam_location, score_formula, control_line, admission_min_score, adjustment, exemption, retired_soldier, registered_poor_family, skill_competition, other_official_notice
- 2026：admission_policy, enrollment_plan, major_catalog, exam_subjects, exam_syllabus, reference_books, exam_schedule, exam_location, score_formula, control_line, admission_min_score, adjustment, retired_soldier, skill_competition, other_official_notice

## 质量说明

- 仅保存 `bctb.edu.cn` 官方域名返回的原始字节。
- 页面附件和文章正文承载的有效图片均检查并保存；站点模板图片不保存。
- 所有原始文件记录 SHA-256、字节数、最终 URL、父页面和严格年份绑定。
- 含姓名、考生号、准考证号、身份证号或个人成绩的页面/附件不归档。
- `not_found` 不等同于 `official_not_published`，后续仍需二次深挖。
