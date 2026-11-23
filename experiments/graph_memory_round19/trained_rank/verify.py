"""Stdlib-only, independently score every selected set and table column from archived rankings."""
from collections import defaultdict
from pathlib import Path
from statistics import mean
import gzip,hashlib,json,os,sys
ROOT=Path(__file__).resolve().parent
R18=Path(os.environ.get('ISE_R18',ROOT.parents[1]/'graph_memory_round18'))
def get(p):
    raw=p.read_bytes()
    return json.loads(gzip.decompress(raw) if p.suffix=='.gz' else raw)
def sha(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def union(spans):
    g=defaultdict(list)
    for s in spans:g[s['event_id'],s['json_pointer']].append((s['char_start'],s['char_end']))
    d={}
    for k,arr in g.items():
        keep=[]
        for a,b in sorted(arr):
            if keep and keep[-1][1]>=a:keep[-1]=(keep[-1][0],max(keep[-1][1],b))
            else:keep.append((a,b))
        d[k]=keep
    return d
def compute(goal,nodes):
    ss=[s for n in nodes for s in n['source_spans']];sp=union(ss)
    hits=sum(max(0,min(b,y)-max(a,x)) for k,arr in goal.items() for a,b in arr for x,y in sp.get(k,()))
    size=sum(y-x for arr in goal.values() for x,y in arr);denom=sum(s['char_end']-s['char_start'] for s in ss)
    c=hits/size;d=hits/denom if denom else 0
    return dict(full_support=int(hits==size),coverage=c,density=d,f1=2*c*d/(c+d) if c+d else 0,tokens=sum(n['token_count'] for n in nodes),nodes=len(nodes))
def verify():
    manifest=get(ROOT/'MANIFEST_SHA256.json');assert all(sha(ROOT/n)==h for n,h in manifest.items())
    lock=get(ROOT/'forecast-seal.json');assert lock['plan']==sha(ROOT/'prediction-plan.json')
    assert all(sha(ROOT/n)==h for n,h in lock['forecasts'].items())
    cfg=get(ROOT/'prediction-plan.json');assert all(sha(ROOT/k)==v for k,v in cfg['files'].items())
    parts=get(ROOT/'split.json.gz');qs={k:{r['q'] for r in rows} for k,rows in parts.items()};ts={k:{r['t'] for r in rows} for k,rows in parts.items()}
    assert all(not (qs[a]&qs[b] or ts[a]&ts[b]) for a,b in [('train','test'),('train','dev'),('test','dev')])
    assert all(r['task_id'] in qs['train'] for r in get(ROOT/'train-pairs.json.gz'))
    gt=get(R18/'isetrace_official/gold-spans.json.gz');out={(r['arm'],r['q']):r for r in get(ROOT/'outcomes.json.gz')}
    table={r['q']:r for r in get(ROOT/'table1-rows.json.gz')};summary=get(ROOT/'results.json');allq=set()
    for n in lock['forecasts']:
        for rec in get(ROOT/n):
            q=rec['q'];assert q not in allq;allq.add(q);rr=rec['rr'];g=union(gt[q]);ix={v['node_id']:v for v in rr}
            assert len(ix)==len(rr) and len(ix)>0
            if rec['partial']:ix[rec['partial']['node_id']]=rec['partial']
            for arm,S in rec['arms'].items():
                assert len(S)==len(set(S))
                val=compute(g,[ix[k] for k in S]);r=out[arm,q]
                assert val['tokens']<=2048 and all(abs(v-r[k])<1e-12 for k,v in val.items())
            assert r['t']==rec['t'];check=table[q]
            for b in (512,1024,2048):
                used=0;pr=[]
                for node in rr:
                    if used+node['token_count']>b:break
                    pr.append(node);used+=node['token_count']
                if b==2048:assert [n['node_id'] for n in pr]==rec['arms']['prefix']
                v=compute(g,pr)['coverage'];assert abs(v-check[f'coverage_{b}'])<1e-12
            assert abs(compute(g,rr[:5])['coverage']-check['recall_5'])<1e-12
            mrr=next((1/j for j,n in enumerate(rr,1) if compute(g,[n])['coverage']>0),0.)
            assert abs(mrr-check['mrr'])<1e-12
    assert allq==set(gt)==qs['test'] and len(out)==10000
    for arm,row in summary['metrics'].items():
        rs=[r for (a,_),r in out.items() if a==arm]
        assert sum(r['full_support'] for r in rs)==row['fs_hits'] and len(rs)==row['n']
        for k in ('coverage','density','f1','tokens'):assert abs(mean(r[k] for r in rs)-row[k])<1e-12
    print(len(allq),'queries,',len(out),'selections, six paper columns and split separation verified')
if __name__=='__main__':verify()
