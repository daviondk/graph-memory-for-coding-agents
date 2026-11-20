"""Download and project public, pinned data; never read relevance or target solution fields."""
import collections
import concurrent.futures
import csv
import datetime
import hashlib
import json
import os
from pathlib import Path
import time
import urllib.parse

import pyarrow.parquet as pq
import requests
from date_fallback import fetch_missing
from issue_dates import resolve

ROOT = Path(__file__).resolve().parent
CACHE = Path(os.environ.get("TRANSFER_CACHE", "D:/CodexResearch/x20-swe-context/full-transfer"))
ORIG = CACHE.parent
GH = "12ad6ab14e18e9378e1e293c9edbc3f7ce43d27b"
HF = "12c65bd15e2559bc808065565e941ee7bbbd008f"
DATASET = "jiayuanz3/SWEContextBench"
ENDPOINT = "https://sql-clickhouse.clickhouse.com"
CACHE.mkdir(parents=True, exist_ok=True)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def save(name, obj):
    (ROOT/name).write_text(json.dumps(obj,ensure_ascii=False,indent=1),encoding="utf8")


def get(url, **kwargs):
    for attempt in range(4):
        try:
            r=requests.get(url,timeout=45,**kwargs); r.raise_for_status(); return r
        except requests.RequestException:
            if attempt==3:raise
            time.sleep(1+attempt*2)


def parquet(name):
    existing=ORIG/(name+".parquet")
    path=existing if existing.is_file() else CACHE/(name+".parquet")
    if not path.is_file():
        path.write_bytes(get(f"https://huggingface.co/datasets/{DATASET}/resolve/{HF}/data/{name}.parquet").content)
    return path


def load_inputs():
    src=parquet('SWEContextBench_Experience'); rel=parquet('SWEContextBench_Related'); lite=parquet('SWEContextBench_Related_Lite')
    dcols=['instance_id','repo','created_at','problem_statement','patch']
    docs=pq.read_table(src, columns=dcols).to_pylist()
    queries=pq.read_table(rel, columns=dcols[:-1]).to_pylist()
    lite_ids=set(pq.read_table(lite, columns=['instance_id']).column(0).to_pylist())
    clean_docs={r['instance_id']:r for r in docs}
    clean_queries={}
    for row in queries:
        if row['instance_id'] not in lite_ids:clean_queries.setdefault(row['instance_id'],row)
    return clean_docs,clean_queries,{'hf':HF,'github':GH,'raw_releases':{p.name:{'bytes':p.stat().st_size,'sha256':sha(p.read_bytes())} for p in [src,rel,lite]},'source_rows':len(docs),'query_rows':len(queries),'lite_ids':len(lite_ids),'unique_sources':len(clean_docs),'non_lite_queries':len(clean_queries)}


def fetch_issues(queries):
    tree=get(f"https://api.github.com/repos/{DATASET}/git/trees/{GH}?recursive=1").json()['tree']
    by_lower={i.lower():i for i in queries}
    tasks=[x for x in tree if x['path'].startswith("cases/SWEContextBench Full/") and Path(x['path']).stem.lower() in by_lower]
    def one(entry):
        iid=by_lower[Path(entry['path']).stem.lower()]
        dst=CACHE/'case-refs'/f'{iid}.json'
        if not dst.exists():
            url=f"https://raw.githubusercontent.com/{DATASET}/{GH}/"+urllib.parse.quote(entry['path'])
            raw=get(url).content
            assert hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()==entry['sha']
            obj=json.loads(raw)
            # Only these 3 public chronology fields leave the projector.
            evt={k:obj[k] for k in ['repo','pull_number','issue_numbers']}
            evt.update(identifier=iid,blob=entry['sha'])
            dst.write_text(json.dumps(evt),encoding='utf8')
        return json.loads(dst.read_text(encoding='utf8'))
    (CACHE/'case-refs').mkdir(exist_ok=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=7) as pool: arr=list(pool.map(one,tasks))
    assert set(queries)=={r['identifier'] for r in arr}
    return {r['identifier']:r for r in arr}


def stamp(value):
    if not value or value.startswith("1970-01-01"):return None
    return value[:19].replace(" ","T")+"Z"


def chronology(docs,queries,refs):
    requested=collections.defaultdict(set)
    for doc in docs.values():requested[doc['repo']].add(int(doc['instance_id'].rsplit('-',1)[1]))
    for item in refs.values():
        requested[queries[item['identifier']]['repo']].update(int(v) for v in [item['pull_number'],*item['issue_numbers']])
    records={}
    def one(repo):
        ns=sorted(requested[repo])
        name=repo.replace('/','__')+'-'+sha(str(ns).encode())[:10]
        assert all(s.isalnum() or s in '-_./' for s in repo)
        aliases={repo,*[item['repo'] for item in refs.values() if item['repo'].lower()==repo.lower()]}
        query=f"""SELECT number, minIf(created_at,action='opened') AS opened, minIf(merged_at,event_type='PullRequestEvent' AND merged_at>toDateTime(0)) AS merged
        FROM github.github_events WHERE event_type IN ('PullRequestEvent','IssuesEvent') AND repo_name IN ({','.join(repr(s) for s in sorted(aliases))}) AND number IN ({','.join(str(v) for v in ns)})
        GROUP BY number ORDER BY number FORMAT JSONEachRow"""
        path=CACHE/'time'/f'{name}.jsonl'
        if not path.exists():
            path.write_bytes(get(ENDPOINT,params={'user':'play','query':query}).content)
        rows=[json.loads(line) for line in path.read_text(encoding='utf8').splitlines() if line]
        return repo,{str(row['number']):{'open':stamp(row['opened']),'merge':stamp(row['merged'])} for row in rows}
    (CACHE/'time').mkdir(exist_ok=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        for repo,nums in pool.map(one,sorted(requested)):records[repo]=nums
    return records


def run():
    docs,queries,receipt=load_inputs()
    full={r['instance_id']:r for r in pq.read_table(parquet('SWEContextBench_Related'),columns=['instance_id','repo','created_at']).to_pylist()}
    refs=fetch_issues(full)
    times=chronology(docs,full,refs)
    requested=collections.defaultdict(set)
    for i,d in docs.items():requested[d['repo'],i.rsplit('-',1)[1]].add('merge')
    for iid,r in refs.items():
        repo=full[iid]['repo']
        requested[repo,str(r['pull_number'])].update(['open','merge'])
        for num in r['issue_numbers']:requested[repo,str(num)].add('open')
    html_rows=fetch_missing(CACHE/'html-evidence',requested,times)
    save('html_clock_evidence.json',html_rows)
    issue_urls=pq.read_table(parquet('SWEContextBench_Relationship'),columns=['related_instance_id','related_issue_url']).to_pylist()
    clocks=resolve(refs,full,issue_urls,times,CACHE/'trac')
    save('issue_dates.json',clocks)
    for iid, ls in clocks.items():refs[iid]['issue_clock']=ls
    save('case_refs.json',refs);save('github_times.json',times)
    receipt['time_api']=ENDPOINT
    receipt['time_db']='github.github_events'
    receipt['downloaded_utc']=datetime.datetime.now(datetime.timezone.utc).isoformat()
    receipt['source_merge_confirmed']=sum(bool(times[d['repo']].get(i.rsplit('-',1)[1],{}).get('merge')) for i,d in docs.items())
    save('source.json',receipt)
    print(receipt['unique_sources'],receipt['non_lite_queries'],receipt['source_merge_confirmed'],flush=True)


if __name__=='__main__':run()

