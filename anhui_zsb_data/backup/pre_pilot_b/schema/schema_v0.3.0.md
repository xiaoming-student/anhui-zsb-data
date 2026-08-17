# 安徽专升本数据系统 Schema v0.3.0

## 1. 适用范围

本版本用于合肥师范学院（HFNU）2024—2026 年 Pilot 数据，重点解决：

- 同一本科专业存在多个联合培养点时的身份冲突；
- 招生计划空白、明确为零和未采集之间的语义差异；
- 录取分数的数值、原始字符串、招生类别和培养点关联；
- 每条核心事实到官方网页/PDF 页码、表格和行的证据回溯；
- 重复运行时 ID、CSV 和数据库结果保持稳定。

当前 Schema 已为多院校设计稳定 ID，但完整 Batch 仍需通过第二所异构院校 Pilot B 后再冻结为 v1.0。

---

## 2. 数据分层

```text
raw/        官方原始文件及解析产物
staging/    经人工/程序核验的来源级 JSON
normalized/规范化 canonical CSV 与兼容导出
 db/        由 canonical CSV 重建的 SQLite 数据库
 qa/        当前冲突和缺失项
 reports/   验证、幂等、重建和 Pilot 报告
```

唯一规范化流程：

```text
raw + config + staging
        ↓
scripts/build_normalized.py
        ↓
normalized/*.csv
        ↓
scripts/validate.py
        ↓
db/anhui_zsb.sqlite + reports + qa
```

`raw_manifest.csv` 是生成结果，不是上一次构建的输入。原始文件的描述性元数据由 `config/source_assets.json` 管理。

---

## 3. ID 规则

核心实体 ID 使用固定 namespace 的 UUIDv5，由自然键确定：

| 实体 | 自然键 |
|---|---|
| Program Year | 招生院校 + 年份 + 标准本科专业名 |
| Offering | Program Year + 培养类型 + 培养院校 + 培养校区 |
| Enrollment Plan | Offering + 计划类型 + 计划版本 |
| Exam Subject | Program Year + 科目槽位 |
| Exam Session | Program Year + 考试场次类型 |
| Eligibility | Program Year |
| Admission Score | Offering + 考生类别 + 分数指标 + 录取轮次 |
| Admission Rule | 学校 + 年份 + 规则类型 + 适用范围 |

要求：

- 输入行顺序变化时 ID 不变；
- 补入更早年份数据时既有 ID 不变；
- 重复执行时 ID 不变；
- 不同院校不会因简单年份计数器产生碰撞。

---

## 4. 核心实体关系

```text
institutions
   ├── program_years
   │      ├── program_offerings
   │      │       ├── enrollment_plans
   │      │       └── admission_scores
   │      ├── exam_subjects
   │      ├── exam_sessions
   │      ├── major_eligibility
   │      └── eligibility_rule_sets
   │                 └── eligibility_rule_items
   └── admission_rules

source_sites
   └── source_documents
             └── source_assets

所有核心事实 ── fact_sources ── source_documents/source_locator
```

---

# 5. 表定义

## 5.1 `institutions.csv`

**粒度：** 一所招生本科院校或联合培养院校一行。

**主键：** `institution_id`

主要字段：

- `institution_name_std`：标准名称，唯一；
- `institution_role`：`admission_school`、`joint_training_school` 或后续扩展值；
- `address`：官方来源中的地址；
- `address_source_id`、`address_source_locator`：地址证据。

---

## 5.2 `program_years.csv`

**粒度：** `年份 × 招生本科院校 × 本科专业`。

**主键：** `program_year_id`

**唯一约束：** `year + admission_school_id + major_name_std`

字段：

- `undergraduate_major_id`：稳定专业 ID；
- `major_name_raw` / `major_name_std`：官方原文和规范名；
- `admission_track_raw`：如“文”“理”“艺术(文)”；
- `admission_track_code`：`liberal`、`science`、`arts_liberal`、`sports_liberal`；
- `source_id`、`source_locator`：招生计划表证据。

---

## 5.3 `program_offerings.csv`

**粒度：** `Program Year × 培养点`。

**主键：** `offering_id`

**唯一约束：** `program_year_id + training_type + training_institution_id + training_campus`

字段：

- `training_type`：`main_school`、`joint_training`；
- `training_institution_id`：实际培养院校；
- `training_campus`：只有官方明确公布时填写；
- `training_campus_status`：当前支持 `published`、`not_published`；
- `remarks_source_raw`：严格保留来源备注，不写入程序推断的“校本部”；
- `training_type_is_derived`：培养类型是否由“无联合培养备注”推导；
- `tuition_value`、`study_years`；
- `source_id`、`source_locator`。

**重要规则：** “专业课考试地点在锦绣校区”不能推导为“学生培养地点在锦绣校区”。考试地点只能写入 `exam_sessions.csv`。

---

## 5.4 `enrollment_plans.csv`

**粒度：** `Offering × 计划类型 × 计划版本`。

**主键：** `enrollment_plan_id`

计划类型：

- `total`
- `retired_soldier_culture_exam_exempt`
- `retired_soldier_non_exempt`
- `registered_poor_family`

`value_status`：

- `explicit_value`：官方明确为正数；
- `explicit_zero`：官方明确写 0；
- `blank_in_source`：官方单元格为空；
- 后续允许扩展 `not_applicable`、`not_published`、`parse_failed`、`not_found`。

规则：

- 官方空白不得自动改成 0；
- 每个当前 HFNU Offering 必须保留 4 个计划槽位；
- 计划总数的唯一事实源是本表，不在 Offering 表重复维护 canonical `plan_total`。

---

## 5.5 `exam_subjects.csv`

**粒度：** `Program Year × 科目槽位`。

**主键：** `exam_subject_id`

`subject_slot`：

- `public_1`
- `public_2`
- `professional_1`
- `professional_2`

每个 Program Year 必须恰好 4 条。

专业课两门共同参加一场 180 分钟考试的安排不在单科字段中重复，而由 `exam_sessions.csv` 表达。

---

## 5.6 `exam_sessions.csv`

**粒度：** `Program Year × 考试场次`。

**主键：** `exam_session_id`

`session_type`：

- `public_1`
- `public_2`
- `professional_combined`

字段包含考试日期、开始/结束时间、时长、考试地点及其发布状态。`subject_slots_json` 指明一场考试覆盖哪些科目槽位。

---

## 5.7 `major_eligibility.csv`

**粒度：** 每个 Program Year 一条官方报考范围原文。

**主键：** `eligibility_id`

**唯一约束：** `program_year_id`

字段：

- `allowed_major_categories_raw`：官方报考范围原文；
- `allowed_major_categories_std`：顶层范围名称规范化结果；
- `restriction_raw_text`：完整限制原文；
- `source_id`、`source_locator`。

当前 Pilot 强制要求：

- 2024：28/28 Program Year 有 Eligibility；
- 2025：28/28；
- 2026：26/26；
- 不允许空 FK 或多余专业。

---

## 5.8 `eligibility_rule_sets.csv` / `eligibility_rule_items.csv`

`eligibility_rule_sets` 与 Program Year 一对一，保留整条规则。

`eligibility_rule_items` 将顶层“专业大类”拆成有序条目，并保存：

- `category_name_raw`
- `condition_raw`
- `include_or_exclude`

例如“电子与信息大类（限于 A、B、C 三个专业）”必须保留限制条件，不能错误理解为整个大类全部可报。

专业代码字段在接入官方高职/本科专业目录后再填充，禁止由模型猜测。

---

## 5.9 `admission_scores.csv`

**粒度：** `Offering × 考生类别 × 分数指标 × 录取轮次`。

**主键：** `admission_score_id`

当前考生类别：

- `normal`
- `retired_soldier_culture_exam_exempt`
- `retired_soldier_non_exempt`
- `registered_poor_family`
- `skill_competition`

字段：

- `score_value_numeric`：纯数值，供排序和分析；
- `score_raw`：官方原始字符串；
- `threshold_detail_json`：如同分条件“专业课1:69”；
- `score_basis`、`score_max`：防止不同量纲直接比较；
- `value_status`：当前为 `published_value` 或 `blank_in_source`；
- `admission_round`：当前历史数据为 `first_choice`，后续可扩展 A/B 段、调剂、补录；
- `source_id`、`source_locator`。

空白观察值也保留一行，避免把“官方表格为空”与“没有采集这条记录”混为一谈。

---

## 5.10 `admission_rules.csv`

**粒度：** `学校 × 年份 × 规则类型 × 适用范围`。

**主键：** `rule_id`

字段：

- `rule_raw_text`：官方规则原文；
- `rule_structured_json`：可查询的结构化表达；
- `rule_scope`：适用考生/阶段；
- `source_id`、`source_locator`。

当前仅保留经核验的 5 类核心规则，A/B 段、计划调整、调剂和技能大赛规则仍在 QA 中作为后续细化项。

---

# 6. 来源与证据表

## 6.1 `source_sites.csv`

来源站点，如“合肥师范学院本科招生网”。

## 6.2 `source_documents.csv`

一份具体官方文档或网页一行。状态支持：

- `verified`：已保存原始资产并核验；
- `extracted_unarchived`：已从官方网页提取，但本地快照尚未保存；
- 后续可扩展 `discovered`、`fetched`、`parsed`、`unavailable`、`failed`。

## 6.3 `source_assets.csv`

一份物理文件或派生解析文件一行：

- ASCII `local_path`
- 原始中文文件名
- MIME 类型
- 文件大小
- SHA-256
- 父资产、解析器及版本

物理文件描述元数据来自 `config/source_assets.json`，文件大小和 SHA-256 每次构建重新计算。

## 6.4 `fact_sources.csv`

为每条核心事实建立一条 `primary_evidence` 关系。验证器检查：

- `record_id` 必须真实存在；
- `source_id` 与事实表一致；
- `source_locator` 与事实表一致；
- 不允许遗漏或重复。

---

# 7. `source_locator` 规范

字段存储紧凑 JSON。

PDF 示例：

```json
{"asset_id":"ASSET-HFNU-2026-ZC-PDF","page":1,"section":"招生专业计划","row_key":"商务英语"}
```

HTML 示例：

```json
{"url":"https://zsb.hfnu.edu.cn/info/1003/2715.htm","section":"招生专业范围","table":2,"row_key":"软件工程"}
```

验证要求：

- `asset_id` 必须存在于 `source_assets.csv`；
- 资产必须属于该行 `source_id`；
- URL 必须与该 `source_document` 的官方 URL 一致；
- 核心事实覆盖率为 100%。

---

# 8. Canonical 与兼容导出

Canonical 表由 `schema/canonical_tables.json` / `.yaml` 明确登记。

兼容导出：

- `sources.csv`
- `documents.csv`

旧表：

- `school_major_years.csv`
- `source_inventory.csv`

已移动到 `legacy_exports/`，禁止下游将其当作 canonical 数据。

---

# 9. 数据库约束

`scripts/build_database.py` 生成：

```text
db/anhui_zsb.sqlite
```

数据库包含：

- PK、FK、自然键唯一约束；
- 计划、考试、Eligibility、分数和证据关系表；
- `fact_sources`；
- `v_program_offerings`；
- `v_published_admission_scores`；
- `PRAGMA user_version = 300`。

生成后必须通过：

```sql
PRAGMA foreign_key_check;
```

---

# 10. 质量门禁

正式流水线：

```bash
python3 extract.py
python3 run_pipeline.py
python3 -m unittest discover -s tests -v
PYTHONPATH=scripts python3 scripts/check_idempotence.py
PYTHONPATH=scripts python3 scripts/check_clean_rebuild.py
```

Batch 前必须同时满足：

- PK/FK、自然键验证通过；
- 计划槽位、Eligibility、分数矩阵验证通过；
- 全部 raw 文件路径和 SHA-256 验证通过；
- 所有核心 locator 可解析并指向正确来源；
- 连续两次构建字节完全相同；
- 空目录 clean-room 重建与当前 canonical 字节完全相同；
- 第二所异构院校 Pilot B 不要求修改核心 Schema。
