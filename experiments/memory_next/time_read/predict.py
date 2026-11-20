"""Eligible pools, topic-ordering and past-only BM25. No related-experience labels at prediction."""
import csv
import datetime as dt
import hashlib
import json
import math
import re
from collections import Counter
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parent
BASE=ROOT.parent
OLD=BASE.parent/'sota_round'/'swe_context'
def read(p):return json.loads(p.read_text(encoding='utf8'))
def table(p):
    with p.open(encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))
def save(p,obj):p.write_text(json.dumps(obj,ensure_ascii=False,indent=1),encoding='utf8')
def sha(s):return hashlib.sha256(s.encode()).hexdigest()
def terms(s):
    out=[]
    for t in re.findall(r'[A-Za-z0-9_]+',s):
        out.append(t.lower());parts=re.sub(r'([a-z])([A-Z])',r'\1 \2',t).replace('_',' ').lower().split()
        if len(parts)>1:out.extend(parts)
    return out
def bm25(docs,query):
    q=Counter(terms(query));d=[Counter(terms(s)) for s in docs]
    N=len(d);lens=[sum(x.values()) for x in d];avg=max(1,sum(lens)/max(1,N))
    df=Counter(x for counts in d for x in counts)
    return [sum(min(2,n)*math.log((N+1)/(df[t]+.5))*2.2*doc[t]/(doc[t]+1.2*(.25+.75*sz/avg)) for t,n in q.items() if t in doc) for doc,sz in zip(d,lens)]
def order(a):return sorted(range(len(a)),key=lambda j:(-a[j],j))
def online(keys,cards,query):
    score=[0.]*len(keys)
    for field,weight in [('symptom',2),('closure',1),('edits',1)]:
        values=bm25([cards[k][field] for k in keys],query)
        for rank,idx in enumerate(order(values),1):score[idx]+=weight/(12+rank)
    return [keys[j] for j in order(score)]
def timestamp(s):return dt.datetime.fromisoformat(s.replace('Z','+00:00'))
def main():
    tr=BASE/'transfer';wr=BASE/'write_factor'
    queries=read(OLD/'queries.json');cards={v['key']:v for v in read(OLD/'cards.json')}
    sources={r['trace_key']:r for r in table(tr/'source_times_lite.csv')};targets=table(tr/'query_times_lite.csv')
    rank=np.load(wr/'rankings.npz');keys=read(wr/'keys.json');results=[]
    for t in sorted(targets,key=lambda x:int(x['ordinal'])):
        i=int(t['ordinal'])
        allowed=sorted(k for k,s in sources.items() if t['opening_complete']=='1' and s['repo'].lower()==t['repo'].lower() and s['source_pr']!=t['target_pr'] and s['source_merge'] and timestamp(s['source_merge'])<timestamp(t['cutoff_utc']))
        pool=set(allowed)
        out={k:[keys[j] for j in rank[k][i] if keys[j] in pool] for k in rank.files}
        out['online_fields']=online(allowed,cards,queries[i]['query'])
        out['recent']=sorted(allowed,key=lambda k:(timestamp(sources[k]['source_merge']),k),reverse=True)
        results.append({'ordinal':i,'eligible':allowed,'ranks':out})
    save(ROOT/'blind_lists.json',results)
    inputs=[ROOT/'PROTOCOL.md',ROOT/'COMPARATOR.md',ROOT/'predict.py',OLD/'queries.json',OLD/'cards.json',tr/'source_times_lite.csv',tr/'query_times_lite.csv',wr/'rankings.npz',wr/'keys.json',ROOT/'blind_lists.json']
    save(ROOT/'rank_lock.json',{x.name:hashlib.sha256(x.read_bytes()).hexdigest() for x in inputs})
    print('pool sizes',len(results),min(len(r['eligible']) for r in results),max(len(r['eligible']) for r in results),sum(len(r['eligible'])>=2 for r in results))
if __name__=='__main__':main()

