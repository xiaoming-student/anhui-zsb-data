# 阶段 1 官方证据包

`evidence/` 保存尚未进入 canonical/staging 的官方原始证据，与流水线输入目录 `raw/` 隔离。

## 目录

```text
evidence/
├── pilot_a/HFNU/       # 合肥师范学院缺失证据闭环
└── pilot_b/AHUA/       # 安徽艺术学院异构 Pilot B 证据包
```

## Pilot A：合肥师范学院

已归档：

- 2024 年招生章程 HTML；
- 2024、2025、2026 年录取分数网页 HTML；
- 2024、2025、2026 年专业课考试大纲官方通知 HTML；
- 2024、2025、2026 年考试大纲/参考书目 PDF 原件；
- PDF 解析文本，用于确认三个年份均存在参考书目相关内容；
- 2024 年招生章程关联的官方申请表附件。

## Pilot B：安徽艺术学院

选择安徽艺术学院是因为其同时具有艺术类实践考试、理论笔试专业、多所联合培养院校及多个培养校区，结构与 HFNU 明显不同。

证据包覆盖：招生章程、招生计划、专业和培养地点、考试科目、考试内容/大纲、参考教材、报考范围、录取规则、录取分数、调剂信息，以及官方分专业报考人数。

## 完整性

资产 URL、检索时间、大小和 SHA-256 记录在：

```text
config/phase1_evidence_inventory.json
```

离线验证：

```bash
python3 scripts/verify_stage1_evidence.py
```

阶段 1 仅补齐证据文件，不修改 Schema、staging、normalized、SQLite 或现有 HFNU canonical 数据。
