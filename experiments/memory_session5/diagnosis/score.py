import csv,gzip,itertools,json,math
from collections import defaultdict
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parent

def score():
    source=json.loads(gzip.decompress((ROOT/'cycles.json.gz').read_bytes()))
    outcomes={(s,r['id']):dict(r['tests']) for s,rs in source.items() for r in rs}
    rows=[]
    with gzip.open(ROOT/'rankings.jsonl.gz','rt') as f:
        for line in f:
            r=json.loads(line);y=outcomes[r['sys'],r['id']]
            for m,md in r['methods'].items():
                ranking=md['rank'];out=[y[i] for i in ranking];k=math.ceil(.1*len(out));total=sum(out)
                rank_sum=sum(i+1 for i,v in enumerate(out) if v)
                rows.append({'sys':r['sys'],'id':r['id'],'m':m,'opportunities':len(out),'k':k,'failures':total,'hits':sum(out[:k]),'recall':sum(out[:k])/total if total else None,'apfd':1-rank_sum/(len(out)*total)+.5/len(out) if 0<total<len(out) else None})
    return rows
def summarize(rows):
    buckets=defaultdict(list)
    for r in rows:buckets[r['sys'],r['m']].append(r)
    outputs={}
    for (s,m),rs in buckets.items():
        stats={k:sum(r[k] for r in rs) for k in ('failures','hits','k','opportunities')}
        for k in ('apfd','recall'):
            vs=[r[k] for r in rs if r[k] is not None];stats[k]=np.mean(vs).item() if vs else None
        stats['sessions']=len(rs);stats['with_failure']=sum(r['failures']>0 for r in rs)
        outputs.setdefault(s,{})[m]=stats
    west=[s for s in outputs if s.startswith('system')]
    methods=sorted(outputs[west[0]])
    def means(systems):return {m:np.mean([outputs[s][m]['recall'] for s in systems]).item() for m in methods}
    contrasts={}
    for other in ('recent2','surprise2','blind2','static','visible','full','conditional2','conditional-full'):
        ds=np.array([outputs[s]['aware2']['recall']-outputs[s][other]['recall'] for s in west]);rng=np.random.default_rng(17112026)
        sims=rng.choice(ds,(10000,len(ds)),replace=True).mean(axis=1)
        contrasts[other]={'delta':ds.mean().item(),'ci':np.quantile(sims,[.025,.975]).tolist(),'systems_win':int((ds>1e-12).sum()),'systems_lose':int((ds< -1e-12).sum())}
    return {'by_system':outputs,'west_macro':means(west),'abb_macro':means(['paintcontrol','iofrol']),'west_contrasts_aware2_minus':contrasts}
if __name__=='__main__':
    rows=score();d=summarize(rows)
    (ROOT/'results.json').write_text(json.dumps(d,indent=1))
    with gzip.open(ROOT/'metrics.csv.gz','wt',newline='') as fp:
        wr=csv.DictWriter(fp,fieldnames=list(rows[0]));wr.writeheader();wr.writerows(rows)
    print(json.dumps({k:v for k,v in d.items() if k!='by_system'}))
