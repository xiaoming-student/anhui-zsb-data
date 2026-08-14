# Legacy 目录

这里保存 Pilot 早期脚本，仅供审计和迁移追溯。

- `populate_data_v1.py` 已在入口处主动抛出 `RuntimeError`；
- `original_scripts/` 中的脚本可能使用旧 Schema、硬编码数组或 append-only 写入；
- 禁止对当前 `normalized/` 执行这些脚本；
- 当前唯一正式入口是项目根目录的 `run_pipeline.py`。
