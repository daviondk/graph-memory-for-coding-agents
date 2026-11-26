"""One frozen evaluation. No fitting or test labels; serialize per-state cache residents."""
from lineage import *
import sys,numpy as np
sys.path.insert(0,str(FROZEN))
from predict import select,retention
from build_inputs import OLD
from experiment import Cache,Keys,GD,IntKeys
MODES=('graph','local','frequency_cost','cost_hot_lru','gdsf','cost')
def baseline(name):
    return GD('batch',31,IntKeys()) if name=='gdsf' else Cache({'frequency_cost':'proposed','cost_hot_lru':'hot_lru','cost':'cost'}[name],31,Keys())
def baseline_write(pol,m,row):
    order=row['order']
    if m=='cost_hot_lru':order=sorted(order,key=lambda k:(row['docs'][k][0],-int(k,16)))
    doc={k:row['docs'][k][0] for k in order}
    if m=='gdsf':pol.update(doc);return pol.res
    pol.operate(doc);return pol.entries()
def main():
    selection=rd(D/'selection.json');assert rd(D/'bridge.json')['gate'] and sha(FROZEN/'models.json')==selection['model'] and sha(D/'inputs.json.gz')==rd(D/'input-seal.json')['data']
    models=rd(FROZEN/'models.json')['transfer'];rows=rd(D/'inputs.json.gz');out={}
    dump('frozen-models.json',{k:{x:v[x] for x in ('features','coef','intercept')} for k,v in models.items()})
    for q,z in rows.items():
        arms={};resident={}
        for m in MODES:
            cur={};pol=baseline(m) if m not in models else None
            for i,p in enumerate(z['prev']):
                if m in models:cur=select(cur,rows[p],i,models[m],m=='graph')
                else:cur=baseline_write(pol,m,rows[p])
            arms[m]=retention(cur,z);resident[m]=sorted(cur)
        out[q]=dict(repo=z['repo'],issue=z['issue'],total=z['total'],within=z['within'],prior=len(z['prev']),arms=arms,residents=resident)
    dump('outcomes.json.gz',out);group=collections.defaultdict(list)
    for q,z in out.items():group[z['repo']].append(q)
    names=sorted(group);n=len(names);bs=np.random.default_rng(501271).multinomial(n,np.full(n,1/n),size=20000)
    den=np.array([sum(out[q]['total'] for q in group[k]) for k in names]);dups=sum(z['within'] for z in out.values())
    totals={m:np.array([sum(out[q]['arms'][m][1] for q in group[k]) for k in names]) for m in MODES};stats={}
    for m,v in totals.items():
        dif=totals['graph']-v
        stats[m]=dict(hits=sum(z['arms'][m][0] for z in out.values()),saved=int(v.sum()),net=int(den.sum()-dups-v.sum()),diff=int(dif.sum()),
            delta=dif.sum()/den.sum(),macro_delta=float(np.mean(dif/den)),ci=np.quantile((bs@dif)/(bs@den),[.025,.975]).tolist(),
            repo_wins=int((dif>0).sum()),repo_losses=int((dif<0).sum()))
    per_repo={r:dict(states=len(qs),total=sum(out[q]['total'] for q in qs),arms={m:sum(out[q]['arms'][m][1] for q in qs) for m in MODES}) for r,qs in group.items()}
    dump('results.json',dict(states=len(out),repo_count=n,total=int(den.sum()),within=dups,per_repo=per_repo,stats=stats,
        source=sha(D/'inputs.json.gz'),forecasts=sha(D/'outcomes.json.gz'),model=sha(FROZEN/'models.json')))
    print('Frozen outcomes:',{m:v for m,v in stats.items() if m in ('local','frequency_cost','graph')})
if __name__=='__main__':main()

