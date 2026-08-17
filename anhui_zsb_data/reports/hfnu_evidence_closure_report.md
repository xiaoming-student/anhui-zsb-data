# HFNU 证据收尾报告

> 生成时间：2026-08-14T22:20+08:00
> Schema：v0.3.0
> 阶段：Stage 1 — HFNU 有限证据收尾

---

## 一、收尾工作概要

### 1.1 归档 3 个已知官方网页

| 源文档 ID | 标题 | URL | HTTP 状态 | SHA-256 |
|---|---|---|---|---|
| SRC-HFNU-2024-ZC | 2024年招生章程 | https://zsb.hfnu.edu.cn/info/1003/2715.htm | 200 | 287a0ad40dd786ed... |
| SRC-HFNU-2024-LQ | 2024年录取分数线 | https://zsb.hfnu.edu.cn/info/1002/3065.htm | 200 | 5d7c3b001fdd413e... |
| SRC-HFNU-2025-LQ | 2025年录取分数线 | https://zsb.hfnu.edu.cn/info/1002/3475.htm | 200 | af0d182d21e6dacc... |

每个页面保存了：
- `raw/YYYY/HFNU/DOC-*-.html`（原始 HTML）
- `raw/YYYY/HFNU/DOC-*-_clean.txt`（清洗文本）
- `raw/YYYY/HFNU/DOC-*-_metadata.json`（含 canonical_url, title, publish_date, retrieved_at, http_status, content_type, encoding, sha256）

`source_catalog.json` 中 3 个文档的 status 从 `extracted_unarchived` 更新为 `verified`。

### 1.2 采集 2026 年录取分数线

**发现**：2026 年录取分数页面（https://zsb.hfnu.edu.cn/info/1002/3885.htm）使用 PDF 内嵌方式发布数据，而非 HTML 表格。

**保存的证据**：
- `raw/2026/HFNU/DOC-HFNU-2026-LQ.html`（包含 PDF 嵌入脚本的页面）
- `raw/2026/HFNU/DOC-HFNU-2026-LQ.pdf`（官方 PDF 附件）
- `raw/2026/HFNU/DOC-HFNU-2026-LQ_clean.txt`
- `raw/2026/HFNU/DOC-HFNU-2026-LQ_metadata.json`

**提取结果**：28 个专业全部提取，含 4 类招生类别：

| 类别 | published | blank |
|---|---:|---:|
| 普通计划 | 26 | 2 |
| 免文化课退役士兵 | 22 | 6 |
| 非免试退役士兵 | 3 | 25 |
| 建档立卡 | 25 | 3 |

**新增记录**：140 条 admission_scores（28 专业 × 5 类别）
- admission_scores: 305 → **445**
- published_value: 200 → **281**
- blank_in_source: 105 → **164**

**代码修复**：
1. `parse_score` 正则表达式：支持 `57(素质39)` 无冒号格式
2. `_resolve_score_offering`：支持 `与XXX联合培养` 完整句子提取机构名
3. `build_admission_scores`：从 `(2024, 2025)` 扩展为 `(2024, 2025, 2026)`
4. `validate.py` 和 `test_pipeline.py`：更新基线预期值

### 1.3 补查 2025 年联培分数

确认 2025 年 4 个联培 Offering 分数在官方页面上确实为空白（`blank_in_source`），保持原状。

---

## 二、HFNU 回归数据

| 指标 | 基线 (Pilot 2.3) | 收尾后 | 变化 |
|---|---:|---:|---|
| Program Year | 82 | 82 | ✅ 不变 |
| Program Offering | 89 | 89 | ✅ 不变 |
| 招生计划槽位 | 356 | 356 | ✅ 不变 |
| 考试科目 | 328 | 328 | ✅ 不变 |
| 考试 Session | 246 | 246 | ✅ 不变 |
| Eligibility | 82 | 82 | ✅ 不变 |
| 招生计划 explicit | 335 | 335 | ✅ 不变 |
| 招生计划 blank | 21 | 21 | ✅ 不变 |
| **录取分数记录** | **305** | **445** | **+140 (2026新增)** |
| 录取分数 published | 200 | 281 | +81 |
| 录取分数 blank | 105 | 164 | +59 |
| Fact Source | 1585 | 1725 | +140 |
| Active conflicts | 0 | 0 | ✅ |

所有既有 2024、2025 事实未丢失，deterministic ID 未漂移。

---

## 三、质量门禁结果

```
[PASS] Python 语法编译
[PASS] Staging 只读验证
[PASS] 完整 canonical 流水线
[PASS] 单元与集成测试 (14/14)
[PASS] 连续重建幂等测试
[PASS] Clean-room 完整重建测试
Quality gate: PASS
```

---

## 四、源文档与资产更新

| 更新项 | 之前 | 之后 |
|---|---|---|
| source_documents 数量 | 5 | 6 |
| source_assets 数量 | 3 | 16 |
| raw/ 新增文件 | — | 9 个 (3 HTML + 3 clean + 3 metadata) + 3 个 2026 LQ (HTML + PDF + clean + metadata) |

---

## 五、仍缺失项 (44 项 open)

| 类别 | 数量 | 说明 |
|---|---:|---|
| 2026 联培分数 (blank_in_source) | 4 项 | 电气工程及其自动化/环境设计/计算机科学与技术/食品质量与安全 (马鞍山师范) 2025年分数确认为空 |
| 2024-2026 考试大纲 | 3 项 | 仅 metadata 待补充 |
| 2024-2026 参考教材 | 3 项 | 仅 metadata 待补充 |
| 2024-2026 调剂 | 3 项 | 官方未公布 |
| 2024-2026 报名人数 | 3 项 | 官方未公布 |
| 其他 | 28 项 | 2026 年各专业的 blank_in_source 分数（主要为非免试退役士兵和音乐学全空） |
