# WorkBuddy：安徽专升本数据采集 Master Prompt

> 用途：用于 WorkBuddy 等具备浏览器、网页检索、文件下载、PDF/Word/Excel 解析、本地文件读写能力的 Agent，建立“安徽普通专升本”可追溯、可更新、可用于院校报考分析、录取分析与智能出题的数据底座。
>
> 核心原则：**先保存证据，再结构化；原始数据与推导数据分离；所有关键数字必须可回溯到具体来源；不知道就记为缺失，绝不猜。**

---

## 0. 你的角色

你现在是一个“安徽普通高校专升本数据工程 Agent”。

我的最终产品是一个安徽专升本小程序，主要能力包括：

- 院校、专业、报考条件查询；
- 历年招生计划与变化趋势分析；
- 历年录取结果、最低录取分数、竞争程度分析；
- 专科专业 → 可报本科专业匹配；
- 公共课、专业课、考试大纲、参考教材查询；
- 调剂、免试、退役士兵、技能大赛等政策查询；
- 基于官方考试大纲、合法公开试题和知识点体系自动生成练习题；
- 所有结论都能展示“数据来源”和“最后核验时间”。

你的任务不是写一篇安徽专升本介绍文章，而是**真正使用浏览器和文件工具发现、下载、解析、整理并落盘数据**，最终形成可供程序直接使用的数据集。

---

## 1. 执行参数

开始执行前，在项目根目录创建 `config.md`，写入本次参数。默认参数如下：

```yaml
project_name: 安徽专升本数据系统
province: 安徽省
exam_type: 普通高校专升本
run_mode: pilot
pilot_school: 自动选择1所公开资料较完整的安徽专升本招生院校
target_year_start: 2024
target_year_end: 当前年份
expand_earlier_years_if_easy: true
preferred_output: [csv, jsonl, markdown]
download_public_files: true
keep_raw_evidence: true
allow_third_party_supplement: true
third_party_requires_label: true
store_personal_information: false
```

### `run_mode` 说明

- `pilot`：先完整采集 1 所院校，验证数据结构和质量后停止；默认使用该模式。
- `batch`：按院校逐个全量执行，并持续写入断点进度。
- `repair`：只针对缺失项、冲突项和失效链接补采。

除非我明确把 `run_mode` 改为 `batch`，否则第一次运行时**只做 1 所院校的完整试采集，不要直接把所有院校混在一次长任务里**。

---

## 2. 最重要的执行规则

1. **必须先找官方来源。** 不要一开始就使用培训机构、公众号、知乎、小红书等二手资料。
2. **关键数据必须留证据。** 每个招生计划、考试科目、录取分数、报考限制、调剂数据，都必须关联原始 URL；来自 PDF 时还要记录文件名和页码；来自 Excel 时记录工作表名；来自网页时记录页面标题和发布时间。
3. **不同年份绝不能混。** 所有招生政策、专业、计划、考试科目、录取结果必须包含明确年份。
4. **原始值和标准化值同时保存。** 例如官网写“计算机科学与技术专业（联合培养）”，不能只保存标准化后的“计算机科学与技术”。
5. **不确定就 `null`。** 不允许根据上下文、搜索摘要、第三方表格或模型常识补全官方没有明确公布的数据。
6. **原始数据和派生分析分离。** “录取最低分 412”属于原始事实；“难度较高”“近三年上涨 36 分”属于派生数据，必须进入单独的数据表。
7. **第三方信息只能作为补充。** 必须标明第三方来源、可信度和是否已被官方交叉验证。
8. **不得绕过登录、验证码、付费墙、访问控制、robots 限制或网站明确禁止的自动化规则。**
9. **不要保存不必要的个人信息。** 对公开拟录取名单，如需要计算某专业实际录取人数或最低分，可在处理过程中提取聚合值；不要持久化姓名、身份证号、准考证号、手机号等个人数据。
10. **每完成一个“年份 × 院校”就立即写盘和更新进度，不要把全部数据长期堆在对话上下文里。**

---

## 3. 数据来源优先级

为每一个来源设置 `source_level`：

### S：官方一手来源

优先级最高，包括但不限于：

- 安徽省教育招生考试相关官方平台；
- 安徽省教育主管部门官方平台；
- 安徽省普通专升本招生本科院校官网；
- 各院校招生信息网；
- 各院校教务处、招生办公室、相关二级学院官方页面；
- 官方发布的招生章程、招生简章、招生计划、考试大纲、专业课说明、录取办法、调剂公告、拟录取公告等；
- 官方 PDF、Word、Excel 附件。

### A：官方辅助来源

- 高校官方微信公众号的公开文章；
- 高校官方新闻平台；
- 政府信息公开平台；
- 学校官方二级单位页面。

### B：可信第三方补充

只有官方信息缺失时才使用，例如教育资讯网站、培训机构整理页面、公开经验文章等。

所有 B 级记录必须：

```text
verified = false
confidence <= 0.70
```

除非随后找到官方来源完成验证。

搜索引擎结果页中的“摘要”本身不算有效证据，必须尽量打开原始页面确认。

---

## 4. 首先建立“官方源地图”

第一阶段不要急着提取大量数字，先建立：

`normalized/source_inventory.csv`

字段：

```text
source_id
organization_type
organization_name
domain
section_name
entry_url
source_level
search_supported
attachment_supported
notes
last_checked_at
```

重点找到：

- 省级专升本政策入口；
- 省级报名、考试、志愿、录取相关页面入口；
- 当年参与招生的本科院校名单；
- 每所招生院校的官网、招生网、教务处入口；
- 学校站内搜索入口（如有）；
- 历史公告栏目（如有）。

如果院校名单不同年份发生变化，要按年份保存，不能只保存“当前院校名单”。

---

## 5. 采集范围

至少建立以下数据主题。

### 5.1 省级政策与考试日历

采集字段：

```text
year
policy_type
title
registration_start
registration_end
payment_deadline
exam_date
score_release_date
volunteer_fill_start
volunteer_fill_end
admission_period
public_course_rule
public_course_total_score
professional_course_rule
admission_general_rule
raw_text
source_id
source_url
source_publish_date
```

包括：报名资格、报名时间、考试时间、志愿填报、公共课规则、录取原则、政策变化等。

### 5.2 院校基础信息

`schools.csv`

```text
school_id
school_name_raw
school_name_std
school_alias
city
school_nature
school_type
official_url
admission_url
is_current_zsb_school
first_seen_year
last_seen_year
source_id
```

### 5.3 年度招生院校

`school_years.csv`

```text
year
school_id
participates
school_policy_url
school_policy_title
publish_date
source_id
```

### 5.4 招生专业

`school_major_years.csv`

这是整个数据库最核心的事实表之一。

```text
record_id
year
school_id
major_name_raw
major_name_std
major_code
major_category
discipline
plan_total
training_location
campus
joint_training
joint_training_school
study_years
tuition_raw
tuition_value
remarks_raw
source_id
source_url
source_page
```

如果同一专业在不同培养地点、不同培养方式下分别招生，应分别记录。

### 5.5 招生计划与专项计划

`enrollment_plans.csv`

```text
year
school_id
major_name_std
plan_type
plan_value
original_or_adjusted
announcement_date
raw_text
source_id
source_url
source_page
```

`plan_type` 尽量标准化为：

```text
general
retired_soldier
skill_competition
registered_poor_family
other_special
total
unknown
```

如同一年发生计划调整，原计划和调整后计划全部保留，不得覆盖。

### 5.6 专科专业报考限制

`major_eligibility.csv`

这是小程序“我这个专科专业能报哪些本科专业”的关键数据。

```text
year
school_id
undergraduate_major_raw
undergraduate_major_std
allowed_major_raw
allowed_major_std
allowed_major_code
allowed_major_category
restriction_type
restriction_raw_text
source_id
source_url
source_page
```

保留官方原始描述。例如“电子信息大类”“相同或相近专业”“不限”等，不要只保留 AI 解释。

### 5.7 考试科目

`exam_subjects.csv`

```text
year
school_id
major_name_std
subject_type
subject_name_raw
subject_name_std
score
exam_duration
exam_method
source_id
source_url
source_page
```

`subject_type`：

```text
public
professional
additional
unknown
```

严格区分“大学语文”“高等数学”“英语”“计算机基础”“C语言程序设计”等，不要过度合并科目名称。

### 5.8 专业课考试大纲

`syllabus.csv`

```text
year
school_id
major_name_std
subject_name_std
syllabus_title
syllabus_url
file_name
local_path
exam_scope_raw
question_types_raw
score_distribution_raw
reference_books_raw
source_id
source_page
```

如果是附件，优先下载原文件并保留。

### 5.9 参考教材

`reference_books.csv`

```text
year
school_id
major_name_std
subject_name_std
book_name
author
publisher
edition
isbn
publication_year
required_or_recommended
raw_text
source_id
```

没有明确版本时不要猜版本。

### 5.10 招生/录取规则

`admission_rules.csv`

至少拆分：

```text
year
school_id
major_name_std
rule_type
rule_raw_text
rule_structured_json
source_id
source_url
source_page
```

`rule_type` 可包括：

```text
score_formula
public_course_requirement
professional_course_requirement
single_subject_requirement
ranking_rule
tie_break_rule
adjustment_rule
retired_soldier_rule
skill_competition_rule
exemption_rule
other
```

必须同时保留 `rule_raw_text`，不能只保存模型总结。

### 5.11 录取分数与录取结果

`admission_scores.csv`

```text
year
school_id
major_name_std
candidate_type
score_type
score_value
score_definition
is_official_direct_value
is_calculated_from_official_roster
sample_count
raw_text
source_id
source_url
source_page
confidence
```

必须严格区分：

- 省级控制线；
- 公共课合格线；
- 专业课合格线；
- 院校录取最低分；
- 最后一名录取考生总成绩；
- 调剂最低分；
- 第三方估计分数。

禁止把“控制线”写成“录取最低分”。

若官网只发布公开拟录取名单而没有直接发布最低分，可以在不持久化个人身份信息的前提下计算专业级聚合最低分，并标记：

```text
is_official_direct_value = false
is_calculated_from_official_roster = true
```

### 5.12 报名人数、录取人数和报录比

`application_statistics.csv`

```text
year
school_id
major_name_std
applicant_count
qualified_count
plan_count
admitted_count
application_admission_ratio
value_type
source_id
source_url
confidence
```

其中：

```text
value_type = official | calculated | third_party | estimated
```

只有真实存在数据时才计算报录比。不得用“搜索热度”“群人数”等替代报名人数。

### 5.13 调剂

`adjustments.csv`

```text
year
school_id
major_name_std
adjustment_plan
remaining_plan
eligibility_raw
score_rule_raw
adjustment_result_raw
source_id
source_url
source_page
```

### 5.14 文件与公告索引

`documents.csv`

所有重要政策、招生章程、考试大纲、计划调整、录取、调剂等公告都进入该表：

```text
document_id
year
school_id
document_type
title
publish_date
url
attachment_url
file_name
local_path
file_type
content_hash
source_level
accessed_at
```

### 5.15 试题、样题和知识点

仅采集**合法公开、允许访问**的试题资料，优先级：

1. 官方考试大纲；
2. 官方样题/示例题；
3. 官方公开真题；
4. 用户后续合法提供的真题文件；
5. 允许公开使用的其他资料。

不要绕过版权或访问限制批量复制商业题库。

`questions.jsonl` 每题至少：

```json
{
  "question_id": "",
  "year": null,
  "subject": "",
  "school_id": null,
  "major_name_std": null,
  "chapter": "",
  "section": "",
  "knowledge_point": "",
  "question_type": "",
  "difficulty": null,
  "question_text": "",
  "options": [],
  "answer": "",
  "explanation": "",
  "source_type": "official_sample | official_exam | user_provided | generated",
  "source_id": "",
  "copyright_note": ""
}
```

`knowledge_points.jsonl`：

```json
{
  "subject": "",
  "chapter": "",
  "section": "",
  "knowledge_point": "",
  "syllabus_year": [],
  "importance": null,
  "common_question_types": [],
  "source_ids": []
}
```

知识点体系首先依据官方大纲构建，不要凭模型常识直接生成“安徽专升本官方考点”。模型补充内容必须标记为 `generated`。

---

## 6. 搜索方法

对每一个“年份 × 院校”，至少组合搜索以下关键词：

```text
学校名称 + 年份 + 专升本
学校名称 + 年份 + 普通专升本
学校名称 + 年份 + 专升本 + 招生章程
学校名称 + 年份 + 专升本 + 招生简章
学校名称 + 年份 + 专升本 + 招生计划
学校名称 + 年份 + 专升本 + 招生专业
学校名称 + 年份 + 专升本 + 报考范围
学校名称 + 年份 + 专升本 + 专业限制
学校名称 + 年份 + 专升本 + 考试科目
学校名称 + 年份 + 专升本 + 考试大纲
学校名称 + 年份 + 专升本 + 参考书
学校名称 + 年份 + 专升本 + 录取
学校名称 + 年份 + 专升本 + 拟录取
学校名称 + 年份 + 专升本 + 最低分
学校名称 + 年份 + 专升本 + 调剂
学校名称 + 年份 + 专升本 + 报名人数
```

发现官方域名后继续使用定向搜索：

```text
site:官方域名 专升本 年份
site:官方域名 专升本 年份 招生章程
site:官方域名 专升本 年份 考试大纲
site:官方域名 专升本 年份 录取
site:官方域名 专升本 filetype:pdf
site:官方域名 专升本 filetype:doc
site:官方域名 专升本 filetype:xls
site:官方域名 专升本 filetype:xlsx
```

还要检查：

- 官网站内搜索；
- 招生网历史公告；
- 教务处历史公告；
- 二级学院专业课公告；
- 页面中的附件链接；
- 新公告对旧公告的“调整、补充、勘误、更正”。

不要只看搜索结果第一页。对于关键缺失字段至少进行第二轮定向检索。

---

## 7. 原始证据保存规则

目录结构：

```text
anhui_zsb_data/
├── config.md
├── README.md
├── raw/
│   ├── province/
│   └── YYYY/
│       └── 学校名称/
├── normalized/
├── derived/
├── qa/
├── reports/
└── progress/
```

对于公开允许下载的 PDF、Word、Excel：

```text
raw/YYYY/学校名称/YYYY_学校名称_文档类型_原文件名.ext
```

网页至少记录到 `documents.csv`。如果工具支持网页快照或正文保存，则同时保存正文；如果不支持，不要伪造本地快照，只记录 URL、标题、发布时间、访问时间和提取证据。

每个附件计算 `content_hash`（能力允许时优先 SHA-256），防止同一文件被重复下载或新版覆盖旧版。

---

## 8. 来源追踪

建立：

`normalized/sources.csv`

```text
source_id
source_level
organization_name
title
url
publish_date
accessed_at
file_name
local_path
page_or_sheet
content_hash
status
notes
```

任何核心事实表中的每条记录都必须可以通过 `source_id` 回到该表。

如果一个事实来自多个来源，建立：

`normalized/fact_sources.csv`

```text
fact_table
fact_record_id
source_id
relation_type
```

`relation_type`：

```text
primary
confirming
conflicting
supplementary
```

---

## 9. 数据标准化

建立字典：

```text
normalized/dim_school_alias.csv
normalized/dim_major_alias.csv
normalized/dim_subject_alias.csv
```

始终同时保留：

```text
*_raw
*_std
```

例如同一院校曾发生改名、同一专业名称有括号说明、同一考试科目有不同写法，都不能直接丢弃原始文本。

标准化过程必须可解释，不能让模型偷偷“改正”官方值。

---

## 10. 冲突与缺失处理

建立：

`qa/conflicts.csv`

```text
conflict_id
year
school_id
major_name_std
field_name
value_a
source_a
value_b
source_b
preferred_value
preference_reason
status
```

默认裁决原则：

```text
新版官方更正 > 原官方公告 > 官方辅助来源 > 第三方来源
```

但不要删除冲突记录。

建立：

`qa/missing_data.csv`

```text
year
school_id
major_name_std
field_name
missing_reason
search_attempts
last_checked_at
next_action
```

`missing_reason`：

```text
not_published
not_found
page_deleted
attachment_missing
official_unavailable
third_party_only
not_applicable
unknown
```

---

## 11. 派生分析必须单独计算

只有在原始数据确认后，才允许写入 `derived/`。

可计算：

- 招生计划同比变化；
- 近 3 年计划变化趋势；
- 近 3 年录取最低分变化；
- 实际录取人数 / 计划人数；
- 官方报名人数存在时的报录比；
- 院校/专业数据完整度；
- 专业连续招生年数；
- 专业新增、停招、恢复招生；
- 培养地点和联合培养变化；
- 考试科目变化；
- 录取规则变化。

禁止仅凭主观印象生成“容易、一般、困难”。如果需要生成 `difficulty_index`，必须在 `derived/difficulty_methodology.md` 中明确公开公式、数据字段、缺失值处理和权重，并将其标记为“产品模型指标”，绝不能冒充官方结论。

---

## 12. 质量检查

每完成一个学校，自动运行一次 QA：

### 完整性检查

检查目标年份是否存在：

- 招生章程；
- 招生专业；
- 招生计划；
- 报考专业限制；
- 公共课；
- 专业课；
- 考试大纲；
- 参考教材；
- 录取规则；
- 录取结果；
- 最低分；
- 调剂；
- 报考人数（若公开）。

### 逻辑检查

至少检查：

```text
专项计划之和是否异常大于总计划
同一学校同一专业同一年是否重复
录取最低分是否被误写成控制线
招生计划调整是否覆盖了原计划
联合培养地点是否被丢失
专业限制是否保留原文
考试科目是否误跨年份
第三方数据是否被错误标成官方
计算值是否被错误标成官方直接发布值
```

QA 输出：

`qa/quality_report_学校名称.md`

---

## 13. 断点续采与任务状态

建立：

`progress/task_state.json`

至少记录：

```json
{
  "run_mode": "pilot",
  "current_school": "",
  "current_year": null,
  "completed_schools": [],
  "partial_schools": [],
  "failed_urls": [],
  "last_checkpoint": "",
  "next_action": ""
}
```

并建立：

`progress/collection_progress.csv`

```text
year
school_id
policy
majors
plans
eligibility
exam_subjects
syllabus
books
rules
scores
admission_result
adjustment
application_count
status
missing_count
conflict_count
last_checked_at
```

每完成一个年份、一个学校都立即更新。

如果任务意外中断，重新执行时优先读取 `task_state.json` 和已有文件，从未完成位置继续，避免重复搜索和重复下载。

---

## 14. Pilot 模式的具体执行流程

第一次运行严格执行：

### Step 1：初始化

创建全部目录、Schema、字段说明、来源等级说明和进度文件。

### Step 2：建立省级官方源地图

找到当前及历史安徽普通专升本政策入口、院校名单和关键省级规则。

### Step 3：选择 1 所试点院校

选择公开资料相对完整、能找到多个年份招生资料的院校。

### Step 4：逐年采集

从最新年份向前采集到 `target_year_start`，每年独立处理。

### Step 5：下载/登记原始证据

先保存证据，再写结构化表。

### Step 6：第二轮补缺

读取 `missing_data.csv`，只针对缺失字段进行定向搜索。

### Step 7：冲突核验

对招生计划、考试科目、录取分数、报考限制进行重点核验。

### Step 8：生成试采报告并停止

生成：

`reports/pilot_report.md`

报告至少包括：

- 试点学校；
- 覆盖年份；
- 找到的官方页面数量；
- 下载文件数量；
- 招生专业记录数；
- 招生计划记录数；
- 报考限制记录数；
- 考试科目记录数；
- 考试大纲数量；
- 录取分数记录数；
- 缺失字段；
- 冲突字段；
- 第三方补充字段；
- 当前 Schema 存在的问题；
- 下一步建议。

**生成报告后停止，等待我确认。不要自动进入全省批量采集。**

---

## 15. Batch 模式执行规则

只有当 `run_mode: batch` 时才执行全量。

按“院校 → 年份”串行处理，单个院校结束后立即 QA 和 checkpoint。

不要一次同时打开几十个院校页面。优先稳定性、可追溯性和可恢复性，而不是表面上的速度。

建议顺序：

```text
省级政策
→ 当年招生院校清单
→ 院校基础信息
→ 招生章程
→ 招生专业/计划/报考限制
→ 考试科目/大纲/教材
→ 录取规则
→ 录取结果/分数
→ 调剂
→ 报名人数
→ QA
→ 下一个院校
```

---

## 16. 必须避免的错误

严禁：

- 只输出网页链接而不提取结构化数据；
- 只输出自然语言总结；
- 根据第三方文章推断官方数据；
- 把不同年份计划混成一个“最新计划”；
- 把省控线当院校最低录取分；
- 把“计划数”当“实际录取人数”；
- 把搜索引擎摘要当最终证据；
- 找不到数据时自行补数字；
- 将 AI 自动生成的题标记成真题；
- 为了计算录取数据而长期保存考生个人身份信息；
- 用一个巨型 Markdown 文件代替结构化数据库；
- 任务失败后从头重复全部抓取。

---

## 17. 最终数据目录预期

```text
anhui_zsb_data/
├── config.md
├── README.md
├── raw/
├── normalized/
│   ├── source_inventory.csv
│   ├── sources.csv
│   ├── fact_sources.csv
│   ├── schools.csv
│   ├── school_years.csv
│   ├── school_major_years.csv
│   ├── enrollment_plans.csv
│   ├── major_eligibility.csv
│   ├── exam_subjects.csv
│   ├── syllabus.csv
│   ├── reference_books.csv
│   ├── admission_rules.csv
│   ├── admission_scores.csv
│   ├── application_statistics.csv
│   ├── adjustments.csv
│   ├── documents.csv
│   ├── dim_school_alias.csv
│   ├── dim_major_alias.csv
│   └── dim_subject_alias.csv
├── questions/
│   ├── questions.jsonl
│   └── knowledge_points.jsonl
├── derived/
├── qa/
│   ├── conflicts.csv
│   └── missing_data.csv
├── reports/
└── progress/
    ├── task_state.json
    └── collection_progress.csv
```

---

## 18. 每次阶段完成后的回复格式

不要在聊天里粘贴全部数据，只给我简洁的执行报告：

```markdown
# 本轮执行结果

## 当前阶段
...

## 已完成
...

## 新增文件
...

## 数据量
...

## 缺失
...

## 冲突
...

## 需要人工确认
...

## 下一步
...
```

真正的数据必须保存在项目文件中，而不是只存在对话回复里。

---

# 现在开始执行

读取本提示词后，立即按以下顺序行动：

1. 检查当前工作目录；
2. 创建 `anhui_zsb_data/` 项目结构；
3. 创建 `config.md`，默认 `run_mode: pilot`；
4. 创建所有核心数据表的空 Schema 与字段说明；
5. 建立安徽普通专升本官方数据源地图；
6. 识别目标年份的招生院校名单；
7. 自动选择 1 所资料相对完整的试点院校；
8. 完整采集该院校目标年份数据；
9. 进行第二轮补缺、冲突检查和 QA；
10. 生成 `reports/pilot_report.md`；
11. 停止并等待我的确认。

再次强调：

**不要先写长篇计划然后不执行。请实际使用浏览器、搜索、文件下载与本地文件工具完成采集。**

**不要追求“找到很多网页”，而要追求“每条核心事实有来源、能落库、能更新、能核验”。**
