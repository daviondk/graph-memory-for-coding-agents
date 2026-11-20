from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import numpy as np
from acquire import ROOT
from pool_rank import METHODS
from score import scores,get_judgments,paired,mean,SEED

def main():
    seal=json.loads((ROOT/'pool_seal.json').read_text())
    assert all(hashlib.sha256((ROOT/p).read_bytes()).hexdigest()==h for p,h in seal.items())
    sample=json.loads((ROOT/'pool_sample.json').read_text())
    with ThreadPoolExecutor(max_workers=8) as pool: jud=list(pool.map(get_judgments,sample))
    (ROOT/'pool_judgments.json').write_text(json.dumps(jud,indent=2))
    detail={};empty=[]
    for t,g,sha in jud:
        if not g: empty.append(t);continue
        p=json.loads((ROOT/'pool_predictions'/(t+'.json')).read_text())
        d={k:p[k] for k in ['repo','n_corpus','n_propagated','n_scanned_for_graph']}
        d['n_anchors']=len(p['anchors']);d['n_gold']=len(g);d['methods']={}
        for m,short in p['top40'].items():
            r=[k+1 for k,c in enumerate(short) if c['id'] in g]
            d['methods'][m]={**scores(r,len(g)),'recall40':len(r)/len(g),'hit40':int(bool(r))}
        detail[t]=d
    ids=list(detail);rng=np.random.default_rng(SEED)
    groups=[[i for i,t in enumerate(ids) if detail[t]['repo']==r] for r in sorted({d['repo'] for d in detail.values()})]
    ix=np.concatenate([rng.choice(g,size=(10000,len(g)),replace=True) for g in groups],axis=1)
    metrics=detail[ids[0]]['methods'][METHODS[0]].keys()
    means={m:{v:mean([detail[t]['methods'][m][v] for t in ids]) for v in metrics} for m in METHODS}
    comp={a+'-'+b:{v:paired([detail[t]['methods'][a][v]-detail[t]['methods'][b][v] for t in ids],ix) for v in metrics} for a,b in [('graph','direct'),('direct','field'),('graph','field'),('field','body'),('graph','body')]}
    result={'sampled':len(sample),'judged':len(ids),'empty_qrels':empty,'means':means,'comparisons':comp,'details':detail}
    (ROOT/'pool_results.json').write_text(json.dumps(result,indent=2))
    print(means)
    for k,v in comp.items():print(k,v['recall40'])
if __name__=='__main__':main()
