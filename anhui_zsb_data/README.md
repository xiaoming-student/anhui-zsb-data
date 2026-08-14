# 安徽专升本数据系统

[![Quality Gate](https://github.com/xiaoming-student/anhui-zsb-data/actions/workflows/quality-gate.yml/badge.svg)](https://github.com/xiaoming-student/anhui-zsb-data/actions/workflows/quality-gate.yml)

这是一个面向“安徽专升本院校报考、录取分析与智能出题”场景的数据底座项目。

当前版本为 **Schema v0.3.0 / HFNU Pilot 2.3**，覆盖合肥师范学院 2024—2026 年核心招生数据。代码已从早期的 append-only、Python 硬编码数组模式，重构为：

```text
官方原始证据 raw
        ↓
来源级核验数据 staging JSON
        ↓
确定性 normalize
        ↓
canonical CSV + SQLite
        ↓
自动验证、QA、报告
```

## 已实现能力

- Program Year / Offering 两级模型，正确表达多个联合培养点；
- 招生计划 4 类槽位及 `blank_in_source` 语义；
- 考试科目槽位和考试 Session；
- 专科专业大类报考范围及限制条件原文；
- 录取分数完整观察矩阵、纯数值字段和同分条件；
- UUIDv5 确定性 ID，不依赖数组顺序；
- 网页/PDF 页码、表格、行级 `source_locator`；
- raw 文件 ASCII 路径、SHA-256 与 manifest；
- SQLite PK/FK/唯一约束；
- 自动 QA、进度、报告、幂等测试和 clean-room 重建测试。

## 环境

- Python 3.10 或更高版本；
- 核心流水线仅使用 Python 标准库；
- 不需要安装第三方 Python 包。

## 快速运行

在项目根目录 `anhui_zsb_data/` 执行：

```bash
python3 extract.py
python3 run_pipeline.py
```

`extract.py` 只验证 staging，不会修改文件。

`run_pipeline.py` 会依次执行：

1. 从 staging 构建 canonical CSV；
2. 执行核心验证；
3. 重建 SQLite；
4. 生成 QA、进度和 Pilot 报告；
5. 执行严格状态验证。

## 完整质量门禁

```bash
python3 -m unittest discover -s tests -v
PYTHONPATH=scripts python3 scripts/check_idempotence.py
PYTHONPATH=scripts python3 scripts/check_clean_rebuild.py
```

也可以一次执行：

```bash
python3 scripts/run_quality_gate.py
```

从 Git 仓库根目录运行时：

```bash
cd anhui_zsb_data
python3 scripts/run_quality_gate.py
```

## 持续集成（GitHub Actions）

CI 配置位于 `.github/workflows/quality-gate.yml`，采用只读仓库权限，不会自动提交生成文件或修改 `main`。

触发方式：

- 创建或更新 Pull Request；
- push 到 `main` 以外的开发分支；
- 在 GitHub Actions 页面手动运行。

每次 CI 都会在 Ubuntu 上分别使用 Python 3.10、3.11、3.12 执行同一条门禁命令：

```bash
python3 scripts/run_quality_gate.py
```

三个 Python Matrix Job 必须分别通过。CI 状态以本页顶部的 `Quality Gate` 徽章和 Pull Request 的 Checks 为准。

每个 Job 无论成功或失败，都会保留并上传 14 天的 Actions Artifact，包括：

- `ci-logs/` 中的完整质量门禁日志；
- `qa/*.csv` 当前 QA 结果；
- `reports/*.json` 和 `reports/*.md` 验证、幂等、clean-room 重建及质量门禁报告。

## 目录结构

```text
anhui_zsb_data/
├── config/                 # 机构、来源文档、原始资产配置
├── raw/                    # 官方 PDF、HTML 等原始证据
├── staging/                # 经核验的来源级 JSON
├── normalized/             # canonical CSV 与兼容导出
├── db/                     # SQLite 数据库
├── schema/                 # Schema 文档与 canonical 表清单
├── scripts/                # 构建、验证、报告与测试脚本
├── tests/                  # 单元/集成测试
├── qa/                     # 当前冲突、缺失项和历史 QA
├── reports/                # Pilot、验证、幂等和重建报告
├── progress/               # 状态、进度与运行元数据
├── questions/              # 题库/知识点预留目录
├── legacy/                 # 已禁用的旧脚本
└── legacy_exports/         # 已退出 canonical 的旧表
```

## 关键入口

| 文件 | 用途 |
|---|---|
| `run_pipeline.py` | 完整流水线入口 |
| `normalize.py` | 仅重建 canonical CSV 的兼容入口 |
| `extract.py` | staging JSON 只读验证器 |
| `scripts/build_normalized.py` | canonical 构建器 |
| `scripts/validate.py` | PK/FK、业务规则、来源与状态验证 |
| `scripts/build_database.py` | 生成 `db/anhui_zsb.sqlite` |
| `scripts/generate_report.py` | 自动生成 QA、进度和报告 |
| `scripts/check_idempotence.py` | 连续两次构建字节一致性测试 |
| `scripts/check_clean_rebuild.py` | 空目录完整重建测试 |
| `scripts/run_quality_gate.py` | 一键执行全部质量检查 |

## 核心数据规模

当前 HFNU Pilot 的预期结果：

| 数据 | 记录数 |
|---|---:|
| Program Year | 82 |
| Program Offering | 89 |
| 招生计划槽位 | 356 |
| 考试科目 | 328 |
| 考试 Session | 246 |
| Eligibility | 82 |
| Eligibility Rule Item | 295 |
| 录取分数观察值 | 305 |
| 录取规则 | 15 |
| Fact Source | 1585 |

招生计划状态：

```text
explicit_value = 335
blank_in_source = 21
```

录取分数状态：

```text
published_value = 200
blank_in_source = 105
```

## 数据真实性原则

1. 原始证据与结构化数据分离；
2. 官方空白不自动改成 0；
3. 原始备注不混入模型推断；
4. 考试地点不推导为培养地点；
5. 官方公布分数与推导分数必须区分；
6. 专业代码只允许来自官方专业目录；
7. 所有关键事实必须有 `source_id + source_locator`；
8. 不知道就记录缺失，不编造。

## 当前限制

代码流水线已经通过 Pilot 级质量检查，但 **Batch Readiness 仍为 FAIL**，原因属于数据覆盖而不是当前代码错误：

- 2024 招生章程网页尚未保存本地 HTML 快照；
- 2024、2025 录取分数网页尚未保存本地 HTML 快照；
- 2026 录取数据尚未纳入当前 staging；
- 考试大纲、参考教材、调剂和报名人数仍待补充；
- 尚未完成第二所结构不同院校的 Pilot B。

建议 Pilot B 在不修改核心 Schema 的情况下通过后，再冻结 v1.0 并进入全量院校采集。

## Schema

完整字段、粒度、主键、外键、枚举和来源规范见：

```text
schema/schema_v0.3.0.md
```
