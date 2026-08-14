# 安徽专升本数据系统运行配置

```yaml
project_name: 安徽专升本数据系统
schema_version: 0.3.0
province: 安徽省
exam_type: 普通高校专升本
run_mode: pilot
pilot_school_id: HFNU
pilot_school_name: 合肥师范学院
target_years: [2024, 2025, 2026]
canonical_store: normalized_csv
constraint_store: sqlite
sqlite_path: db/anhui_zsb.sqlite
keep_raw_evidence: true
require_source_locator: true
use_deterministic_ids: true
allow_third_party_supplement: true
third_party_requires_label: true
store_personal_information: false
batch_ready: false
```

## 当前执行约束

- 本轮仅处理 HFNU Pilot，不自动进入 39 所院校 Batch；
- 新采集结果写入 `staging/<school_id>/<year>/`；
- 禁止执行 `legacy/` 中的旧脚本；
- 所有 canonical 输出只能由 `scripts/build_normalized.py` 生成；
- 任一 P0 验证失败时，流水线必须非零退出；
- Pilot B 通过前不冻结 Schema v1.0。
