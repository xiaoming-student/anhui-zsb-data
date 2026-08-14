#!/usr/bin/env python3
"""
validate.py — Canonical data validation for Pilot 2.2
Exit code 0 = all checks pass, non-zero = P0 failures found.
"""
import csv
import hashlib
import sys
from pathlib import Path

# 路径配置
BASE_DIR = Path(__file__).resolve().parent.parent
CANONICAL_DIR = BASE_DIR / 'normalized'
RAW_DIR = BASE_DIR / 'raw'
STAGING_DIR = BASE_DIR / 'staging'
RAW_MANIFEST = BASE_DIR / 'raw_manifest.csv'

# P0 主键表
PK_TABLES = {
    'program_years': 'program_year_id',
    'program_offerings': 'offering_id',
    'enrollment_plans': 'enrollment_plan_id',
    'exam_subjects': 'exam_subject_id',
    'major_eligibility': 'eligibility_id',
    'admission_scores': 'admission_score_id',
}

# 外键关系
FK_RELATIONS = [
    # (child_table, child_fk_field, parent_table, parent_pk_field)
    ('program_offerings', 'program_year_id', 'program_years', 'program_year_id'),
    ('enrollment_plans', 'offering_id', 'program_offerings', 'offering_id'),
    ('exam_subjects', 'program_year_id', 'program_years', 'program_year_id'),
    ('major_eligibility', 'program_year_id', 'program_years', 'program_year_id'),
    ('admission_scores', 'offering_id', 'program_offerings', 'offering_id'),
]

class Validator:
    def __init__(self):
        self.p0_errors = []
        self.p1_warnings = []
        self.info = []
        self.data = {}  # table_name -> list[dict]

    def load_csv(self, table_name):
        """加载 canonical CSV"""
        csv_path = CANONICAL_DIR / f'{table_name}.csv'
        if not csv_path.exists():
            self.p0_errors.append(f'[P0] 文件缺失: normalized/{table_name}.csv')
            return []
        with open(csv_path, 'r', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)
            rows = list(reader)
        self.data[table_name] = rows
        self.info.append(f'[INFO] 加载 {table_name}: {len(rows)} 行')
        return rows

    def check_pk_uniqueness(self):
        """P0-1: 主键唯一性"""
        for table, pk_field in PK_TABLES.items():
            rows = self.data.get(table, [])
            if not rows:
                continue
            pk_values = [r.get(pk_field, '') for r in rows]
            # 过滤空值
            non_empty_pks = [v for v in pk_values if v]
            if len(non_empty_pks) != len(pk_values):
                empty_count = len(pk_values) - len(non_empty_pks)
                self.p0_errors.append(f'[P0] {table} 主键 {pk_field} 有 {empty_count} 个空值')
            duplicates = [v for v in non_empty_pks if non_empty_pks.count(v) > 1]
            if duplicates:
                dup_set = set(duplicates)
                self.p0_errors.append(f'[P0] {table} 主键 {pk_field} 重复: {list(dup_set)[:5]}')
            else:
                self.info.append(f'[INFO] {table} 主键唯一性检查通过 ({len(rows)} 行)')

    def check_fk_integrity(self):
        """P0-2: 外键完整性"""
        for child_table, child_fk, parent_table, parent_pk in FK_RELATIONS:
            child_rows = self.data.get(child_table, [])
            parent_rows = self.data.get(parent_table, [])
            if not child_rows or not parent_rows:
                continue
            parent_pks = set(r.get(parent_pk, '') for r in parent_rows)
            orphan_fks = [
                r.get(child_fk, '') for r in child_rows
                if r.get(child_fk, '') not in parent_pks and r.get(child_fk, '')
            ]
            if orphan_fks:
                self.p0_errors.append(
                    f'[P0] {child_table}.{child_fk} 存在 {len(orphan_fks)} 个孤儿外键'
                )
            else:
                self.info.append(
                    f'[INFO] {child_table} → {parent_table} 外键完整性检查通过'
                )

    def check_eligibility_coverage(self):
        """P0-3: 资格规则覆盖率 = 招生专业集合"""
        for year in ['2024', '2025', '2026']:
            py_rows = [
                r for r in self.data.get('program_years', [])
                if r.get('year') == year
            ]
            elig_rows = [
                r for r in self.data.get('major_eligibility', [])
                if r.get('year') == year
            ]
            py_majors = set(r.get('major_name_std', '') for r in py_rows)
            elig_majors = set(r.get('undergraduate_major_std', '') for r in elig_rows)
            # 过滤空值
            py_majors.discard('')
            elig_majors.discard('')
            if py_majors != elig_majors:
                missing = py_majors - elig_majors
                extra = elig_majors - py_majors
                if missing:
                    self.p0_errors.append(
                        f'[P0] {year}年 资格规则缺少专业: {missing}'
                    )
                if extra:
                    self.p0_errors.append(
                        f'[P0] {year}年 资格规则多余专业: {extra}'
                    )
            else:
                self.info.append(
                    f'[INFO] {year}年 资格规则覆盖率检查通过 ({len(py_majors)} 专业)'
                )

    def check_plan_slot_count(self):
        """P0-4: 每个 offering 必须有 4 个 plan slot"""
        plan_rows = self.data.get('enrollment_plans', [])
        offering_counts = {}
        for r in plan_rows:
            oid = r.get('offering_id', '')
            if oid:
                offering_counts[oid] = offering_counts.get(oid, 0) + 1
        bad_offerings = [oid for oid, cnt in offering_counts.items() if cnt != 4]
        if bad_offerings:
            self.p0_errors.append(
                f'[P0] {len(bad_offerings)} 个 offering 的 plan slot 数量 ≠ 4: '
                f'{bad_offerings[:5]}'
            )
        else:
            self.info.append(
                f'[INFO] plan slot 数量检查通过 ({len(offering_counts)} offerings × 4)'
            )

    def check_plan_value_status(self):
        """P0-5: plan 值状态分布检查"""
        plan_rows = self.data.get('enrollment_plans', [])
        explicit_cnt = sum(1 for r in plan_rows if r.get('value_status') == 'explicit_value')
        blank_cnt = sum(1 for r in plan_rows if r.get('value_status') == 'blank_in_source')
        total = explicit_cnt + blank_cnt
        if total != len(plan_rows):
            self.p0_errors.append(
                f'[P0] plan value_status 分布异常: explicit={explicit_cnt}, '
                f'blank={blank_cnt}, 其他={len(plan_rows) - total}'
            )
        else:
            self.info.append(
                f'[INFO] plan value_status 分布: explicit_value={explicit_cnt}, '
                f'blank_in_source={blank_cnt}, 合计={total}'
            )

    def check_file_paths(self):
        """P0-6: 原始文件路径存在性"""
        doc_rows = self.data.get('source_documents', [])
        if not doc_rows:
            self.p1_warnings.append('[P1] source_documents.csv 不存在或为空，跳过文件路径检查')
            return
        missing_files = []
        for r in doc_rows:
            file_path = r.get('file_path', '')
            if file_path and not (BASE_DIR / file_path).exists():
                missing_files.append(file_path)
        if missing_files:
            self.p0_errors.append(
                f'[P0] {len(missing_files)} 个原始文件路径不存在: {missing_files[:5]}'
            )
        else:
            self.info.append(
                f'[INFO] 原始文件路径检查通过 ({len(doc_rows)} 个文档)'
            )

    def check_sha256_hashes(self):
        """P0-7: raw_manifest SHA-256 校验"""
        if not RAW_MANIFEST.exists():
            self.p1_warnings.append('[P1] raw_manifest.csv 不存在，跳过 SHA-256 校验')
            return
        with open(RAW_MANIFEST, 'r', encoding='utf-8-sig') as f:
            manifest = list(csv.DictReader(f))
        bad_hashes = []
        for r in manifest:
            file_path = r.get('file_path', '')
            expected_hash = r.get('sha256', '')
            if not file_path or not expected_hash:
                continue
            full_path = BASE_DIR / file_path
            if not full_path.exists():
                bad_hashes.append((file_path, '文件不存在'))
                continue
            with open(full_path, 'rb') as f:
                actual_hash = hashlib.sha256(f.read()).hexdigest()
            if actual_hash != expected_hash:
                bad_hashes.append((file_path, f'期望 {expected_hash[:16]}..., 实际 {actual_hash[:16]}...'))
        if bad_hashes:
            self.p0_errors.append(
                f'[P0] {len(bad_hashes)} 个文件 SHA-256 校验失败: {bad_hashes[:5]}'
            )
        else:
            self.info.append(
                f'[INFO] SHA-256 校验通过 ({len(manifest)} 个文件)'
            )

    def check_source_locator_coverage(self):
        """P0-8: source_locator 覆盖率"""
        tables_to_check = ['program_years', 'program_offerings', 'enrollment_plans',
                           'exam_subjects', 'major_eligibility']
        for table in tables_to_check:
            rows = self.data.get(table, [])
            if not rows:
                continue
            missing_locator = [
                r for r in rows
                if not r.get('source_locator') or r.get('source_locator') == '{}'
            ]
            if missing_locator:
                self.p1_warnings.append(
                    f'[P1] {table} 有 {len(missing_locator)} 行缺少 source_locator'
                )
            else:
                self.info.append(
                    f'[INFO] {table} source_locator 覆盖率 100%'
                )

    def check_progress_consistency(self):
        """P0-9: 进度/统计与实际 CSV 行数一致"""
        progress_csv = BASE_DIR / 'progress' / 'collection_progress.csv'
        if not progress_csv.exists():
            self.p1_warnings.append('[P1] collection_progress.csv 不存在，跳过进度一致性检查')
            return
        # 检查每个 year 的实际行数
        for year in ['2024', '2025', '2026']:
            py_actual = len([
                r for r in self.data.get('program_years', [])
                if r.get('year') == year
            ])
            elig_actual = len([
                r for r in self.data.get('major_eligibility', [])
                if r.get('year') == year
            ])
            self.info.append(
                f'[INFO] {year}年 实际行数: program_years={py_actual}, '
                f'major_eligibility={elig_actual}'
            )

    def run_all_checks(self):
        """运行所有检查"""
        # 加载所有 canonical 表
        for table in list(PK_TABLES.keys()) + ['source_documents']:
            self.load_csv(table)

        # 执行检查
        self.check_pk_uniqueness()
        self.check_fk_integrity()
        self.check_eligibility_coverage()
        self.check_plan_slot_count()
        self.check_plan_value_status()
        self.check_file_paths()
        self.check_sha256_hashes()
        self.check_source_locator_coverage()
        self.check_progress_consistency()

    def print_report(self):
        """输出检查报告"""
        print('\n' + '='*60)
        print('  Pilot 2.2 数据验证报告')
        print('='*60)
        print('\n【信息】')
        for msg in self.info:
            print(f'  {msg}')
        if self.p1_warnings:
            print('\n【P1 警告】')
            for msg in self.p1_warnings:
                print(f'  {msg}')
        if self.p0_errors:
            print('\n【P0 错误】')
            for msg in self.p0_errors:
                print(f'  {msg}')
        print('\n' + '='*60)
        print(f'  汇总: P0 错误={len(self.p0_errors)}, P1 警告={len(self.p1_warnings)}')
        print('='*60 + '\n')

    def exit_code(self):
        """返回退出码：0=通过, 1=P0 失败"""
        return 1 if self.p0_errors else 0


def main():
    print('开始 Pilot 2.2 数据验证...\n')
    validator = Validator()
    validator.run_all_checks()
    validator.print_report()
    exit_code = validator.exit_code()
    if exit_code == 0:
        print('✅ 所有 P0 检查通过！可以进入 Batch 阶段。')
    else:
        print('❌ 存在 P0 错误，请先修复后再进入 Batch。')
    sys.exit(exit_code)


if __name__ == '__main__':
    main()
