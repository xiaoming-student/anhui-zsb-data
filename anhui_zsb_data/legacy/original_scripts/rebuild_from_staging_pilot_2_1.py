#!/usr/bin/env python3
"""
从 staging JSON 重建 normalized CSV

新架构：
1. 从 staging/HFNU/{year}/*.json 读取原始数据
2. 使用 id_mapping.json 获取正确的 ID
3. 生成 normalized/*.csv
"""

import json
import csv
from pathlib import Path
from typing import Dict, List, Any

# 配置
BASE_DIR = Path(__file__).resolve().parent.parent
STAGING_DIR = BASE_DIR / "staging" / "HFNU"
NORMALIZED_DIR = BASE_DIR / "normalized"
YEARS = ["2024", "2025", "2026"]


def load_json(filepath: Path) -> Dict:
    """加载 JSON 文件"""
    with open(filepath, 'r', encoding='utf-8') as f:
        return json.load(f)


def write_csv(filepath: Path, headers: List[str], rows: List[Dict]):
    """写入 CSV 文件"""
    with open(filepath, 'w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        writer.writeheader()
        writer.writerows(rows)
    print(f"✓ {filepath.name}: {len(rows)} 行")


def load_id_mapping(year: str) -> Dict:
    """加载 id_mapping.json"""
    mapping_file = STAGING_DIR / year / "id_mapping.json"
    if mapping_file.exists():
        return load_json(mapping_file)
    return {}


def normalize_track(track: str) -> str:
    """标准化 track 名称"""
    track_map = {
        '艺术': '艺术(文)',
        '体育': '体育(文)',
    }
    return track_map.get(track, track)


def extract_institution_from_remarks(remarks: str) -> str:
    """从 remarks_source_raw 提取联合培养院校名称"""
    if '与' in remarks and '联合培养' in remarks:
        start = remarks.index('与') + 1
        end = remarks.index('联合培养')
        return remarks[start:end].strip()
    return ''


def get_ids_from_mapping(id_mapping: Dict, major: str, track: str, institution: str = None) -> Dict:
    """
    从 id_mapping 获取 program_year_id 和 offering_id
    
    键格式：major|track|institution（主校时 institution 为空）
    """
    # 标准化 track
    track = normalize_track(track)
    
    if institution:
        key = f"{major}|{track}|{institution}"
    else:
        key = f"{major}|{track}|"
    
    if key in id_mapping:
        return id_mapping[key]
    
    # 如果找不到，返回 None
    return None


def find_program_year_id_by_major(id_mapping: Dict, major: str) -> Dict:
    """
    根据专业名称查找 program_year_id
    尝试所有可能的 track
    """
    tracks = ['文', '理', '艺术(文)', '体育(文)']
    
    for track in tracks:
        # 先尝试主校键
        key = f"{major}|{track}|"
        if key in id_mapping:
            return id_mapping[key]
        
        # 再尝试联合培养键
        for k, v in id_mapping.items():
            parts = k.split('|')
            if len(parts) == 3 and parts[0] == major and parts[1] == track:
                return v
    
    return None


def find_offering_id_by_major_track(id_mapping: Dict, major: str, track: str = None) -> Dict:
    """
    根据专业名称和 track 查找 offering_id
    如果 track 为 None，尝试所有可能的 track
    """
    if track:
        track = normalize_track(track)
        tracks = [track]
    else:
        tracks = ['文', '理', '艺术(文)', '体育(文)']
    
    for t in tracks:
        # 先尝试主校键
        key = f"{major}|{t}|"
        if key in id_mapping:
            return id_mapping[key]
        
        # 再尝试联合培养键
        for k, v in id_mapping.items():
            parts = k.split('|')
            if len(parts) == 3 and parts[0] == major and parts[1] == t:
                return v
    
    return None


def build_year_id_index(year: str) -> Dict:
    """
    构建年度的 ID 索引，方便后续查找
    
    返回:
      main_index: {(major, normalized_track): {program_year_id, offering_id}}
      joint_index: {(major, normalized_track, institution): {program_year_id, offering_id}}
      all_entries: [所有记录]
    """
    mapping = load_id_mapping(year)
    main_index = {}
    joint_index = {}
    
    for key, value in mapping.items():
        parts = key.split('|')
        if len(parts) != 3:
            continue
        major, track, institution = parts[0], parts[1], parts[2]
        track = normalize_track(track)
        
        if not institution:
            main_index[(major, track)] = value
        else:
            joint_index[(major, track, institution)] = value
    
    return {
        'mapping': mapping,
        'main_index': main_index,
        'joint_index': joint_index,
    }


def resolve_ids(idx: Dict, major: str, track: str, institution: str = None) -> Dict:
    """
    使用索引解析 ID，带标准化和回退
    """
    track = normalize_track(track)
    
    if institution:
        key = (major, track, institution)
        if key in idx['joint_index']:
            return idx['joint_index'][key]
    
    # 尝试主校
    key = (major, track)
    if key in idx['main_index']:
        return idx['main_index'][key]
    
    # 尝试联合培养（取第一个匹配的）
    for (m, t, inst), v in idx['joint_index'].items():
        if m == major and t == track:
            return v
    
    return None


def rebuild_program_years():
    """重建 program_years.csv"""
    rows = []
    
    for year in YEARS:
        year_dir = STAGING_DIR / year
        idx = build_year_id_index(year)
        
        # 加载 enrollment_plans 获取专业列表
        ep_file = year_dir / "enrollment_plans.json"
        if not ep_file.exists():
            continue
        
        ep_data = load_json(ep_file)
        plans = ep_data['data']
        
        # 提取唯一的 program_year_id（从 id_mapping）
        seen_py_ids = set()
        
        for plan in plans:
            major = plan['major_name_raw']
            raw_track = plan['admission_track_raw']
            track = normalize_track(raw_track)
            training_type = plan.get('training_type', '')
            
            # 确定 institution
            if training_type == 'joint_training':
                remarks = plan.get('remarks_source_raw', '')
                institution = extract_institution_from_remarks(remarks)
                if not institution:
                    continue  # 没有 institution 的联合培养跳过
            else:
                institution = None
            
            ids = resolve_ids(idx, major, track, institution)
            if not ids:
                print(f"  警告: 找不到 ID 映射: {major}|{track}|{institution or ''}")
                continue
            
            py_id = ids['program_year_id']
            if py_id not in seen_py_ids:
                seen_py_ids.add(py_id)
                
                # 构建 program_years 记录
                rows.append({
                    'program_year_id': py_id,
                    'year': year,
                    'school_id': 'HFNU',
                    'major_name_raw': major,
                    'major_name_std': major,
                    'admission_track': track,
                    'source_id': f'SRC-{year}-ZC'
                })
    
    write_csv(
        NORMALIZED_DIR / "program_years.csv",
        ['program_year_id', 'year', 'school_id', 'major_name_raw', 'major_name_std', 
         'admission_track', 'source_id'],
        rows
    )
    return rows


def rebuild_program_offerings():
    """重建 program_offerings.csv"""
    rows = []
    
    for year in YEARS:
        year_dir = STAGING_DIR / year
        mapping = load_id_mapping(year)
        
        # 加载 enrollment_plans
        ep_file = year_dir / "enrollment_plans.json"
        if not ep_file.exists():
            continue
        
        ep_data = load_json(ep_file)
        plans = ep_data['data']
        
        for plan in plans:
            major = plan['major_name_raw']
            track = plan['admission_track_raw']
            training_type = plan.get('training_type', '')
            
            # 确定 institution
            if training_type == 'joint_training' and 'training_institution_name' in plan:
                institution = plan['training_institution_name']
            else:
                institution = None
            
            ids = get_ids_from_mapping(mapping, major, track, institution)
            if not ids:
                continue
            
            # 构建 program_offerings 记录
            rows.append({
                'offering_id': ids['offering_id'],
                'program_year_id': ids['program_year_id'],
                'year': year,
                'training_type': training_type,
                'training_institution_id': '',  # 简化处理
                'training_institution_name': institution or '',
                'training_campus': '',  # 从 plan 中获取（如果有的话）
                'training_address': '',  # 从 plan 中获取（如果有的话）
                'tuition_value': plan.get('tuition_value', ''),
                'study_years': '2',  # 默认值
                'remarks_source_raw': plan.get('remarks_source_raw', ''),
                'training_type_is_derived': 'false',  # 简化处理
                'training_type_derivation_method': '',
                'source_id': f'SRC-{year}-ZC',
                'source_locator': plan.get('source_locator', '')
            })
    
    write_csv(
        NORMALIZED_DIR / "program_offerings.csv",
        ['offering_id', 'program_year_id', 'year', 'training_type', 
         'training_institution_id', 'training_institution_name', 'training_campus',
         'training_address', 'tuition_value', 'study_years', 'remarks_source_raw',
         'training_type_is_derived', 'training_type_derivation_method',
         'source_id', 'source_locator'],
        rows
    )
    return rows


def rebuild_enrollment_plans():
    """重建 enrollment_plans.csv"""
    rows = []
    
    for year in YEARS:
        year_dir = STAGING_DIR / year
        mapping = load_id_mapping(year)
        
        # 加载 enrollment_plans
        ep_file = year_dir / "enrollment_plans.json"
        if not ep_file.exists():
            continue
        
        ep_data = load_json(ep_file)
        plans = ep_data['data']
        
        for plan in plans:
            major = plan['major_name_raw']
            track = plan['admission_track_raw']
            training_type = plan.get('training_type', '')
            
            # 确定 institution
            if training_type == 'joint_training' and 'training_institution_name' in plan:
                institution = plan['training_institution_name']
            else:
                institution = None
            
            ids = get_ids_from_mapping(mapping, major, track, institution)
            if not ids:
                continue
            
            offering_id = ids['offering_id']
            
            # 4 个 enrollment_plan 记录
            plan_types = [
                ('total', plan.get('plan_total', '')),
                ('retired_soldier_culture_exam_exempt', plan.get('plan_retired_soldier_culture_exam_exempt', '')),
                ('retired_soldier_non_exempt', plan.get('plan_retired_soldier_non_exempt', '')),
                ('registered_poor_family', plan.get('plan_registered_poor_family', ''))
            ]
            
            for plan_type, plan_value in plan_types:
                # 确定 value_status
                if plan_value == '':
                    value_status = 'blank_in_source'
                else:
                    value_status = 'explicit_value'
                
                # 生成 plan_id（包含 offering_id 避免重复）
                plan_id = f"PLAN-{offering_id}-{plan_type}"
                
                rows.append({
                    'enrollment_plan_id': plan_id,
                    'offering_id': offering_id,
                    'plan_type': plan_type,
                    'plan_value': plan_value,
                    'value_status': value_status,
                    'is_derived': 'false',
                    'derivation_method': '',
                    'raw_value': str(plan_value),
                    'source_id': f'SRC-{year}-ZC',
                    'source_locator': plan.get('source_locator', '')
                })
    
    write_csv(
        NORMALIZED_DIR / "enrollment_plans.csv",
        ['enrollment_plan_id', 'offering_id', 'plan_type', 'plan_value', 'value_status',
         'is_derived', 'derivation_method', 'raw_value', 'source_id', 'source_locator'],
        rows
    )
    return rows


def rebuild_exam_subjects():
    """重建 exam_subjects.csv"""
    rows = []
    
    for year in YEARS:
        year_dir = STAGING_DIR / year
        mapping = load_id_mapping(year)
        
        # 加载 exam_subjects
        es_file = year_dir / "exam_subjects.json"
        if not es_file.exists():
            continue
        
        es_data = load_json(es_file)
        subjects = es_data['data']
        
        for subject in subjects:
            major = subject['major_name_raw']
            
            # 查找 program_year_id（考试科目的 institution 为空）
            ids = get_ids_from_mapping(mapping, major, '文')  # 简化处理，用 '文'
            
            # 如果找不到，尝试 '理'
            if not ids:
                ids = get_ids_from_mapping(mapping, major, '理')
            
            # 如果还找不到，尝试 '艺术(文)'
            if not ids:
                ids = get_ids_from_mapping(mapping, major, '艺术(文)')
            
            # 如果还找不到，尝试 '体育(文)'
            if not ids:
                ids = get_ids_from_mapping(mapping, major, '体育(文)')
            
            if not ids:
                print(f"  警告: 找不到 {major} 的 program_year_id，跳过")
                continue
            
            program_year_id = ids['program_year_id']
            
            # 4 个考试科目
            subject_slots = [
                ('public_1', subject.get('public_subject_1', '')),
                ('public_2', subject.get('public_subject_2', '')),
                ('professional_1', subject.get('professional_subject_1', '')),
                ('professional_2', subject.get('professional_subject_2', ''))
            ]
            
            for slot, subject_name in subject_slots:
                if not subject_name:
                    continue
                
                # 生成 exam_subject_id
                exam_subject_id = f"EXAM-{program_year_id}-{slot}"
                
                rows.append({
                    'exam_subject_id': exam_subject_id,
                    'program_year_id': program_year_id,
                    'subject_slot': slot,
                    'subject_name_raw': subject_name,
                    'subject_name_std': subject_name,
                    'score_max': '150' if slot.startswith('public_') else '120',
                    'exam_duration': '',
                    'exam_method': '闭卷',
                    'source_id': f'SRC-{year}-ZC',
                    'source_locator': subject.get('source_locator', '')
                })
    
    write_csv(
        NORMALIZED_DIR / "exam_subjects.csv",
        ['exam_subject_id', 'program_year_id', 'subject_slot', 'subject_name_raw',
         'subject_name_std', 'score_max', 'exam_duration', 'exam_method',
         'source_id', 'source_locator'],
        rows
    )
    return rows


def rebuild_major_eligibility():
    """重建 major_eligibility.csv"""
    rows = []
    
    for year in YEARS:
        year_dir = STAGING_DIR / year
        mapping = load_id_mapping(year)
        
        # 加载 eligibility
        el_file = year_dir / "eligibility.json"
        if not el_file.exists():
            continue
        
        el_data = load_json(el_file)
        eligibilities = el_data['data']
        
        for elig in eligibilities:
            major = elig['undergraduate_major_std']
            
            # 查找 program_year_id
            ids = get_ids_from_mapping(mapping, major, '文')
            
            if not ids:
                ids = get_ids_from_mapping(mapping, major, '理')
            
            if not ids:
                ids = get_ids_from_mapping(mapping, major, '艺术(文)')
            
            if not ids:
                ids = get_ids_from_mapping(mapping, major, '体育(文)')
            
            if not ids:
                print(f"  警告: 找不到 {major} 的 program_year_id，跳过")
                continue
            
            program_year_id = ids['program_year_id']
            
            # 生成 eligibility_id
            eligibility_id = f"ELIG-{program_year_id}"
            
            rows.append({
                'eligibility_id': eligibility_id,
                'program_year_id': program_year_id,
                'undergraduate_major_raw': elig.get('undergraduate_major_raw', major),
                'undergraduate_major_std': major,
                'allowed_major_categories_raw': elig.get('allowed_major_categories_raw', ''),
                'allowed_major_categories_std': elig.get('allowed_major_categories_std', ''),
                'restriction_raw_text': elig.get('restriction_raw_text', ''),
                'source_id': f'SRC-{year}-ZC',
                'source_locator': elig.get('source_locator', '')
            })
    
    write_csv(
        NORMALIZED_DIR / "major_eligibility.csv",
        ['eligibility_id', 'program_year_id', 'undergraduate_major_raw',
         'undergraduate_major_std', 'allowed_major_categories_raw',
         'allowed_major_categories_std', 'restriction_raw_text',
         'source_id', 'source_locator'],
        rows
    )
    return rows


def rebuild_admission_scores():
    """重建 admission_scores.csv"""
    rows = []
    
    # 只处理有数据的年份
    for year in ['2024', '2025']:
        year_dir = STAGING_DIR / year
        mapping = load_id_mapping(year)
        
        # 加载 admission_scores
        as_file = year_dir / "admission_scores.json"
        if not as_file.exists():
            continue
        
        as_data = load_json(as_file)
        scores = as_data['data']
        
        for score in scores:
            major = score['major_name_raw']
            
            # 查找 offering_id
            ids = get_ids_from_mapping(mapping, major, '文')
            
            if not ids:
                ids = get_ids_from_mapping(mapping, major, '理')
            
            if not ids:
                ids = get_ids_from_mapping(mapping, major, '艺术(文)')
            
            if not ids:
                ids = get_ids_from_mapping(mapping, major, '体育(文)')
            
            if not ids:
                print(f"  警告: 找不到 {major} 的 offering_id，跳过")
                continue
            
            offering_id = ids['offering_id']
            
            # 4 个分数类型
            score_types = [
                ('normal', score.get('score_normal_raw', '')),
                ('retired_culture_exam_exempt', score.get('score_retired_culture_exam_exempt_raw', '')),
                ('retired_non_exempt', score.get('score_retired_non_exempt_raw', '')),
                ('registered_poor_family', score.get('score_registered_poor_family_raw', ''))
            ]
            
            for score_type, score_raw in score_types:
                if not score_raw:
                    continue
                
                # 解析分数（简化处理）
                # 格式可能是 "280" 或 "280/300"
                if '/' in score_raw:
                    parts = score_raw.split('/')
                    score_value_numeric = parts[0]
                    score_max = parts[1]
                else:
                    score_value_numeric = score_raw
                    score_max = ''
                
                # 生成 admission_score_id
                admission_score_id = f"SCORE-{offering_id}-{score_type}"
                
                rows.append({
                    'admission_score_id': admission_score_id,
                    'offering_id': offering_id,
                    'candidate_category': score_type,
                    'score_metric': '',
                    'score_basis': '',
                    'score_max': score_max,
                    'score_value_numeric': score_value_numeric,
                    'score_raw': score_raw,
                    'threshold_detail_json': '',
                    'assessment_name': '',
                    'source_id': f'SRC-{year}-LQ',
                    'source_locator': score.get('source_locator', '')
                })
    
    write_csv(
        NORMALIZED_DIR / "admission_scores.csv",
        ['admission_score_id', 'offering_id', 'candidate_category', 'score_metric',
         'score_basis', 'score_max', 'score_value_numeric', 'score_raw',
         'threshold_detail_json', 'assessment_name', 'source_id', 'source_locator'],
        rows
    )
    return rows


def main():
    """主函数"""
    print("=" * 70)
    print("从 staging JSON 重建 normalized CSV")
    print("=" * 70)
    print()
    
    # 确保输出目录存在
    NORMALIZED_DIR.mkdir(parents=True, exist_ok=True)
    
    # 重建各个表
    print("重建 program_years.csv...")
    program_years = rebuild_program_years()
    
    print("\n重建 program_offerings.csv...")
    program_offerings = rebuild_program_offerings()
    
    print("\n重建 enrollment_plans.csv...")
    enrollment_plans = rebuild_enrollment_plans()
    
    print("\n重建 exam_subjects.csv...")
    exam_subjects = rebuild_exam_subjects()
    
    print("\n重建 major_eligibility.csv...")
    major_eligibility = rebuild_major_eligibility()
    
    print("\n重建 admission_scores.csv...")
    admission_scores = rebuild_admission_scores()
    
    # 统计信息
    print("\n" + "=" * 70)
    print("重建完成！统计信息：")
    print(f"  program_years: {len(program_years)} 行")
    print(f"  program_offerings: {len(program_offerings)} 行")
    print(f"  enrollment_plans: {len(enrollment_plans)} 行")
    print(f"  exam_subjects: {len(exam_subjects)} 行")
    print(f"  major_eligibility: {len(major_eligibility)} 行")
    print(f"  admission_scores: {len(admission_scores)} 行")
    
    # 按年份统计
    print("\n按年份统计：")
    for year in YEARS:
        py_count = len([r for r in program_years if r['year'] == year])
        po_count = len([r for r in program_offerings if r['year'] == year])
        ep_count = len([r for r in enrollment_plans if r['source_id'].endswith(f'-{year}-ZC')])
        es_count = len([r for r in exam_subjects if r['source_id'].endswith(f'-{year}-ZC')])
        me_count = len([r for r in major_eligibility if r['source_id'].endswith(f'-{year}-ZC')])
        print(f"  {year}: program_years={py_count}, program_offerings={po_count}, "
              f"enrollment_plans={ep_count}, exam_subjects={es_count}, "
              f"major_eligibility={me_count}")
    
    print("=" * 70)


if __name__ == '__main__':
    main()
