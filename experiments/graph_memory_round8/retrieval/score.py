"""Judge only the sealed predictions using positive BEIR function qrels."""
import csv
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
import hashlib
import io
import json
import math
import numpy as np
from acquire import ROOT,member
from prepare import prefix
from rank import METHODS

MEASURES=['mrr10','hit1','hit5','hit10','recall10','ndcg10','all10']
SEED=923668
def mean(v): return float(np.mean(v))
def scores(ranks,num_gold):
    rr=sorted(ranks)
    at10=[r for r in rr if r<=10]
    discount=lambda r:1/math.log2(1+r)
    return dict(mrr10=1/rr[0] if at10 else 0,hit1=int(1 in rr),hit5=int(bool(rr) and rr[0]<=5),hit10=int(bool(at10)),recall10=len(at10)/num_gold,ndcg10=sum(map(discount,at10))/sum(discount(r) for r in range(1,1+min(10,num_gold))),all10=int(len(at10)==num_gold))
def get_judgments(t):
    raw=member(prefix(t)+'qrels/test.tsv')
    rows=list(csv.DictReader(io.StringIO(raw.decode()),delimiter='\t'))
    assert all(row['query-id']==t for row in rows)
    gs={row['corpus-id'] for row in rows if float(row['score'])>0}
    return t,sorted(gs),hashlib.sha256(raw).hexdigest()
def paired(diffs,indices):
    values=np.array(diffs)
    wt=sum(values>1e-12); lt=sum(values<-1e-12)
    n=wt+lt
    sign=min(1,2*sum(math.comb(n,i) for i in range(min(wt,lt)+1))/(2**n)) if n else 1
    return {'delta':mean(values),'lo':float(np.quantile(values[indices].mean(1),.025)),'hi':float(np.quantile(values[indices].mean(1),.975)),'wins':int(wt),'ties':len(values)-int(n),'losses':int(lt),'sign_p':float(sign)}
def main():
    manifest=json.loads((ROOT/'seal.json').read_text())
    assert all(hashlib.sha256((ROOT/p).read_bytes()).hexdigest()==h for p,h in manifest.items()),'Seal mismatch'
    sample=json.loads((ROOT/'sample.json').read_text())['selected']
    with ThreadPoolExecutor(max_workers=8) as pool: judgments=list(pool.map(get_judgments,sample))
    (ROOT/'judgments.json').write_text(json.dumps(judgments,indent=2))
    results=[]
    empty=[]
    detail={}
    for t,gs,sha in judgments:
        if not gs: empty.append(t);continue
        record=json.loads((ROOT/'predictions'/(t+'.json')).read_text(encoding='utf8'))
        cand=record['candidates']
        rel=[c for c in cand if c['id'] in gs]
        methods={m:scores([c['ranks'][m] for c in rel],len(gs)) for m in METHODS}
        changed=[c for c in cand if c['scores']['graph']>c['scores']['direct']+1e-12]
        detail[t]={'repo':record['repo'],'eligible_gold':len(rel),'all_gold':len(gs),'n_corpus':record['n_corpus'],'n_anchors':len(record['anchors']),'n_edges':len(record['edges']),'n_propagated':len(changed),'n_gold_propagated':sum(c['id'] in gs for c in changed),'gold_ranks':{m:sorted(c['ranks'][m] for c in rel) for m in METHODS},'methods':methods}
        for m in METHODS: results.append({'issue':t,'repo':record['repo'],'method':m,**methods[m]})
    ids=list(detail); assert ids, 'No scored tasks'
    repos=sorted({detail[t]['repo'] for t in ids})
    rng=np.random.default_rng(SEED)
    groups=[[i for i,t in enumerate(ids) if detail[t]['repo']==repo] for repo in repos]
    ix=np.concatenate([rng.choice(g,size=(10000,len(g)),replace=True) for g in groups],axis=1)
    diagnostics={'sampled':len(sample),'n_judged':len(ids),'empty_qrels':empty,'hit40_count':sum(d['eligible_gold']>0 for d in detail.values()),'n_anchors_issues':sum(d['n_anchors']>0 for d in detail.values()),'n_activated_issues':sum(d['n_propagated']>0 for d in detail.values()),'n_gold_propagated':sum(d['n_gold_propagated'] for d in detail.values()),'median_corpus':float(np.median([d['n_corpus'] for d in detail.values()]))}
    means={m:{v:mean([detail[t]['methods'][m][v] for t in ids]) for v in MEASURES} for m in METHODS}
    comparisons={}
    for a,b in [('graph',m) for m in METHODS if m!='graph']+[('direct','rrf'),('rrf','dense'),('dense','dense_dot')]:
        comparisons[a+'-'+b]={v:paired([detail[t]['methods'][a][v]-detail[t]['methods'][b][v] for t in ids],ix) for v in MEASURES}
    result={'diagnostics':diagnostics,'means':means,'comparisons':comparisons,'details':detail}
    with (ROOT/'per_issue.csv').open('w',encoding='utf8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(results[0]));w.writeheader();w.writerows(results)
    (ROOT/'results.json').write_text(json.dumps(result,indent=2))
    print(json.dumps(diagnostics))
    for m,x in means.items():print(m,' '.join(f'{v}={s:.3f}' for v,s in x.items()))
    for c in comparisons:print(c,comparisons[c]['mrr10'])
if __name__=='__main__':main()
