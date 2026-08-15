#!/usr/bin/env python3
"""Sanitize one acquisition checkpoint before artifact upload.

Fixes cross-year contamination caused by multi-year index pages, removes decorative
images, rebuilds manifests/coverage, and leaves only privacy-safe official evidence.
"""
from __future__ import annotations
import csv, json, os, re, zipfile
from pathlib import Path
from collections import defaultdict

GROUP=int(os.environ.get('ACQ_GROUP','1'))
ROOT=Path(os.environ.get('ACQ_OUT','acquisition_output'))
REP=ROOT/'reports'
EVID=ROOT/'anhui_zsb_data'/'evidence'/'full_raw_30_schools'
J=REP/f'group_{GROUP}_result.json'
r=json.loads(J.read_text(encoding='utf-8'))

YEARS={2024,2025,2026}
TOPICS=["admission_policy","enrollment_plan","major_catalog","training_location","tuition_and_duration","eligibility","exam_subjects","exam_syllabus","reference_books","exam_schedule","exam_location","admission_rules","score_formula","control_line","admission_min_score","admission_max_score","admission_average_score","application_statistics","qualified_statistics","admitted_statistics","registered_statistics","plan_adjustment","adjustment","exemption","retired_soldier","registered_poor_family","skill_competition","other_official_notice"]
KW={
"admission_policy":["招生章程","招生简章"],"enrollment_plan":["招生计划","拟招生方案"],"major_catalog":["招生专业","专业招生范围"],"training_location":["联合培养","培养地点","培养校区"],"tuition_and_duration":["学费","学制"],"eligibility":["报名条件","报考范围","资格条件"],"exam_subjects":["考试科目","专业课","公共课"],"exam_syllabus":["考试大纲","测试大纲","考查大纲"],"reference_books":["参考书目","参考教材"],"exam_schedule":["考试时间","考试安排"],"exam_location":["考试地点","考点","考场"],"admission_rules":["录取规则","录取细则","同分排序"],"score_formula":["计分公式","综合成绩","总成绩"],"control_line":["合格线","控制线","专业课合格"],"admission_min_score":["最低录取分","最低投档分","录取分数线","预录取分数线"],"admission_max_score":["最高录取分","录取最高分"],"admission_average_score":["平均录取分","录取平均分"],"application_statistics":["报考人数","报名人数","报考志愿数"],"qualified_statistics":["资格审核通过人数","资格通过人数"],"admitted_statistics":["录取人数","录取统计"],"registered_statistics":["报到人数","注册人数"],"plan_adjustment":["计划调整","调整计划","扩招","缩招"],"adjustment":["调剂","补录","征集志愿"],"exemption":["免试","免文化课"],"retired_soldier":["退役大学生士兵","退役士兵"],"registered_poor_family":["建档立卡"],"skill_competition":["技能大赛","职业技能大赛"],"other_official_notice":["专升本"]}
PRIV=["拟录取名单","预录取名单","录取名单","考生名单","面试名单","审核名单","免试名单","成绩名单","成绩查询","录取查询","考生号","准考证号","身份证号"]
IMG={'jpg','jpeg','png','tif','tiff'}
FACT_IMG=["专升本","招生","计划","分数","大纲","政策","章程","考试","录取","参考书","教材","调剂","人数"]

def years(text): return {int(x) for x in re.findall(r'(?<!\d)(202[456])(?!\d)',text or '')}
def context_source(x): return f"{x.get('title','')} {x.get('final_url','')}"
def context_asset(x): return ' '.join(str(x.get(k,'')) for k in ('original_file_name','retrieval_url','notes'))
def classify(text):
    t=re.sub(r'\s+','',text or '')
    out=[k for k,v in KW.items() if any(q in t for q in v)]
    return out or (["other_official_notice"] if '专升本' in t else [])
def remove_path(rel):
    if not rel: return
    p=ROOT/rel
    try:
        if p.is_file(): p.unlink()
    except OSError: pass

def source_keep(x):
    y=int(x['year']); ys=years(context_source(x))
    # If title/URL explicitly names a different year, this is cross-year contamination.
    return not ys or y in ys

sources=[]; dropped_sources=[]
for x in r.get('sources',[]):
    if source_keep(x): sources.append(x)
    else: dropped_sources.append(x); remove_path(x.get('local_path',''))
valid_source_ids={x['source_id'] for x in sources}
dropped_ids={x['source_id'] for x in dropped_sources}

assets=[]; dropped_assets=[]
for x in r.get('assets',[]):
    y=int(x['year']); ctx=context_asset(x); ys=years(ctx)
    drop=False
    if x.get('source_id') in dropped_ids: drop=True
    if ys and y not in ys: drop=True
    # Decorative/random images are not raw admission facts under the user's evidence policy.
    if str(x.get('asset_type','')).lower() in IMG and not any(k in ctx for k in FACT_IMG): drop=True
    # Never retain anything that slipped through the candidate-personal-data title guard.
    if any(k in ctx for k in PRIV): drop=True
    if drop: dropped_assets.append(x); remove_path(x.get('local_path',''))
    else: assets.append(x)

# For generic multi-year list pages, keep the raw page but do not let its entire list
# falsely satisfy year-specific topic coverage. Explicit-year sources can satisfy topics.
coverage={}
for s in r.get('schools',[]):
    sid=s['school_id']
    for y in YEARS:
        for t in TOPICS: coverage[(sid,y,t)]='not_found'
for s in sources:
    sid=s['school_id']; y=int(s['year']); ys=years(context_source(s))
    if ys and y in ys:
        for t in (s.get('topics','').split('|') if s.get('topics') else []):
            if t in TOPICS: coverage[(sid,y,t)]='collected'
    else:
        coverage[(sid,y,'other_official_notice')]='collected'
# Assets only satisfy year-specific topics when year is explicit in filename/URL/parent;
# otherwise inherit an explicit valid parent source if available.
source_by_id={s['source_id']:s for s in sources}
for a in assets:
    if a.get('asset_type')=='parsed_text': continue
    sid=a['school_id']; y=int(a['year']); ctx=context_asset(a); ys=years(ctx)
    usable=bool(ys and y in ys)
    if not usable:
        p=source_by_id.get(a.get('source_id'))
        if p:
            pys=years(context_source(p)); usable=bool(pys and y in pys)
    if usable:
        for t in classify(ctx): coverage[(sid,y,t)]='collected'

# Preserve meaningful failure states in empty topic grids only as not_found; failures stay in failure report.
coverage_rows=[]
for s in r.get('schools',[]):
    sid=s['school_id']; name=s['school_name']
    for y in (2024,2025,2026):
        for t in TOPICS: coverage_rows.append({'school_id':sid,'school_name':name,'year':y,'topic':t,'status':coverage[(sid,y,t)]})

r['sources']=sources; r['assets']=assets; r['coverage']=coverage_rows
r['sanitizer']={'version':'2','dropped_cross_year_or_unsafe_sources':len(dropped_sources),'dropped_cross_year_or_decorative_or_unsafe_assets':len(dropped_assets),'year_binding':'explicit title/url/parent context required for topic coverage'}
J.write_text(json.dumps(r,ensure_ascii=False,indent=2),encoding='utf-8')

# Rebuild school-level manifests, coverage, notes and ZIP after pruning.
def write_csv(path,rows,fields):
    with path.open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore'); w.writeheader(); w.writerows(rows)
for s in r.get('schools',[]):
    sid=s['school_id']; name=s['school_name']; d=EVID/sid; d.mkdir(parents=True,exist_ok=True)
    ss=[x for x in sources if x['school_id']==sid]; aa=[x for x in assets if x['school_id']==sid]; ff=[x for x in r.get('failures',[]) if x.get('school_id')==sid]; cc=[x for x in coverage_rows if x['school_id']==sid]
    (d/'school_manifest.json').write_text(json.dumps({'school_id':sid,'school_name':name,'official_domains':s.get('domains',[]),'sources':ss,'assets':aa,'failures':ff,'sanitized':True},ensure_ascii=False,indent=2),encoding='utf-8')
    write_csv(d/'school_coverage.csv',cc,['school_id','school_name','year','topic','status'])
    (d/'school_notes.md').write_text(f"# {name} ({sid})\n\n- Sources after sanitization: {len(ss)}\n- Assets after sanitization: {len(aa)}\n- Cross-year/decorative evidence was removed before artifact upload.\n",encoding='utf-8')
    zp=EVID/f'{sid}_official_raw_2024_2026.zip'
    if zp.exists(): zp.unlink()
    with zipfile.ZipFile(zp,'w',zipfile.ZIP_DEFLATED,allowZip64=True) as z:
        for p in d.rglob('*'):
            if p.is_file(): z.write(p,p.relative_to(EVID))

print(json.dumps({'group':GROUP,'sources_after':len(sources),'assets_after':len(assets),'dropped_sources':len(dropped_sources),'dropped_assets':len(dropped_assets),'privacy_exclusions':len(r.get('privacy',[]))},ensure_ascii=False))
