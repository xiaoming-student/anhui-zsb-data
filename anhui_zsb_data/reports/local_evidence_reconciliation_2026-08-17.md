# 本地数据证据迁移与远程分支整合报告

> 生成日期：2026-08-17（Asia/Shanghai）
> 本地基线快照：`1ee8fb8`
> 原始目录策略：只复制、不移动、不删除；`raw_acquisition` 作为迁移前只读备份保留。

## Git 整合记录

1. 本地未提交成果已保存为提交 `1ee8fb8`，并建立安全分支 `codex/pre-evidence-integration-20260817-local-snapshot`。
2. `origin/main` 已合入当前 `feat/pilot-b-ahnu`，合并提交为 `94d0404`；生成物和主线脚本冲突采用远程完整基线，本地原版本仍可从安全分支恢复。
3. BCTB 数据分支摘取 105 个目标文件，HBLG 数据分支摘取 140 个目标文件，统一提交为 `249fec5`。
4. 未把两个数据分支的历史代码整体带入，只纳入逐校 evidence、coverage、manifest 和对应采集报告。

## 完成结果

- 审计候选文件：326 个；
- 与远程现有内容字节相同：21 个（其中 16 个已在 evidence，5 个仅在 canonical raw，本次同步提升到补证区）；
- 仅本地逻辑文件：305 个，已全部映射并复制；
- 仅本地唯一 SHA-256：280 个；
- 具有来源 URL：268 个；缺少 URL、仍需溯源：58 个；
- 原始 `raw_acquisition` 备份文件：297 个，迁移校验后设为只读。

说明：305 个仅本地文件中包含 1 个审计时存在的 macOS `.DS_Store`。它被单列到 `_system/system_metadata`，不计作招生业务证据，但其字节和 SHA-256 仍被保存，保证审计数量闭合。

## 目录结构

```text
evidence/local_reconciliation/
├── schools/<学校ID>/<年份>/<主题>/
├── provincial/<年份>/<主题>/
├── _system/cross_year/system_metadata/
├── local_evidence_manifest.json
├── local_source_catalog.csv
├── sha256_manifest.csv
└── raw_acquisition_backup_sha256.csv
```

## 仅本地文件分布

### 按年份

| 年份 | 文件数 |
|---|---:|
| 2024 | 18 |
| 2025 | 130 |
| 2026 | 147 |
| cross_year | 10 |

### 按主题

| 主题 | 文件数 |
|---|---:|
| `adjustment` | 1 |
| `admission_min_score` | 23 |
| `admission_policy` | 238 |
| `application_statistics` | 8 |
| `control_line` | 1 |
| `enrollment_plan` | 4 |
| `exam_syllabus` | 23 |
| `other_official_notice` | 6 |
| `system_metadata` | 1 |

### 按学校（含省级与系统项）

| ID | 文件数 |
|---|---:|
| `AHAU` | 7 |
| `AHJZU` | 7 |
| `AHMU` | 7 |
| `AHNU` | 26 |
| `AHSTU` | 6 |
| `AHSZU` | 7 |
| `AHTCM` | 7 |
| `AHUA` | 6 |
| `AHUT` | 9 |
| `AHYZ` | 4 |
| `AIIT` | 5 |
| `AISU` | 6 |
| `ANHUI-PROV` | 28 |
| `AQNU` | 6 |
| `AUFE` | 4 |
| `AUST` | 3 |
| `AXHU` | 7 |
| `AYCC` | 6 |
| `BBC` | 6 |
| `BBMU` | 7 |
| `BCTB` | 4 |
| `BZU` | 6 |
| `CHU` | 6 |
| `CHZU` | 5 |
| `CUHF` | 7 |
| `CZU` | 4 |
| `FYNU` | 4 |
| `FYUT` | 5 |
| `HBLG` | 5 |
| `HFNU` | 13 |
| `HFUE` | 6 |
| `HFUU` | 6 |
| `HNNU` | 6 |
| `HSU` | 6 |
| `LOCAL-SYSTEM` | 1 |
| `MASU` | 6 |
| `SLU` | 7 |
| `TLU` | 6 |
| `UTA` | 3 |
| `UWH` | 6 |
| `WDU` | 6 |
| `WHIT` | 3 |
| `WJIT` | 6 |
| `WNMC` | 7 |
| `WXC` | 7 |

## 后续仍需补找

1. 优先处理 `local_source_catalog.csv` 中 `review_required=true` 的条目，补齐官方 URL、抓取时间和页面定位。
2. 2024 年逐校招生章程仍是明显缺口；现有本地批量章程主要集中在 2025、2026 年。
3. 录取分数、报名/录取人数、专业课大纲和参考书目的学校覆盖仍不完整，应按 full-42 coverage 继续采集。
4. 本次目录属于本地补证区，不直接改写 `full_raw_30_schools` 的封闭审计结果；完成来源复核后再提升到正式逐校 evidence。

## 可复现命令

```bash
python3 anhui_zsb_data/scripts/reconcile_local_evidence.py --snapshot 1ee8fb8
```
