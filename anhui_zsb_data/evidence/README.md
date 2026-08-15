# Stage 1 官方证据包

`evidence/` 保存尚未进入 canonical/staging 的官方原始证据，与流水线输入目录 `raw/` 隔离。

## 目录

```text
evidence/
├── pilot_a/HFNU/
└── pilot_b/AHUA/
```

## Gate 0 收敛结果

- PR #3 是唯一 Stage 1 主 PR；
- 22 个官方 source document；
- 60 个证据资产，60 个唯一 SHA-256；
- 已纳入 PR #2 独有的 AHUA 2025、HFNU 2024 报名人数、HTML 解析文本和页面内嵌 PDF；
- 排除公共模板图片；两个官方空白申请/承诺表经隐私复核后作为章程附件保留；
- 不包含姓名、身份证号、考生号、准考证号或个人成绩明细。

完整审计：

```text
config/phase1_evidence_inventory.json
reports/stage1_pr_reconciliation.json
reports/stage1_pr_reconciliation.md
```

## 唯一采集入口

```bash
python3 scripts/collect_stage1_evidence.py --check-config
python3 scripts/collect_stage1_evidence.py --dry-run
python3 scripts/collect_stage1_evidence.py
```

采集器只能写入 `evidence/`，不会写入或清理 canonical `raw/`。官方字节、大小或最终 URL 与审计清单不一致时会立即失败。

离线验证：

```bash
python3 scripts/verify_stage1_evidence.py
```

Stage 1 不修改 Schema、staging、normalized、SQLite 或现有 canonical 业务数据。
