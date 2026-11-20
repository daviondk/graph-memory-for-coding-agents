"""Extract target-side issue references only, resolving Django tickets in their own namespace."""
import concurrent.futures
import collections
import datetime
import hashlib
import html
import json
import re
import time
from urllib.parse import urlsplit, parse_qs, unquote
import requests


def resolve(refs,full,links,times,cache):
    cache.mkdir(exist_ok=True)
    urls=collections.defaultdict(set)
    for row in links:
        value=row['related_issue_url']
        if value:urls[row['related_instance_id']].add(value.rstrip('/'))
    tasks={}
    for key,ref in refs.items():
        known=urls[key].copy()
        for n in ref['issue_numbers']:
            if any(url.rsplit('/',1)[-1]==str(n) for url in known):
                continue
            base=('https://code.djangoproject.com/ticket/' if any('code.djangoproject.com' in u for u in known) else 'https://github.com/'+full[key]['repo']+'/issues/')
            known.add(base+str(n))
        tasks[key]=sorted(known)
    def trac(url):
        number=url.rsplit('/',1)[-1];f=cache/(number+'.json')
        if f.exists():return json.loads(f.read_text(encoding='utf8'))
        for attempt in range(4):
            r=requests.get(url,timeout=35)
            if r.status_code!=429:break
            delay=r.headers.get('Retry-After','')
            time.sleep(min(60,max(4,int(delay) if delay.isdigit() else 5*(attempt+1))))
        if r.status_code!=200:
            return {'url':url,'open':None,'source':'unknown','http':r.status_code}
        m=re.search(r'<p>\s*Opened\s+<a[^>]+href="([^"]+)"',r.text,re.I)
        data={'url':url,'html_sha256':hashlib.sha256(r.content).hexdigest(),'open':None,'source':'Django Trac'}
        if m:
            ts=parse_qs(urlsplit(html.unescape(m[1])).query)['from'][0]
            data.update(open=datetime.datetime.fromisoformat(ts).astimezone(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),evidence=m[0])
        f.write_text(json.dumps(data),encoding='utf8')
        time.sleep(.6)
        return data
    distinct=sorted({u for us in tasks.values() for u in us if 'code.djangoproject.com' in u})
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:trac_dates={r['url']:r for r in pool.map(trac,distinct)}
    result={}
    for key,ls in tasks.items():
        repo=full[key]['repo'];events=times[repo]
        rec=[]
        for url in ls:
            if url in trac_dates:
                rec.append(trac_dates[url]);continue
            number=url.rsplit('/',1)[-1]
            ev=events.get(number,{})
            rec.append({'url':url,'open':ev.get('open'),'source':ev.get('open_source','GHArchive') if ev.get('open') else 'unknown'})
        result[key]=rec
    return result

