# 合肥师范学院专升本 Stage 2A 集成报告

> 自动生成时间：2026-08-15T05:47:05+00:00
> Schema：v0.3.0（未修改）

## 结论

HFNU 已审计证据已正式进入 canonical raw、source catalog/source assets、staging、normalized CSV 与 SQLite。

**Batch Readiness 仍为 FAIL。** 下一步是人工 Review Stage 2A，合并后执行 AHUA Stage 2B；不得直接进入全省 Batch。

## 核心数据量

| 数据表 | 记录数 |
|---|---:|
| Program Year | 82 |
| Program Offering | 89 |
| 招生计划槽位 | 356 |
| 考试科目 | 328 |
| 录取分数观察值 | 445 |
| 考试大纲 | 164 |
| 参考教材 | 199 |
| 报名人数 | 30 |

## 年度覆盖

| 年份 | Offering | 分数观察 | 已发布分数 | 大纲 | 参考教材 | 报名统计 | Open Missing |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 2024 | 30 | 150 | 116 | 56 | 70 | 30 | 1 |
| 2025 | 31 | 155 | 84 | 56 | 70 | 0 | 6 |
| 2026 | 28 | 140 | 81 | 52 | 59 | 0 | 2 |

## Stage 2A 已完成

- 26 个 HFNU Stage 1 evidence asset 按相同字节提升到 canonical raw。
- 正式 source document 增至 10，source asset 增至 29。
- 2026 官方录取表生成 28 个 Offering × 5 类 = 140 条观察值。
- 2024—2026 大纲与参考教材由官方 PDF staging 可重复构建。
- 2024 官方分专业报名人数生成 30 条 application statistics；计划数与 canonical 全部一致。
- 分数状态：published_value=281，blank_in_source=164。
- 计划状态：explicit_value=335，blank_in_source=21。
- 既有稳定 ID 漂移为 0。

## 当前 QA

- Active conflicts：0
- Open missing：9
- 仍开放：三年 adjustments、2025/2026 application statistics、四个 2025 官方空白录取 Offering。

## 下一步

人工 Review 并合并 Stage 2A 后，从最新 main 创建 Stage 2B AHUA Pilot B 分支。Schema v1.0 仍不得冻结。
