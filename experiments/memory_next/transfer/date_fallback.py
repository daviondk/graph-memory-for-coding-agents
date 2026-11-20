"""Resolve missing event times from explicitly identified GitHub timeline events."""
import concurrent.futures
import hashlib
import html
import json
from pathlib import Path
import re
import time
import requests

UTC=r'([1-2]\d{3}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z)'
OPEN=re.compile(r'<a\s+[^>]*href="#issue-\d+"[^>]*>\s*<relative-time[^>]*\bdatetime="'+UTC, re.I)
MERGE=re.compile(r'>\s*merged commit\s+<a\s+href="[^"]+/commit/[0-9a-f]+"[^>]*>[\s\S]{0,1800}?<a\s+[^>]*href="[^"]+#event-\d+"[^>]*>\s*<relative-time[^>]*\bdatetime="'+UTC,re.I)
SCRIPTS=re.compile(r'<script[^>]*type="application/json"[^>]*>([\s\S]*?)</script>',re.I)


def find_obj(obj,number):
    if isinstance(obj,dict):
        if str(obj.get('number'))==number and obj.get('createdAt') and obj.get('state') and 'databaseId' in obj and ('stateReason' in obj or 'locked' in obj):
            return obj['createdAt']
        for child in obj.values():
            v=find_obj(child,number)
            if v:return v
    elif isinstance(obj,list):
        for child in obj:
            v=find_obj(child,number)
            if v:return v
    return None


def fetch_missing(cache,requested,times):
    work=[]
    for (repo,n),fields in sorted(requested.items()):
        existing=times.setdefault(repo,{}).setdefault(n,{'open':None,'merge':None})
        if any(not existing.get(k) for k in fields):work.append((repo,n))
    cache.mkdir(exist_ok=True)
    def one(case):
        repo,n=case
        path=cache/(repo.replace('/','__')+'-'+n+'.json')
        if path.exists():return json.loads(path.read_text(encoding='utf8'))
        url=f'https://github.com/{repo}/issues/{n}'
        record={'repo':repo,'number':n,'url':url}
        for attempt in range(4):
            try:
                res=requests.get(url,timeout=30)
                if res.status_code==429 and attempt<3:
                    time.sleep(4*(attempt+1));continue
                record.update(status=res.status_code,final_url=res.url,html_sha256=hashlib.sha256(res.content).hexdigest())
                if res.status_code==200:
                    text=res.text
                    m=OPEN.search(text)
                    if m:record.update(open=m[1],open_evidence=html.unescape(m[0])[:300])
                    else:
                        for raw in SCRIPTS.findall(text):
                            try: date=find_obj(json.loads(raw),n)
                            except (ValueError,TypeError):continue
                            if date:
                                record.update(open=date,open_evidence='application/json issue.number and databaseId, state, createdAt');break
                    m=MERGE.search(text)
                    if m and '/pull/' in res.url:
                        record.update(merge=m[1],merge_evidence=re.sub(r'\s+',' ',m[0])[:1600])
                break
            except requests.RequestException as ex:
                record['error']=repr(ex)
                time.sleep(1+attempt)
        path.write_text(json.dumps(record),encoding='utf8')
        return record
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool: results=list(pool.map(one,work))
    for v in results:
        target=times[v['repo']][v['number']]
        for name in ['open','merge']:
            if not target.get(name) and v.get(name):
                target[name]=v[name];target[name+'_source']='GitHub HTML'
    return results

