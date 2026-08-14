#!/usr/bin/env python3
"""Collect Stage 1 official evidence without changing Schema or business data."""
from __future__ import annotations

import hashlib
import http.cookiejar
import json
import mimetypes
import re
import ssl
import time
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urljoin, urlparse
from urllib.request import HTTPCookieProcessor, HTTPSHandler, Request, build_opener

ROOT = Path(__file__).resolve().parent.parent
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/127 Safari/537.36 anhui-zsb-archiver/1.0"
ALLOWED = ("hfnu.edu.cn", "ahua.edu.cn", "web.archive.org")
CAPTCHA = ("请输入验证码", "验证码下载附件", "captcha")
EXTS = {".pdf", ".doc", ".docx", ".xls", ".xlsx", ".zip"}

SOURCES = [
    {"id":"HFNU-2024-ZC","school":"HFNU","year":2024,"title":"合肥师范学院2024年普通高校专升本招生章程","url":"https://zsb.hfnu.edu.cn/info/1003/2715.htm","path":"raw/2024/HFNU/DOC-HFNU-2024-ZC.html","cats":["招生章程","招生计划","专业及培养地点","考试科目","报考范围","录取规则"]},
    {"id":"HFNU-2024-LQ","school":"HFNU","year":2024,"title":"2024年专升本招生考试录取分数线","url":"https://zsb.hfnu.edu.cn/info/1002/3065.htm","path":"raw/2024/HFNU/DOC-HFNU-2024-LQ.html","cats":["录取分数","调剂信息"]},
    {"id":"HFNU-2025-LQ","school":"HFNU","year":2025,"title":"2025年专升本招生考试录取分数线","url":"https://zsb.hfnu.edu.cn/info/1002/3475.htm","path":"raw/2025/HFNU/DOC-HFNU-2025-LQ.html","cats":["录取分数","调剂信息"]},
    {"id":"HFNU-2026-LQ","school":"HFNU","year":2026,"title":"2026年专升本招生考试录取分数线","url":"https://zsb.hfnu.edu.cn/info/1002/3885.htm","path":"raw/2026/HFNU/DOC-HFNU-2026-LQ.html","cats":["录取分数","调剂信息"]},
    {"id":"HFNU-2024-DG","school":"HFNU","year":2024,"title":"2024年普通高校专升本拟招生专业","url":"https://zsb.hfnu.edu.cn/info/1002/2695.htm","path":"raw/2024/HFNU/DOC-HFNU-2024-DG.html","cats":["考试大纲","参考教材","考试科目","招生计划","报考范围"],"attachments":[{"id":"HFNU-2024-DG-PDF","url":"https://zsb.hfnu.edu.cn/system/_content/download.jsp?owner=1090424591&urltype=news.DownloadAttachUrl&wbfileid=A5E8FF4D6F6748DEA5F8A94725163309","path":"raw/2024/HFNU/DOC-HFNU-2024-DG.pdf","name":"合肥师范学院2024年普通专升本招生考试大纲及参考书目.pdf","kind":"pdf","required":True}]},
    {"id":"HFNU-2025-DG","school":"HFNU","year":2025,"title":"2025年普通高校专升本拟招生专业范围","url":"https://zsb.hfnu.edu.cn/info/1002/3215.htm","path":"raw/2025/HFNU/DOC-HFNU-2025-DG.html","cats":["考试大纲","参考教材","考试科目","报考范围","专业及培养地点"],"attachments":[{"id":"HFNU-2025-DG-PDF","url":"https://zsb.hfnu.edu.cn/system/_content/download.jsp?owner=1090424591&urltype=news.DownloadAttachUrl&wbfileid=1712D2B6AD8613B7DB1A57B008224FC0","path":"raw/2025/HFNU/DOC-HFNU-2025-DG.pdf","name":"合肥师范学院2025年普通专升本招生考试大纲及参考书目.pdf","kind":"pdf","required":True}]},
    {"id":"HFNU-2026-DG","school":"HFNU","year":2026,"title":"2026年普通高校专升本拟招生专业范围","url":"https://zsb.hfnu.edu.cn/info/1002/3625.htm","path":"raw/2026/HFNU/DOC-HFNU-2026-DG.html","cats":["考试大纲","考试科目","报考范围"],"attachments":[{"id":"HFNU-2026-DG-PDF","url":"https://zsb.hfnu.edu.cn/system/_content/download.jsp?owner=1090424591&urltype=news.DownloadAttachUrl&wbfileid=7298453E08C33B075C74A9629F539E8D","path":"raw/2026/HFNU/DOC-HFNU-2026-DG.pdf","name":"合肥师范学院2026年普通专升本招生考试大纲（专业课）.pdf","kind":"pdf","required":True}]},
    {"id":"AHUA-2026-ZC","school":"AHUA","year":2026,"title":"安徽艺术学院2026年普通高校专升本招生章程","url":"https://www.ahua.edu.cn/zsw/2026/0318/c201a46012/page.htm","path":"raw/2026/AHUA/DOC-AHUA-2026-ZC.html","cats":["招生章程","招生计划","专业及培养地点","考试科目","报考范围","录取规则","调剂信息"]},
    {"id":"AHUA-2026-FA","school":"AHUA","year":2026,"title":"2026年普通高校专升本拟招生专业及考试方案","url":"https://www.ahua.edu.cn/zsw/2025/1031/c201a44096/page.htm","path":"raw/2026/AHUA/DOC-AHUA-2026-FA.html","cats":["招生专业","考试科目","报考范围"]},
    {"id":"AHUA-2026-XZYX","school":"AHUA","year":2026,"title":"2026年普通高校专升本新增招生专业","url":"https://www.ahua.edu.cn/zsw/2026/0205/c201a45646/page.htm","path":"raw/2026/AHUA/DOC-AHUA-2026-XZYX.html","cats":["招生计划","专业及培养地点","考试科目","考试大纲","参考教材","报考范围"]},
    {"id":"AHUA-2026-KSNR","school":"AHUA","year":2026,"title":"2026年普通高校专升本招生各专业考试内容","url":"https://www.ahua.edu.cn/zsw/2026/0318/c201a46013/page.htm","path":"raw/2026/AHUA/DOC-AHUA-2026-KSNR.html","cats":["考试科目","考试大纲"]},
    {"id":"AHUA-2026-LQ","school":"AHUA","year":2026,"title":"2026年专升本招生考试拟录取名单查询","url":"https://www.ahua.edu.cn/zsw/2026/0520/c201a46973/page.htm","path":"raw/2026/AHUA/DOC-AHUA-2026-LQ.html","cats":["录取分数","调剂信息"]},
    {"id":"AHUA-2024-ZC","school":"AHUA","year":2024,"title":"安徽艺术学院2024年普通高校专升本招生章程","url":"https://www.ahua.edu.cn/zsw/2024/0321/c201a29345/page.htm","path":"raw/2024/AHUA/DOC-AHUA-2024-ZC.html","cats":["招生章程","招生计划","专业及培养地点","考试科目","报考范围","录取规则"]},
    {"id":"AHUA-2024-BKRS","school":"AHUA","year":2024,"title":"2024年专升本招生考试各专业报考人数一览表","url":"https://www.ahua.edu.cn/zsw/2024/0406/c201a29560/page.htm","path":"raw/2024/AHUA/DOC-AHUA-2024-BKRS.html","cats":["报名人数或报录数据"]},
    {"id":"AHUA-2024-LQ","school":"AHUA","year":2024,"title":"2024年专升本招生考试拟录取名单查询","url":"https://www.ahua.edu.cn/zsw/2024/0524/c201a31068/page.htm","path":"raw/2024/AHUA/DOC-AHUA-2024-LQ.html","cats":["录取分数","调剂信息","报录数据"]},
]
REQUIRED_B = ["招生章程","招生计划","专业及培养地点","考试科目","考试大纲","参考教材","报考范围","录取规则","录取分数","调剂信息","报名人数或报录数据"]

class Links(HTMLParser):
    def __init__(self): super().__init__(); self.items=[]
    def handle_starttag(self, tag, attrs):
        if tag.lower()=="a":
            href=dict(attrs).get("href")
            if href: self.items.append(href)

def now(): return datetime.now(timezone.utc).isoformat(timespec="seconds")
def sha(data): return hashlib.sha256(data).hexdigest()
def allowed(url):
    host=(urlparse(url).hostname or "").lower()
    return any(host==x or host.endswith("."+x) for x in ALLOWED)
def text(data, headers=None):
    enc=(headers.get_content_charset() if headers else None) or "utf-8"
    for candidate in (enc,"utf-8","gb18030"):
        try: return data.decode(candidate)
        except (UnicodeDecodeError,LookupError): pass
    return data.decode("utf-8","replace")

jar=http.cookiejar.CookieJar()
opener=build_opener(HTTPCookieProcessor(jar),HTTPSHandler(context=ssl.create_default_context()))
def fetch(url, referer=None, tries=3):
    if not allowed(url): raise RuntimeError("host_not_allowed")
    headers={"User-Agent":UA,"Accept-Language":"zh-CN,zh;q=0.9","Cache-Control":"no-cache"}
    if referer: headers["Referer"]=referer
    error=None
    for i in range(tries):
        try:
            with opener.open(Request(url,headers=headers),timeout=45) as r:
                return r.read(),r.headers,r.geturl(),getattr(r,"status",200)
        except (HTTPError,URLError,TimeoutError,OSError) as exc:
            error=exc; time.sleep(2*(i+1))
    raise RuntimeError(f"fetch_failed:{error}")

def valid_pdf(data): return data.startswith(b"%PDF-")
def captcha(data,headers):
    preview=text(data[:12000],headers).lower()
    return any(x.lower() in preview for x in CAPTCHA)
def wayback(url):
    q=urlencode({"url":url,"output":"json","fl":"timestamp,original,statuscode,mimetype,digest,length","collapse":"digest"})+"&filter=statuscode%3A200&filter=mimetype%3Aapplication%2Fpdf"
    try:
        data,_,_,_=fetch("https://web.archive.org/cdx/search/cdx?"+q,tries=2)
        rows=json.loads(data.decode())
        if len(rows)<2: return None
        ts,original,*_=rows[-1]
        return fetch(f"https://web.archive.org/web/{ts}id_/{original}",tries=2)
    except Exception: return None

def save(path,data):
    p=ROOT/path; p.parent.mkdir(parents=True,exist_ok=True); p.write_bytes(data)
def record(src,asset_id,kind,url,path,data=None,headers=None,final="",status=None,method="",required=True,error="",name=""):
    return {"asset_id":asset_id,"source_id":src["id"],"school_id":src["school"],"year":src["year"],"title":src["title"],"categories":src["cats"],"asset_type":kind,"source_level":"S","source_url":url,"retrieval_url":final,"retrieval_method":method,"local_path":path,"original_file_name":name or Path(path).name,"content_type":headers.get_content_type() if headers else "","http_status":status,"file_size":len(data) if data else None,"sha256":sha(data) if data else "","retrieved_at":now(),"required":required,"status":"collected" if data else "failed","error":error}

def collect_attachment(src,a):
    try:
        data,h,final,status=fetch(a["url"],src["url"])
        method="official_direct"
        if captcha(data,h) or (a["kind"]=="pdf" and not valid_pdf(data)):
            archived=wayback(a["url"])
            if archived:
                data,h,final,status=archived; method="web_archive_official_bytes"
        if captcha(data,h): raise RuntimeError("blocked_by_captcha")
        if a["kind"]=="pdf" and not valid_pdf(data): raise RuntimeError(f"expected_pdf_received_{h.get_content_type()}")
        save(a["path"],data)
        return record(src,a["id"],a["kind"],a["url"],a["path"],data,h,final,status,method,a.get("required",False),name=a.get("name",""))
    except Exception as exc:
        return record(src,a["id"],a["kind"],a["url"],a["path"],required=a.get("required",False),error=f"{type(exc).__name__}:{exc}",name=a.get("name",""))

def discovered(src,data,headers):
    parser=Links(); parser.feed(text(data,headers)); out=[]; seen=set()
    explicit={a["url"] for a in src.get("attachments",[])}
    for href in parser.items:
        url=urljoin(src["url"],href); ext=Path(urlparse(url).path).suffix.lower()
        if url in explicit or url in seen or not allowed(url): continue
        if ext not in EXTS and "download.jsp" not in url and "/_upload/article/files/" not in url: continue
        seen.add(url)
        try:
            payload,h,final,status=fetch(url,src["url"])
            if captcha(payload,h): raise RuntimeError("blocked_by_captcha")
            if payload.startswith(b"%PDF-"): ext=".pdf"
            elif not ext: ext=mimetypes.guess_extension(h.get_content_type()) or ".bin"
            path=str(Path(src["path"]).with_suffix(""))+f"-ATT-{len(out)+1:02d}{ext}"
            save(path,payload)
            out.append(record(src,f"{src['id']}-ATT-{len(out)+1:02d}",ext.lstrip("."),url,path,payload,h,final,status,"official_discovered_attachment",False))
        except Exception as exc:
            out.append(record(src,f"{src['id']}-ATT-{len(out)+1:02d}","attachment",url,"",required=False,error=f"{type(exc).__name__}:{exc}"))
    return out

def main():
    records=[]
    for src in SOURCES:
        print("[HTML]",src["id"],src["url"])
        try:
            data,h,final,status=fetch(src["url"])
            body=text(data,h)
            if len(data)<500 or src["title"] not in body or captcha(data,h): raise RuntimeError("invalid_html_or_missing_title")
            save(src["path"],data)
            records.append(record(src,f"{src['id']}-HTML","html_snapshot",src["url"],src["path"],data,h,final,status,"official_direct",True))
            for a in src.get("attachments",[]): records.append(collect_attachment(src,a))
            records.extend(discovered(src,data,h))
        except Exception as exc:
            records.append(record(src,f"{src['id']}-HTML","html_snapshot",src["url"],src["path"],required=True,error=f"{type(exc).__name__}:{exc}"))
            for a in src.get("attachments",[]): records.append(collect_attachment(src,a))
    coverage={}
    for r in records:
        if r["school_id"]=="AHUA" and r["status"]=="collected":
            for c in r["categories"]: coverage.setdefault(c,[]).append(r["asset_id"])
    required_fail=[r for r in records if r["required"] and r["status"]!="collected"]
    missing=[c for c in REQUIRED_B if c not in coverage]
    ok=not required_fail and not missing
    config=ROOT/"config"; reports=ROOT/"reports"; config.mkdir(exist_ok=True); reports.mkdir(exist_ok=True)
    inventory={"schema_version":"phase1-evidence-v1","generated_at":now(),"scope":{"pilot_a":"HFNU missing evidence","pilot_b":"AHUA heterogeneous evidence pack","canonical_data_modified":False,"schema_modified":False},"assets":records}
    (config/"phase1_evidence_inventory.json").write_text(json.dumps(inventory,ensure_ascii=False,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    report={"ok":ok,"generated_at":now(),"source_count":len(SOURCES),"asset_count":len(records),"collected_count":sum(r["status"]=="collected" for r in records),"required_failures":required_fail,"pilot_b_category_coverage":coverage,"pilot_b_missing_categories":missing}
    (reports/"stage1_evidence_collection_report.json").write_text(json.dumps(report,ensure_ascii=False,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    lines=["# 阶段 1 官方证据采集报告","",f"> 结果：{'PASS' if ok else 'FAIL'}",f"> 生成时间：{report['generated_at']}","","## 资产","","| 学校 | 年份 | 类型 | 状态 | 路径 | SHA-256 |","|---|---:|---|---:|---|---|"]
    for r in records: lines.append(f"| {r['school_id']} | {r['year']} | {r['asset_type']} | {'PASS' if r['status']=='collected' else 'FAIL'} | `{r['local_path']}` | `{r['sha256'][:16]}` |")
    lines += ["","## Pilot B 覆盖","","| 主题 | 状态 |","|---|---:|"]+[f"| {c} | {'PASS' if c in coverage else 'FAIL'} |" for c in REQUIRED_B]
    lines += ["","## 失败项",""]+([f"- `{r['asset_id']}`：{r['error']}" for r in records if r['status']!='collected'] or ["无。"]) + ["","本阶段只归档官方证据，不修改 canonical、staging 或 Schema。"]
    (reports/"stage1_evidence_collection_report.md").write_text("\n".join(lines)+"\n",encoding="utf-8")
    (reports/"pilot_b_selection.md").write_text("""# Pilot B：安徽艺术学院\n\n选择理由：艺术类实践考试、多联合培养院校/校区、多种计分口径，并同时存在理论笔试专业；结构明显不同于 HFNU。2024 年官方还公开了分专业报考人数，可验证报录数据主题。\n\n本阶段只建立证据包，不修改 Schema。\n""",encoding="utf-8")
    print(f"Stage 1 evidence: {'PASS' if ok else 'FAIL'}; collected={report['collected_count']}/{len(records)}")
    return 0 if ok else 1

if __name__=="__main__": raise SystemExit(main())
