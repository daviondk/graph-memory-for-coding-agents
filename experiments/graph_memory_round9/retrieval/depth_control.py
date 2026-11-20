"""Post-hoc diagnostic: compare one-edge proposals to reading next dense positions."""
import numpy as np
from source import ROOT,load_json,write_json
from score import canon,metric,compare
def main():
    d=load_json(ROOT/'results.json')
    gold={t:{canon(s) for s in g} for t,g,_ in load_json(ROOT/'judgments.json')}
    rows={}
    for t,detail in d['details'].items():
        p=load_json(ROOT/'predictions'/(t+'.json'));o=p['ranks']['dense'];g=gold[t]
        n=len(p['suggestions']['one']);cuts=10-n;nextd=o[10:10+n];used=p['suggestions']['one']
        norder=o[:cuts]+nextd+[s for s in o[cuts:] if s not in nextd]
        full_old={canon(s) for s in o[:10]}
        assert len(norder)==len(set(norder))==len(o)
        rows[t]={'band':detail['band'],'n_extra':n,'next_dense':metric([i for i,k in enumerate(norder,1) if canon(k) in g],len(g)),'one':detail['methods']['one'],
        'extra_positive_next_dense':len(g&{canon(s) for s in nextd}),'extra_positive_graph':len(g&{canon(s) for s in used}),'same_suggestions':len(set(used)&set(nextd)),
        'all_after_extra_dense':int(g<=full_old|{canon(s) for s in nextd}),'all_after_extra_graph':int(g<=full_old|{canon(s) for s in used}),'prev_base_positive':len(full_old&g)}
    ids=list(rows); groups=[[i for i,t in enumerate(ids) if rows[t]['band']==b] for b in sorted({z['band'] for z in rows.values()})]
    ix=np.concatenate([np.random.default_rng(91108+i).choice(g,size=(10000,len(g)),replace=True) for i,g in enumerate(groups)],axis=1)
    stats={m:compare([rows[t]['one'][m]-rows[t]['next_dense'][m] for t in ids],ix) for m in ('acc10','recall10','mrr10','ndcg10')}
    totals={k:sum(v[k] for v in rows.values()) for k in ('n_extra','extra_positive_next_dense','extra_positive_graph','same_suggestions','all_after_extra_dense','all_after_extra_graph')}
    totals.update(next_dense_all=sum(v['next_dense']['acc10'] for v in rows.values()),next_dense_recall=float(np.mean([v['next_dense']['recall10'] for v in rows.values()])))
    write_json(ROOT/'depth_control.json',dict(status='post hoc after seeing dense ranks of graph-correct additions',totals=totals,deltas=stats,details=rows))
    print(totals,stats['acc10'])
if __name__=='__main__':main()
