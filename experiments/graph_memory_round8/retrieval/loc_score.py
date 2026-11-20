import csv
import hashlib
import io
import json
import numpy as np
from acquire import ROOT,member
from loc_rank import TASKS,base,METHODS
from score import scores,mean,paired,SEED,MEASURES
def main():
    seal=json.loads((ROOT/'loc_seal.json').read_text())
    assert all(hashlib.sha256((ROOT/f).read_bytes()).hexdigest()==h for f,h in seal.items())
    details={};judgment=[];empty=[]
    for t in TASKS:
        raw=member(base(t)+'qrels/test.tsv')
        rows=list(csv.DictReader(io.StringIO(raw.decode()),delimiter='\t'))
        assert all(r['query-id']==t for r in rows)
        g={r['corpus-id'] for r in rows if float(r['score'])>0}
        judgment.append({'issue':t,'gold':sorted(g),'qrels_sha256':hashlib.sha256(raw).hexdigest()})
        if not g:empty.append(t);continue
        p=json.loads((ROOT/'loc_predictions'/(t+'.json')).read_text())
        cand=p['candidates']
        relevant=[c for c in cand if c['id'] in g]
        gold_ranks={m:sorted(c['ranks'][m] for c in relevant) for m in METHODS}
        details[t]=dict(corpus=len(cand),gold=len(g),gold_in_corpus=len(relevant),n_anchors=len(p['anchors']),n_edges=len(p['edges']),gold_ranks=gold_ranks,methods={m:scores(gold_ranks[m],len(g)) for m in METHODS})
    ids=list(details); assert len(ids)
    ix=np.random.default_rng(SEED).integers(0,len(ids),(10000,len(ids)))
    means={m:{v:mean([details[t]['methods'][m][v] for t in ids]) for v in MEASURES} for m in METHODS}
    contrasts={a+'-'+b:{v:paired([details[t]['methods'][a][v]-details[t]['methods'][b][v] for t in ids],ix) for v in MEASURES} for a,b in [('graph',m) for m in METHODS if m!='graph']+[('rrf','dense'),('direct','rrf')]}
    (ROOT/'loc_judgments.json').write_text(json.dumps(judgment,indent=2))
    (ROOT/'loc_results.json').write_text(json.dumps(dict(means=means,comparisons=contrasts,details=details,empty=empty),indent=2))
    for m in METHODS:print(m,means[m]['mrr10'],means[m]['hit10'])
    print('graph-direct',contrasts['graph-direct']['mrr10'])
if __name__=='__main__':main()
