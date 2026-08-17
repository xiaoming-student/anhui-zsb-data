# 安徽专升本数据系统最终修复与测试报告

> 修复版本：Pilot 2.3 / Schema v0.3.0  
> 处理对象：合肥师范学院 2024—2026 年 Pilot 代码与数据目录

## 1. 交付结论

当前项目已经完成可重复运行的 Pilot 级工程化修复：

- canonical 数据可从 `raw + config + staging` 完整重建；
- 所有核心 PK/FK、业务规则和来源关系通过验证；
- 连续两次构建结果字节完全一致；
- 复制最小输入到空目录后，可以重建出与当前目录完全一致的 canonical 数据；
- SQLite 外键检查通过；
- 14 项单元与集成测试全部通过；
- 质量门禁 6 个阶段全部通过。

当前代码适合继续完成 HFNU 缺失数据，并用于第二所院校 Pilot B。由于仍缺部分官方快照、2026 录取数据和考试大纲，项目主动保持：

```text
Batch Readiness = FAIL
```

这表示“暂不建议全量跑 39 所”，不是当前流水线测试失败。

---

## 2. 已修复的关键代码问题

### 2.1 数据生成方式

旧模式：

```text
Python 大型硬编码数组
→ append CSV
```

新模式：

```text
raw 官方证据
→ staging JSON
→ deterministic normalize
→ canonical CSV
→ SQLite / QA / report
```

旧 append-only 脚本已经移入 `legacy/` 并加运行保护。

### 2.2 Program Year / Offering

建立两级模型：

```text
Program Year = 年份 + 招生院校 + 本科专业
Offering     = Program Year + 实际培养点
```

联合培养院校不再因同名专业产生主键碰撞。

### 2.3 稳定 ID

所有核心 ID 使用 UUIDv5 自然键生成，不依赖数组顺序。解决了：

- 多培养点录取分数 ID 重复；
- 新增历史记录导致后续 ID 整体漂移；
- 第二所学校使用简单 `SRC-2025-ZC` 等 ID 时的潜在碰撞。

### 2.4 Source Asset 与 locator

- raw 物理文件使用 ASCII 路径；
- 原中文文件名保存在元数据；
- `config/source_assets.json` 成为资产描述输入；
- `raw_manifest.csv` 改为纯生成结果，消除循环依赖；
- 修复旧 `DOC-HFNU-...` locator，使其统一指向真实 `ASSET-HFNU-...`；
- 验证每个 locator 的资产/URL均属于该行 `source_id`；
- 核心 1585 条事实 locator 覆盖率和解析成功率均为 100%。

### 2.5 数据库

生成：

```text
db/anhui_zsb.sqlite
```

包含：

- PK、FK、自然键唯一约束；
- `fact_sources` 证据关系表；
- Program Offering 和已发布录取分数视图；
- `PRAGMA user_version = 300`；
- `PRAGMA foreign_key_check` 结果为空。

### 2.6 自动质量控制

新增/完善：

- `scripts/validate.py`
- `scripts/check_idempotence.py`
- `scripts/check_clean_rebuild.py`
- `scripts/run_quality_gate.py`
- `tests/test_pipeline.py`

验证内容包括：

- PK/FK；
- 计划槽位；
- Eligibility 年度覆盖；
- 分数观察矩阵；
- raw 文件路径、大小和 SHA-256；
- locator 资产归属；
- fact source 完整性；
- canonical 文件清单；
- progress、task state 和 report 一致性；
- SQLite 约束；
- 幂等与 clean-room 重建。

---

## 3. 已修复的数据错误

### 3.1 2026 商务英语计划

官方值：

```text
总计划 = 110
免文化课退役士兵 = 7
非免试退役士兵 = 1
建档立卡 = 8
```

当前已正确恢复 `1`。

招生计划最终状态：

```text
总槽位 = 356
explicit_value = 335
blank_in_source = 21
```

### 3.2 Eligibility

修复年度 copy/index patch 产生的错项后：

```text
2024 = 28 / 28
2025 = 28 / 28
2026 = 26 / 26
invalid FK = 0
```

2025 已恢复：

- 制药工程
- 新能源材料与器件

2026 已保留：

- 新能源材料与器件

并排除错误残留：

- 材料科学与工程
- 数据科学与大数据技术

### 3.3 录取分数

- 原 9 组重复 `admission_score_id` 已归零；
- 建立 5 类完整观察矩阵；
- `score_value_numeric` 与 `score_raw` 分离；
- 同分附加条件保存为 JSON；
- 当前共 305 条观察，其中：

```text
published_value = 200
blank_in_source = 105
```

### 3.4 培养地点和原始备注

- 不再把“专业课考试地点为锦绣校区”错误写成所有校本部专业的培养校区；
- main-school `training_campus` 保持空值并标记 `not_published`；
- `remarks_source_raw` 不再人为加入“校本部”；
- 考试时间和考试地点由 `exam_sessions.csv` 单独表达。

### 3.5 旧表

以下旧表已退出 canonical：

- `school_major_years.csv`
- `source_inventory.csv`

保存在 `legacy_exports/` 供历史审计，不会被新流水线误读。

---

## 4. 当前核心数据结果

| 数据表 | 记录数 |
|---|---:|
| institutions | 5 |
| program_years | 82 |
| program_offerings | 89 |
| enrollment_plans | 356 |
| exam_subjects | 328 |
| exam_sessions | 246 |
| major_eligibility | 82 |
| eligibility_rule_items | 295 |
| admission_scores | 305 |
| admission_rules | 15 |
| fact_sources | 1585 |

年度核心记录：

| 年份 | Program Year | Offering | 计划槽位 | 考试科目 | Eligibility |
|---:|---:|---:|---:|---:|---:|
| 2024 | 28 | 30 | 120 | 112 | 28 |
| 2025 | 28 | 31 | 124 | 112 | 28 |
| 2026 | 26 | 28 | 112 | 104 | 26 |

---

## 5. 实际测试结果

质量门禁：

| 检查 | 结果 |
|---|---:|
| Python 语法编译 | PASS |
| 14 个 staging JSON 只读校验 | PASS |
| 完整 canonical 流水线 | PASS |
| 14 项单元/集成测试 | PASS |
| 27 个 canonical/兼容文件连续构建幂等 | PASS |
| 27 个文件 clean-room 重建一致性 | PASS |
| Validator P0 | 0 |
| Validator P1 | 0 |
| Active conflicts | 0 |
| SQLite FK violations | 0 |

详细执行输出见：

```text
reports/quality_gate_report.md
reports/idempotence_test_pilot_2_3.md
reports/clean_rebuild_test_pilot_2_3.md
reports/validation_report.json
```

---

## 6. 使用方式

完整流水线：

```bash
python3 extract.py
python3 run_pipeline.py
```

全部质量检查：

```bash
python3 scripts/run_quality_gate.py
```

单独测试：

```bash
python3 -m unittest discover -s tests -v
PYTHONPATH=scripts python3 scripts/check_idempotence.py
PYTHONPATH=scripts python3 scripts/check_clean_rebuild.py
```

---

## 7. 仍未完成的内容

以下属于数据覆盖任务，不属于当前代码测试失败：

- 保存 2024 招生章程 HTML 快照；
- 保存 2024、2025 录取分数网页快照；
- 采集并纳入 2026 录取数据；
- 下载并解析 2024—2026 专业课考试大纲和参考书；
- 补充调剂数据；
- 官方未公开的报名人数继续保持缺失；
- 录取规则进一步拆分 A/B 段、计划调整、调剂和技能大赛细则；
- 执行第二所结构不同院校 Pilot B。

建议 Pilot B 在不修改核心 Schema 的前提下通过后，再冻结 v1.0 并进入全量院校采集。
