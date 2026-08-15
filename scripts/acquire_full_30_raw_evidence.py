#!/usr/bin/env python3
"""Acquire one five-school checkpoint of official 2024-2026 Anhui ZSB evidence.

Search engines are discovery-only. Formal evidence is saved only from each school's
official-domain allowlist. Candidate-level personal data is excluded.
"""
from __future__ import annotations

import csv
import hashlib
import html
import json
import os
import re
import time
import zipfile
from collections import defaultdict, deque
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote_plus, unquote, urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

GROUP = int(os.environ.get("ACQ_GROUP", "1"))
if GROUP not in range(1, 7):
    raise SystemExit("ACQ_GROUP must be 1..6")

OUT = Path(os.environ.get("ACQ_OUT", "acquisition_output"))
EVIDENCE = OUT / "anhui_zsb_data" / "evidence" / "full_raw_30_schools"
REPORTS = OUT / "reports"
EVIDENCE.mkdir(parents=True, exist_ok=True)
REPORTS.mkdir(parents=True, exist_ok=True)

YEARS = (2024, 2025, 2026)
TOPICS = [
    "admission_policy", "enrollment_plan", "major_catalog", "training_location",
    "tuition_and_duration", "eligibility", "exam_subjects", "exam_syllabus",
    "reference_books", "exam_schedule", "exam_location", "admission_rules",
    "score_formula", "control_line", "admission_min_score", "admission_max_score",
    "admission_average_score", "application_statistics", "qualified_statistics",
    "admitted_statistics", "registered_statistics", "plan_adjustment", "adjustment",
    "exemption", "retired_soldier", "registered_poor_family", "skill_competition",
    "other_official_notice",
]
VALID_STATUS = {
    "collected", "official_not_published", "not_found", "not_applicable",
    "removed_or_unavailable", "access_restricted", "manual_download_required",
    "candidate_personal_data_excluded", "awaiting_manual_review",
}

SCHOOLS = [
    ("HFNU","合肥师范学院",["hfnu.edu.cn"],["https://zsb.hfnu.edu.cn/","https://zsb.hfnu.edu.cn/zsxx1/zszc.htm"]),
    ("AHUA","安徽艺术学院",["ahua.edu.cn"],["https://www.ahua.edu.cn/zsw/","https://www.ahua.edu.cn/zsw/zsxx/list.htm"]),
    ("AHSTU","安徽科技学院",["ahstu.edu.cn"],["https://www.ahstu.edu.cn/zsc/"]),
    ("CHZU","滁州学院",["chzu.edu.cn"],["https://zsw.chzu.edu.cn/"]),
    ("CZU","池州学院",["czu.edu.cn"],["https://zs.czu.edu.cn/","https://xinxgk.czu.edu.cn/xxgkml/zsksxx/zszcjzsjh.htm"]),
    ("AHAU","安徽农业大学",["ahau.edu.cn"],["https://zsb.ahau.edu.cn/","https://www.ahau.edu.cn/"]),
    ("AHMU","安徽医科大学",["ahmu.edu.cn"],["https://zs.ahmu.edu.cn/","https://www.ahmu.edu.cn/"]),
    ("AHTCM","安徽中医药大学",["ahtcm.edu.cn"],["https://bkzs.ahtcm.edu.cn/","https://bkzs.ahtcm.edu.cn/zszn/zszc.htm"]),
    ("BBMU","蚌埠医科大学",["bbmu.edu.cn"],["https://zsw.bbmu.edu.cn/","https://zsw.bbmu.edu.cn/info/1006/3342.htm"]),
    ("FYNU","阜阳师范大学",["fynu.edu.cn"],["https://www.fynu.edu.cn/bkzsxxw/","https://www.fynu.edu.cn/bkzsxxw/zsxx/zszc.htm"]),
    ("AQNU","安庆师范大学",["aqnu.edu.cn"],["https://zsw.aqnu.edu.cn/","https://zsw.aqnu.edu.cn/zsxx/zszc.htm"]),
    ("WNMC","皖南医学院",["wnmc.edu.cn"],["https://zsb.wnmc.edu.cn/","https://www.wnmc.edu.cn/"]),
    ("WXC","皖西学院",["wxc.edu.cn"],["https://zsb.wxc.edu.cn/","https://www.wxc.edu.cn/"]),
    ("BZU","亳州学院",["bzuu.edu.cn"],["https://www.bzuu.edu.cn/","https://www.bzuu.edu.cn/zzzs/"]),
    ("CHU","巢湖学院",["chu.edu.cn"],["https://www.chu.edu.cn/zsw/","https://www.chu.edu.cn/"]),
    ("HSU","黄山学院",["hsu.edu.cn"],["https://zsb.hsu.edu.cn/","https://zsb.hsu.edu.cn/32/37/c1172a209463/page.htm"]),
    ("AHSZU","宿州学院",["ahszu.edu.cn"],["https://www.ahszu.edu.cn/zs/","https://www.ahszu.edu.cn/zs/zhuansb.htm"]),
    ("HFUU","合肥大学",["hfuu.edu.cn"],["https://www.hfuu.edu.cn/zs/","https://www.hfuu.edu.cn/zs/5d/08/c12151a154888/page.htm"]),
    ("BBC","蚌埠学院",["bbc.edu.cn"],["https://zhaoban.bbc.edu.cn/","https://zhaoban.bbc.edu.cn/1269/list.htm"]),
    ("AHUT","安徽工业大学",["ahut.edu.cn"],["https://zs.ahut.edu.cn/","https://www.ahut.edu.cn/"]),
    ("AUFE","安徽财经大学",["aufe.edu.cn"],["https://zsjy.aufe.edu.cn/","https://www.aufe.edu.cn/"]),
    ("AHNU","安徽师范大学",["ahnu.edu.cn"],["https://zsxx.ahnu.edu.cn/","https://www.ahnu.edu.cn/"]),
    ("TLU","铜陵学院",["tlu.edu.cn"],["https://zsb.tlu.edu.cn/"]),
    ("AHYZ","安徽第二医学院",["ahyz.edu.cn"],["https://zsw.ahyz.edu.cn/","https://www.ahyz.edu.cn/"]),
    ("HNNU","淮南师范学院",["hnnu.edu.cn"],["https://zsb.hnnu.edu.cn/","https://www.hnnu.edu.cn/"]),
    ("AHJZU","安徽建筑大学",["ahjzu.edu.cn"],["https://www.ahjzu.edu.cn/zsw/","https://www.ahjzu.edu.cn/"]),
    ("AXHU","安徽新华学院",["axhu.edu.cn"],["https://zhaosheng.axhu.edu.cn/","https://zhaosheng.axhu.edu.cn/contents/2685/261780.html"]),
    ("SLU","安徽三联学院",["slu.edu.cn"],["https://zsb.slu.edu.cn/","https://zsb.slu.edu.cn/2026/0312/c462a56211/page.htm"]),
    ("AISU","安徽外国语学院",["aisu.edu.cn"],["https://www.aisu.edu.cn/zsb/","https://www.aisu.edu.cn/zsb/info/1097/5199.htm"]),
    ("UWH","芜湖学院",["uwh.edu.cn"],["https://www.uwh.edu.cn/zsw/","https://www.uwh.edu.cn/"]),
]
assert len(SCHOOLS) == 30
SCHOOLS = SCHOOLS[(GROUP-1)*5:GROUP*5]

TOPIC_KW = {
    "admission_policy":["招生章程","招生简章"], "enrollment_plan":["招生计划","拟招生方案"],
    "major_catalog":["招生专业","专业招生范围"], "training_location":["联合培养","培养地点","培养校区"],
    "tuition_and_duration":["学费","学制"], "eligibility":["报名条件","报考范围","资格条件"],
    "exam_subjects":["考试科目","专业课","公共课"], "exam_syllabus":["考试大纲","测试大纲","考查大纲"],
    "reference_books":["参考书目","参考教材"], "exam_schedule":["考试时间","考试安排"],
    "exam_location":["考试地点","考点","考场"], "admission_rules":["录取规则","录取细则","同分排序"],
    "score_formula":["计分公式","综合成绩","总成绩"], "control_line":["合格线","控制线","专业课合格"],
    "admission_min_score":["最低录取分","最低投档分","录取分数线","预录取分数线"],
    "admission_max_score":["最高录取分","录取最高分"], "admission_average_score":["平均录取分","录取平均分"],
    "application_statistics":["报考人数","报名人数","报考志愿数"], "qualified_statistics":["资格审核通过人数","资格通过人数"],
    "admitted_statistics":["录取人数","录取统计"], "registered_statistics":["报到人数","注册人数"],
    "plan_adjustment":["计划调整","调整计划","扩招","缩招"], "adjustment":["调剂","补录","征集志愿"],
    "exemption":["免试","免文化课"], "retired_soldier":["退役大学生士兵","退役士兵"],
    "registered_poor_family":["建档立卡"], "skill_competition":["技能大赛","职业技能大赛"],
    "other_official_notice":["专升本"],
}
PRIVACY = ["拟录取名单","预录取名单","录取名单","考生名单","面试名单","审核名单","免试名单","成绩名单","成绩查询","录取查询","考生号","准考证号","身份证号"]
RELEVANT = ["专升本","招生章程","招生计划","考试大纲","参考书","专业课","录取分数","最低分","最高分","平均分","合格线","控制线","调剂","计划调整","报考人数","录取人数","报到人数","退役士兵","建档立卡","技能大赛"]
FILE_EXTS = {".pdf",".doc",".docx",".xls",".xlsx",".csv",".jpg",".jpeg",".png",".tif",".tiff"}
MAX_PAGES = int(os.environ.get("MAX_PAGES_PER_SCHOOL_YEAR", "40"))
MAX_FILE = 100*1024*1024
DELAY = float(os.environ.get("ACQ_DELAY", "0.30"))

session = requests.Session()
retry = Retry(total=3, connect=3, read=3, backoff_factor=.8, status_forcelist=[429,500,502,503,504], allowed_methods=["GET"])
session.mount("https://", HTTPAdapter(max_retries=retry)); session.mount("http://", HTTPAdapter(max_retries=retry))
session.headers.update({"User-Agent":"Mozilla/5.0 (compatible; AnhuiZSBDataResearch/1.0)","Accept":"*/*"})

sources=[]; assets=[]; failures=[]; privacy=[]; discovery=[]; coverage={}

def now(): return datetime.now(timezone.utc).isoformat()
def sha(b): return hashlib.sha256(b).hexdigest()
def short(s): return hashlib.sha1(s.encode("utf-8","replace")).hexdigest()[:10]
def allowed(url, domains):
    h=(urlparse(url).hostname or "").lower()
    return any(h==d or h.endswith("."+d) for d in domains)
def privacy_hit(s):
    t=re.sub(r"\s+","",s or "")
    return next((k for k in PRIVACY if k in t), None)
def topics(text):
    t=re.sub(r"\s+","",text or "")
    out=[k for k,v in TOPIC_KW.items() if any(x in t for x in v)]
    return out or (["other_official_notice"] if "专升本" in t else [])
def ptopic(ts):
    for t in TOPICS:
        if t in ts and t!="other_official_notice": return t
    return "other_official_notice"
def subdir(t):
    if t=="admission_policy": return "admission_policy"
    if t in {"enrollment_plan","major_catalog","training_location","tuition_and_duration","eligibility"}: return "enrollment_plan"
    if t in {"exam_subjects","exam_syllabus","reference_books","exam_schedule","exam_location"}: return "exam_syllabus"
    if t in {"admission_rules","score_formula","control_line","admission_min_score","admission_max_score","admission_average_score"}: return "admission_scores"
    if t in {"application_statistics","qualified_statistics","admitted_statistics","registered_statistics"}: return "statistics"
    if t in {"plan_adjustment","adjustment"}: return "adjustments"
    return "other"
def clean(u): return html.unescape(u).split("#",1)[0].strip()
def safe_name(s): return re.sub(r'[\\/:*?"<>|\x00-\x1f]','_',s or "download")[:180]

def get(url, stream=False):
    try:
        r=session.get(url,timeout=35,allow_redirects=True,stream=stream)
        meta={"status":r.status_code,"final_url":r.url,"content_type":r.headers.get("Content-Type",""),"content_disposition":r.headers.get("Content-Disposition",""),"content_length":r.headers.get("Content-Length","")}
        if r.status_code>=400: return None,meta
        if stream:
            declared=int(r.headers.get("Content-Length","0") or 0)
            if declared>MAX_FILE:
                h=hashlib.sha256(); n=0
                for c in r.iter_content(1024*1024): h.update(c); n+=len(c)
                meta.update({"too_large":True,"size":n,"sha256":h.hexdigest()}); return None,meta
            b=r.content
        else: b=r.content
        meta.update({"size":len(b),"sha256":sha(b)})
        return b,meta
    except Exception as e: return None,{"status":"error","final_url":url,"error":repr(e)}

def ext_for(url, meta, body):
    e=Path(urlparse(meta.get("final_url") or url).path).suffix.lower()
    if e in FILE_EXTS: return e
    cd=meta.get("content_disposition",""); m=re.search(r"filename\*?=(?:UTF-8''|\")?([^\";]+)",cd,re.I)
    if m:
        e=Path(unquote(m.group(1))).suffix.lower()
        if e in FILE_EXTS: return e
    ct=meta.get("content_type","").lower().split(";",1)[0]
    mp={"application/pdf":".pdf","application/msword":".doc","application/vnd.openxmlformats-officedocument.wordprocessingml.document":".docx","application/vnd.ms-excel":".xls","application/vnd.openxmlformats-officedocument.spreadsheetml.sheet":".xlsx","text/csv":".csv","image/jpeg":".jpg","image/png":".png","image/tiff":".tif"}
    if ct in mp: return mp[ct]
    if body and body.startswith(b"%PDF-"): return ".pdf"
    if body and body.startswith(b"\xff\xd8\xff"): return ".jpg"
    if body and body.startswith(b"\x89PNG"): return ".png"
    return ""

def orig_name(url, meta):
    cd=meta.get("content_disposition",""); m=re.search(r"filename\*?=(?:UTF-8''|\")?([^\";]+)",cd,re.I)
    if m: return safe_name(unquote(m.group(1)))
    return safe_name(Path(urlparse(meta.get("final_url") or url).path).name)

def fail_status(meta):
    s=meta.get("status")
    if s==403: return "access_restricted"
    if s in (404,410): return "removed_or_unavailable"
    return "access_restricted"

def bing(school, year):
    sid,name,domains,roots=school; found=[]
    qs=[f'site:{domains[0]} "{name}" {year} 专升本',f'site:{domains[0]} "{name}" {year} 专升本 考试大纲 参考书 录取分数线 调剂 招生计划']
    for q in qs:
        u="https://www.bing.com/search?q="+quote_plus(q)+"&count=30&setlang=zh-hans"
        b,m=get(u); rec={"school_id":sid,"year":year,"query":q,"status":m.get("status"),"error":m.get("error","")}
        if b:
            s=BeautifulSoup(b,"html.parser"); n=0
            for a in s.select("li.b_algo h2 a[href], a[href]"):
                href=clean(a.get("href","")); label=a.get_text(" ",strip=True)
                if href.startswith("http") and allowed(href,domains) and not privacy_hit(label+href): found.append((href,label)); n+=1
            raw=html.unescape(b.decode("utf-8","ignore"))
            for d in domains:
                for mm in re.finditer(r'https?://[^\"\'<>\s]*'+re.escape(d)+r'[^\"\'<>\s]*',raw,re.I):
                    href=clean(unquote(mm.group(0)).rstrip(".,;"))
                    if allowed(href,domains) and not privacy_hit(href): found.append((href,"bing-direct"))
            rec["official_urls_found"]=n
        discovery.append(rec); time.sleep(.35)
    out=[]; seen=set()
    for x in found:
        if x[0] not in seen: seen.add(x[0]); out.append(x)
    return out

def relevant(url,label,year):
    x=unquote(url)+" "+(label or "")
    if privacy_hit(x): return False
    if Path(urlparse(url).path).suffix.lower() in FILE_EXTS: return True
    if any(k in x for k in RELEVANT): return True
    if str(year) in x and any(k in x for k in ["招生","考试","录取","计划","章程"]): return True
    return bool(re.search(r"/(zsb|zs|zsw|bkzs|zhaosheng|zhaoban|zsxx|zhuansb|zszc|tzgg|zsdt)(/|\.|$)",urlparse(url).path,re.I))

def save_asset(school,year,parent_url,parent_id,url,label,base):
    sid,name,domains,_=school
    if privacy_hit(label+url):
        privacy.append({"school_id":sid,"school_name":name,"year":year,"url":url,"reason":privacy_hit(label+url),"status":"candidate_personal_data_excluded"}); return
    b,m=get(url,stream=True); time.sleep(DELAY)
    if b is None:
        st="awaiting_manual_review" if m.get("too_large") else fail_status(m)
        failures.append({"school_id":sid,"school_name":name,"year":year,"url":url,"parent_url":parent_url,"status":st,"http_status":m.get("status"),"reason":"file >100MB" if m.get("too_large") else m.get("error","")}); return
    e=ext_for(url,m,b)
    if e not in FILE_EXTS: return
    orig=orig_name(url,m); hit=privacy_hit(label+orig+url)
    if hit:
        privacy.append({"school_id":sid,"school_name":name,"year":year,"url":url,"reason":hit,"status":"candidate_personal_data_excluded"}); return
    ts=topics(label+" "+orig); pt=ptopic(ts); aid=f"AST-{sid}-{year}-{short(m.get('final_url') or url)}"; stored=f"DOC-{sid}-{year}-{pt}-{short(m.get('final_url') or url)}{e}"
    dest=base/subdir(pt)/stored; dest.parent.mkdir(parents=True,exist_ok=True)
    if not dest.exists(): dest.write_bytes(b)
    assets.append({"asset_id":aid,"source_id":parent_id,"school_id":sid,"school_name":name,"year":year,"asset_type":e[1:],"local_path":str(dest.relative_to(OUT)),"original_file_name":orig,"stored_file_name":stored,"file_extension":e,"mime_type":m.get("content_type",""),"file_size":len(b),"sha256":sha(b),"retrieval_url":m.get("final_url") or url,"retrieved_at":now(),"parent_asset_id":"","parser_name":"","parser_version":"","generated_at":"","privacy_classification":"public_aggregate_or_policy","duplicate_group":"","status":"collected","notes":"parent="+parent_url})
    for t in ts: coverage[(sid,year,t)]="collected"

def crawl(school,year):
    sid,name,domains,roots=school; base=EVIDENCE/sid/str(year)
    for d in ["admission_policy","enrollment_plan","exam_syllabus","admission_scores","statistics","adjustments","other"]: (base/d).mkdir(parents=True,exist_ok=True)
    seeds=[(u,"configured-root",0) for u in roots]+[(u,a,0) for u,a in bing(school,year)]
    q=deque(); enq=set()
    for x in seeds:
        if allowed(x[0],domains) and x[0] not in enq: q.append(x); enq.add(x[0])
    seen=set(); saved=0
    while q and len(seen)<MAX_PAGES:
        url,label,depth=q.popleft()
        if url in seen or not allowed(url,domains): continue
        seen.add(url)
        if privacy_hit(label+url): privacy.append({"school_id":sid,"school_name":name,"year":year,"url":url,"reason":privacy_hit(label+url),"status":"candidate_personal_data_excluded"}); continue
        if Path(urlparse(url).path).suffix.lower() in FILE_EXTS:
            save_asset(school,year,"","",url,label,base); continue
        b,m=get(url); time.sleep(DELAY)
        if b is None:
            failures.append({"school_id":sid,"school_name":name,"year":year,"url":url,"parent_url":"","status":fail_status(m),"http_status":m.get("status"),"reason":m.get("error","")}); continue
        ct=m.get("content_type","").lower(); e=ext_for(url,m,b)
        if e in FILE_EXTS and "html" not in ct:
            save_asset(school,year,"","",url,label,base); continue
        try: soup=BeautifulSoup(b,"html.parser")
        except Exception: continue
        title=soup.title.get_text(" ",strip=True) if soup.title else ""
        hit=privacy_hit(title+label)
        text=soup.get_text("\n",strip=True)
        if not hit and re.search(r"(姓名.{0,20}(考生号|准考证号)|考生号.{0,20}姓名)",text,re.S) and len(re.findall(r"\b\d{10,18}\b",text))>=2: hit="candidate-record-pattern"
        if hit:
            privacy.append({"school_id":sid,"school_name":name,"year":year,"url":m.get("final_url") or url,"reason":hit,"status":"candidate_personal_data_excluded"}); continue
        final=clean(m.get("final_url") or url); blob=title+"\n"+text[:100000]
        if "专升本" in blob and (str(year) in blob or str(year) in final):
            ts=topics(blob); pt=ptopic(ts); srcid=f"SRC-{sid}-{year}-{short(final)}"; dest=base/subdir(pt)/f"DOC-{sid}-{year}-{pt}-{short(final)}.html"; dest.write_bytes(b)
            parsed=dest.with_name(dest.stem+"_parsed.txt"); parsed.write_text(text,encoding="utf-8")
            sources.append({"school_id":sid,"school_name":name,"year":year,"source_id":srcid,"document_type":"html","topics":"|".join(ts),"title":title,"official_url":url,"final_url":final,"parent_page_url":"","publish_date":"","retrieved_at":now(),"official_domain":urlparse(final).hostname or "","source_level":"school_official","http_status":m.get("status"),"content_type":m.get("content_type",""),"status":"collected","notes":"","local_path":str(dest.relative_to(OUT)),"sha256":sha(b),"file_size":len(b)})
            assets.append({"asset_id":f"AST-{sid}-{year}-{short(str(parsed))}","source_id":srcid,"school_id":sid,"school_name":name,"year":year,"asset_type":"parsed_text","local_path":str(parsed.relative_to(OUT)),"original_file_name":"","stored_file_name":parsed.name,"file_extension":".txt","mime_type":"text/plain","file_size":parsed.stat().st_size,"sha256":sha(parsed.read_bytes()),"retrieval_url":final,"retrieved_at":now(),"parent_asset_id":"","parser_name":"BeautifulSoup","parser_version":"bs4","generated_at":now(),"privacy_classification":"public_aggregate_or_policy","duplicate_group":"","status":"collected","notes":"derived parsed text"})
            for t in ts: coverage[(sid,year,t)]="collected"
            saved+=1
        parent_id=f"SRC-{sid}-{year}-{short(final)}"
        for tag in soup.find_all(["a","iframe","embed","object"]):
            href=tag.get("href") or tag.get("src") or tag.get("data")
            if not href: continue
            u=clean(urljoin(final,href)); lab=tag.get_text(" ",strip=True)[:250]
            if not allowed(u,domains): continue
            h=privacy_hit(lab+u)
            if h:
                privacy.append({"school_id":sid,"school_name":name,"year":year,"url":u,"reason":h,"status":"candidate_personal_data_excluded"}); continue
            if not relevant(u,lab,year): continue
            if Path(urlparse(u).path).suffix.lower() in FILE_EXTS or re.search(r"download|_upload|system/_content",u,re.I): save_asset(school,year,final,parent_id,u,lab,base)
            elif depth<2 and u not in enq: q.append((u,lab,depth+1)); enq.add(u)
    for t in TOPICS: coverage.setdefault((sid,year,t),"not_found")
    print(f"{sid} {year}: seen={len(seen)} saved_html={saved}")

def write_csv(path,rows,fields):
    with path.open("w",encoding="utf-8-sig",newline="") as f:
        w=csv.DictWriter(f,fieldnames=fields,extrasaction="ignore"); w.writeheader(); w.writerows(rows)

def finish():
    def uniq(rows,key):
        out=[]; seen=set()
        for r in rows:
            k=key(r)
            if k not in seen: seen.add(k); out.append(r)
        return out
    ss=uniq(sources,lambda r:(r["school_id"],r["year"],r["final_url"],r["sha256"])); aa=uniq(assets,lambda r:(r["school_id"],r["year"],r["retrieval_url"],r["sha256"],r["asset_type"])); ff=uniq(failures,lambda r:(r["school_id"],r["year"],r["url"],r["status"])); pp=uniq(privacy,lambda r:(r["school_id"],r["year"],r["url"],r["reason"]))
    groups=defaultdict(list)
    for a in aa:
        if a["asset_type"]!="parsed_text" and a.get("sha256"): groups[a["sha256"]].append(a)
    di=0
    for rows in groups.values():
        if len(rows)>1:
            di+=1; gid=f"DUP-G{GROUP}-{di:04d}"
            for a in rows:a["duplicate_group"]=gid
    cov=[]
    for sid,name,_,_ in SCHOOLS:
        for y in YEARS:
            for t in TOPICS:
                st=coverage[(sid,y,t)]; assert st in VALID_STATUS; cov.append({"school_id":sid,"school_name":name,"year":y,"topic":t,"status":st})
    for sid,name,domains,roots in SCHOOLS:
        d=EVIDENCE/sid; d.mkdir(parents=True,exist_ok=True); srows=[r for r in ss if r["school_id"]==sid]; arows=[r for r in aa if r["school_id"]==sid]; frows=[r for r in ff if r["school_id"]==sid]
        (d/"school_manifest.json").write_text(json.dumps({"school_id":sid,"school_name":name,"official_domains":domains,"sources":srows,"assets":arows,"failures":frows,"generated_at":now()},ensure_ascii=False,indent=2),encoding="utf-8")
        write_csv(d/"school_coverage.csv",[r for r in cov if r["school_id"]==sid],["school_id","school_name","year","topic","status"])
        (d/"school_notes.md").write_text(f"# {name} ({sid})\n\n- Official domains: {', '.join(domains)}\n- Sources: {len(srows)}\n- Assets: {len(arows)}\n- Failures: {len(frows)}\n",encoding="utf-8")
        with zipfile.ZipFile(EVIDENCE/f"{sid}_official_raw_2024_2026.zip","w",zipfile.ZIP_DEFLATED,allowZip64=True) as z:
            for p in d.rglob("*"):
                if p.is_file(): z.write(p,p.relative_to(EVIDENCE))
    result={"group":GROUP,"schools":[{"school_id":s[0],"school_name":s[1],"domains":s[2]} for s in SCHOOLS],"sources":ss,"assets":aa,"failures":ff,"privacy":pp,"coverage":cov,"discovery":discovery,"generated_at":now()}
    (REPORTS/f"group_{GROUP}_result.json").write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps({"group":GROUP,"schools":len(SCHOOLS),"sources":len(ss),"assets":len(aa),"failures":len(ff),"privacy_exclusions":len(pp)},ensure_ascii=False))

for school in SCHOOLS:
    for year in YEARS:
        try: crawl(school,year)
        except Exception as e:
            sid,name,_,_=school; failures.append({"school_id":sid,"school_name":name,"year":year,"url":"","parent_url":"","status":"access_restricted","http_status":"exception","reason":repr(e)})
            for t in TOPICS: coverage.setdefault((sid,year,t),"not_found")
finish()
