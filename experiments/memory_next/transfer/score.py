"""Score frozen predictions on published links. All unavailable queries remain misses."""
import collections
import csv
import gzip
import hashlib
import json
import math
import random
import statistics

import pyarrow.parquet as pq

from prepare import ROOT,parquet,save,sha
from rank import ARMS


def exact(gain,loss):
    n=gain+loss
    return min(1, 2*sum(math.comb(n,k) for k in range(min(gain,loss)+1))/2**n)


def percentile(a,p):
    a=sorted(a)
    x=(len(a)-1)*p
    l=int(x)
    return a[l]+(a[min(l+1,len(a)-1)]-a[l])*(x-l)


def paired(rows,a,b):
    clusters=collections.defaultdict(list)
    vals=[]
    for r in rows:
        x=int(r[a+'_1'])-int(r[b+'_1']);vals.append(x);clusters[r['repo']].append(x)
    cpairs=[(sum(v),len(v)) for v in clusters.values()]
    if not cpairs:return {'n':0}
    rng=random.Random(16112026)
    boot=[]
    for i in range(10000):
        sample=rng.choices(cpairs,k=len(cpairs))
        boot.append(sum(v for v,n in sample)/sum(n for v,n in sample))
    return {'n':len(vals),'repos':len(cpairs),'gain':vals.count(1),'loss':vals.count(-1),'delta':statistics.mean(vals),'repo_ci95':[percentile(boot,.025),percentile(boot,.975)],'p_descriptive':exact(vals.count(1),vals.count(-1))}


def summarize(rows):
    if not rows:return {'n':0}
    out={'n':len(rows),'repos':len({r['repo'] for r in rows}),'gold_available':sum(r['available'] for r in rows),'median_candidates':statistics.median(r['n'] for r in rows)}
    out['arms']={a:{'hits1':sum(r[a+'_1'] for r in rows),'hits5':sum(r[a+'_5'] for r in rows),'mrr':statistics.mean(r[a+'_rr'] for r in rows)} for a in ARMS}
    out['pairs']={f'{a}_vs_{b}':paired(rows,a,b) for a,b in [('card','issue256'),('card','issue192'),('card','placebo'),('separate','issue256')]}
    return out


def run():
    lock=json.loads((ROOT/'blind_freeze.json').read_text(encoding='utf8'))
    for name,digest in lock['sha256'].items():assert sha((ROOT/name).read_bytes())==digest
    source=parquet('SWEContextBench_Relationship')
    gold=collections.defaultdict(list)
    for r in pq.read_table(source,columns=['related_instance_id','experience_instance_id']).to_pylist():
        if r['experience_instance_id'] not in gold[r['related_instance_id']]:
            gold[r['related_instance_id']].append(r['experience_instance_id'])
    results=[]
    with gzip.open(ROOT/'blind_ranks.jsonl.gz','rt',encoding='utf8') as fp:
        for line in fp:
            d=json.loads(line);target=d['target'];g=gold[target]
            assert g
            members=set(d['ranks']['issue256'])
            row={'id':target,'repo':d['repo'],'scope':d['scope'],'n':d['candidates'],'fully_dated':d['all_open_validated'] and d['has_issue_refs'],'available':bool(set(g)&members),'ngold':len(g),'gold':'|'.join(g)}
            for arm,ranking in d['ranks'].items():
                assert len(ranking)==len(set(ranking))==d['candidates'] and set(ranking)==members
                pos=next((j for j,i in enumerate(ranking,1) if i in g),0)
                row[arm+'_1']=pos==1
                row[arm+'_5']=1<=pos<=5
                row[arm+'_rr']=1/pos if pos else 0
                row[arm+'_first']=bool(ranking and ranking[0]==g[0])
                row[arm+'_last']=bool(ranking and ranking[0]==g[-1])
            results.append(row)
    with (ROOT/'per_question.csv').open('w',encoding='utf8',newline='') as fp:
        writer=csv.DictWriter(fp,fieldnames=list(results[0]));writer.writeheader();writer.writerows(results)
    out={}
    for sc in ['repo_time','all_time','repo_release']:
        rows=[r for r in results if r['scope']==sc]
        assert len(rows)==258
        subsets={'all':rows,'available':[r for r in rows if r['available']],'available_at_least_5':[r for r in rows if r['available'] and r['n']>=5],'fully_dated':[r for r in rows if r['fully_dated']],'fully_dated_available_at_least_5':[r for r in rows if r['fully_dated'] and r['available'] and r['n']>=5]}
        out[sc]={n:summarize(s) for n,s in subsets.items()}
        out[sc]['sensitivity']={a:{en:sum(r[a+'_'+en] for r in rows) for en in ['first','last']} for a in ['card','issue256']}
        out[sc]['candidate_distribution']={str(bound):sum(r['n']<=bound for r in rows) for bound in [0,1,4,9,19,49]}
    save('results.json',{'relation_sha256':sha(source.read_bytes()),'blind_freeze_sha256':sha((ROOT/'blind_freeze.json').read_bytes()),'results':out})
    for sc in out:print(sc,json.dumps(out[sc]['all'],ensure_ascii=False)[:1900])


if __name__=='__main__':run()

