#!/usr/bin/env python3
"""
修复 staging JSON 中的跨表 ID 一致性问题

问题：exam_subjects.json 和 eligibility.json 使用了与 enrollment_plans.json 不同的 program_year_id
解决方案：
1. 从 enrollment_plans.json 提取正确的 major -> program_year_id 映射
2. 用该映射修复 exam_subjects.json 和 eligibility.json 中的 program_year_id
"""

import json
from pathlib import Path
from collections import defaultdict

BASE_DIR = Path(__file__).parent.parent
STAGING_DIR = BASE_DIR / "staging" / "HFNU"
YEARS = ["2024", "2025", "2026"]


def get_correct_major_to_py_mapping(year: str) -> dict:
    """从 enrollment_plans.json 获取正确的 major -> program_year_id 映射"""
    plans_file = STAGING_DIR / year / "enrollment_plans.json"
    with open(plans_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    # 从 enrollment_plans 构建 major -> program_year_id 映射
    # 注意：同一个 major 可能有多个 offering（本校 + 联培），但 program_year_id 应该相同
    major_to_py = {}
    for plan in data['enrollment_plans']:
        major = plan['major_name_raw']
        py_id = plan['program_year_id']
        if major in major_to_py and major_to_py[major] != py_id:
            print(f"WARNING: 发现冲突 {major} -> {major_to_py[major]} vs {py_id}")
        major_to_py[major] = py_id
    
    return major_to_py


def get_exam_subjects_py_to_major_mapping(year: str) -> dict:
    """
    从 exam_subjects.json 获取旧的 program_year_id -> major 映射
    通过分析每个 PY 的科目组合来反查对应的 major
    """
    # 从 extract.py 的数据结构反推：exam_subjects 是按 major 组织的
    # 每个 major 有 4 个科目，顺序是 public_1, public_2, professional_1, professional_2
    
    # 读取 exam_subjects
    subjects_file = STAGING_DIR / year / "exam_subjects.json"
    with open(subjects_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    # 按 program_year_id 分组
    py_groups = defaultdict(list)
    for s in data['exam_subjects']:
        py_groups[s['program_year_id']].append(s)
    
    # 构建 (public_1, public_2, professional_1, professional_2) -> program_year_id 映射
    subject_combo_to_py = {}
    for py_id, subjects in py_groups.items():
        # 按 slot 排序
        subjects_sorted = sorted(subjects, key=lambda x: x['subject_slot'])
        combo = tuple(s['subject_name_raw'] for s in subjects_sorted)
        subject_combo_to_py[combo] = py_id
    
    return subject_combo_to_py


def build_old_py_to_new_py_mapping(year: str, major_to_py: dict) -> dict:
    """
    构建旧的 program_year_id -> 新的 program_year_id 映射
    通过科目组合反查 major，然后找到正确的 program_year_id
    """
    # 这个函数需要通过 extract.py 的原始数据来建立映射
    # 但由于 extract.py 的数据是硬编码的，我们需要从 exam_subjects 的科目组合反推
    
    # 从 enrollment_plans 获取 major -> tuition -> subject_combo 的映射
    # 实际上更简单的方法是：直接对比 eligibility 和 exam_subjects 中的 program_year_id
    
    # 对于 eligibility：有 undergraduate_major_std，可以直接匹配
    elig_file = STAGING_DIR / year / "eligibility.json"
    with open(elig_file, 'r', encoding='utf-8') as f:
        elig_data = json.load(f)
    
    old_py_to_major = {}
    for e in elig_data['eligibility']:
        major = e['undergraduate_major_std']
        old_py_id = e['program_year_id']
        old_py_to_major[old_py_id] = major
    
    # 构建映射：old_py_id -> new_py_id
    py_mapping = {}
    for old_py_id, major in old_py_to_major.items():
        if major in major_to_py:
            new_py_id = major_to_py[major]
            py_mapping[old_py_id] = new_py_id
    
    return py_mapping


def fix_exam_subjects(year: str, py_mapping: dict) -> int:
    """修复 exam_subjects.json 中的 program_year_id"""
    subjects_file = STAGING_DIR / year / "exam_subjects.json"
    with open(subjects_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    fixed_count = 0
    for subject in data['exam_subjects']:
        old_py_id = subject['program_year_id']
        if old_py_id in py_mapping:
            subject['program_year_id'] = py_mapping[old_py_id]
            fixed_count += 1
    
    with open(subjects_file, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    
    return fixed_count


def fix_eligibility(year: str, py_mapping: dict) -> int:
    """修复 eligibility.json 中的 program_year_id"""
    elig_file = STAGING_DIR / year / "eligibility.json"
    with open(elig_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    fixed_count = 0
    for elig in data['eligibility']:
        old_py_id = elig['program_year_id']
        if old_py_id in py_mapping:
            elig['program_year_id'] = py_mapping[old_py_id]
            fixed_count += 1
    
    with open(elig_file, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    
    return fixed_count


def main():
    print("=" * 60)
    print("修复 staging JSON 跨表 ID 一致性")
    print("=" * 60)
    
    total_fixed = {'exam': 0, 'elig': 0}
    
    for year in YEARS:
        print(f"\n处理 {year} 年...")
        
        # 1. 获取正确的 major -> program_year_id 映射
        major_to_py = get_correct_major_to_py_mapping(year)
        print(f"  从 enrollment_plans 提取了 {len(major_to_py)} 个专业映射")
        
        # 2. 构建旧的 PY -> 新的 PY 映射
        py_mapping = build_old_py_to_new_py_mapping(year, major_to_py)
        print(f"  构建了 {len(py_mapping)} 个 PY ID 映射")
        
        if not py_mapping:
            print(f"  无需修复，跳过")
            continue
        
        # 3. 修复 exam_subjects
        exam_fixed = fix_exam_subjects(year, py_mapping)
        total_fixed['exam'] += exam_fixed
        print(f"  修复 exam_subjects: {exam_fixed} 条")
        
        # 4. 修复 eligibility
        elig_fixed = fix_eligibility(year, py_mapping)
        total_fixed['elig'] += elig_fixed
        print(f"  修复 eligibility: {elig_fixed} 条")
    
    print("\n" + "=" * 60)
    print(f"修复完成！共修复 exam_subjects: {total_fixed['exam']} 条, eligibility: {total_fixed['elig']} 条")
    print("=" * 60)
    print("\n下一步：运行 rebuild_from_staging.py 重新生成 normalized CSV")


if __name__ == '__main__':
    main()
