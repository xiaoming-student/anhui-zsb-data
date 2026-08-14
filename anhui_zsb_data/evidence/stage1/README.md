# Stage 1 官方证据收件区

本目录保存阶段 1 已获取、但尚未提升为 canonical 输入的官方证据。

- 抓取批次：`2026-08-14T17:10:00+00:00`
- Pilot A：合肥师范学院（HFNU）
- Pilot B：安徽艺术学院（AHUA）
- 原始层级：`evidence/stage1/raw/<year>/<school>/`
- 完整文件清单、URL、字节数和 SHA-256：`../../reports/stage1_evidence_fetch_report.json`

## 为什么不直接放入 canonical `raw/`

项目当前约束要求 `raw/` 下每一个文件都必须先登记到
`config/source_assets.json`，否则质量门禁会拒绝构建。本阶段只负责证据
获取与审计，不提前修改 staging、normalized、SQLite 或 Schema，因此先
进入独立收件区。

下一阶段完成来源复核后，应按以下顺序提升：

1. 为官方页面和附件建立稳定的 source/document/asset 标识；
2. 登记文件大小、MIME、SHA-256、父资产和解析关系；
3. 将通过复核的文件移动至 canonical `raw/`；
4. 更新 staging 与 source locator；
5. 执行完整质量门禁并检查 canonical 差异。

## 隐私边界

本目录不包含需要身份证号、考生号或登录验证才能访问的查询结果，也不
归档含考生姓名、考生号等个人信息的名单型页面。
