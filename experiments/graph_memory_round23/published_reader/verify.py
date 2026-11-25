"""Portable verification using the checked-in suite and the shared annotated spans only."""
from pathlib import Path
import gzip
import hashlib
import json
import sys
from collections import defaultdict
import numpy as np
from scipy.stats import binomtest
D=Path(__file__).resolve().parent
def read(f):return json.loads(gzip.decompress(f.read_bytes()) if f.suffix=='.gz' else f.read_bytes())
def digest(f):return hashlib.sha256(f.read_bytes()).hexdigest()
def groups(rows):
    mapped=defaultdict(list)
    for event,key,a,b in rows:mapped[event,key].append((a,b))
    out={}
    for k,raw in mapped.items():
        spans=[]
        for l,h in sorted(raw):
            if spans and spans[-1][1]>=l:spans[-1]=(spans[-1][0],max(h,spans[-1][1]))
            else:spans.append((l,h))
        out[k]=spans
    return out
def coverage(truth,got):
    den=sum(b-a for seq in truth.values() for a,b in seq)
    retrieved=sum(b-a for seq in got.values() for a,b in seq)
    n=sum(max(0,min(b,y)-max(a,x)) for k,seq in got.items() for a,b in seq for x,y in truth.get(k,()))
    recall=n/den;prec=n/retrieved if retrieved else 0.
    return int(n==den),recall,prec,(2*recall*prec/(recall+prec) if prec+recall else 0.),retrieved
def check(stage):
    root=D.parents[1];base=root/'graph_memory_round19/write_transfer' if stage=='dev' else root/'graph_memory_round18/isetrace_official'
    plan=read(D/'plan.json');sel=plan['selection'][stage]
    groupset=defaultdict(list);split=read(root/'graph_memory_round22/native_multiseed/official580/split.json.gz')[stage]
    for row in (split[:500] if stage=='dev' else split):groupset[row['t']].append(row['q'])
    def order(label,s):return hashlib.sha256(f'r23-verbatim-{label}-v1|{stage}|{s}'.encode()).hexdigest()
    expect=[{'t':t,'q':min(groupset[t],key=lambda s:order('query',s))} for t in sorted(groupset,key=lambda s:order('traj',s))[:len(sel)]]
    assert expect==sel and len(sel)==(4 if stage=='dev' else 192)
    inputs=read(D/f'{stage}-inputs.json');seal=read(D/f'{stage}-seal.json');res=read(D/f'{stage}-results.json');details=read(D/f'{stage}-outcomes.json.gz')
    for obj,tag in [(seal['inputs'],f'{stage}-inputs.json'),(res['per_query'],f'{stage}-outcomes.json.gz'),(inputs['plan'],'plan.json'),(res['seal'],f'{stage}-seal.json')]:assert obj==digest(D/tag)
    gold=read(base/'gold-spans.json.gz');assert res['gold']==digest(base/'gold-spans.json.gz')
    matrix={};detail_by={r['q']:r for r in details}
    for s in sel:
        q=s['q'];path=D/'forecasts'/stage/f'{q[6:]}.json.gz';record=read(path)
        assert digest(path)==seal['files'][q] and record['t']==s['t'] and inputs['subset'][q]['sha']==record['input']
        ad=record['ad'];truth=groups([(x['event_id'],x['json_pointer'],x['char_start'],x['char_end']) for x in gold[q]])
        for a,z in record['picks'].items():
            coords=groups([(*ad[e],l,h) for e,l,h in z['spans']]);m=coverage(truth,coords);src=detail_by[q]['scores'][a]
            assert len(z['spans'])==0 if not m[4] else len(z['spans'])>0
            assert np.allclose(m,[src[k] for k in ('full','coverage','density','f1','chars')],atol=1e-12,rtol=0)
            assert z['tokens']==src['tokens']<=2048
            matrix[q,a]=[*m[:4],z['tokens']]
    for a,m in res['measures'].items():
        assert np.allclose(np.mean([matrix[q,a] for q in sorted(detail_by)],axis=0),[m[k] for k in ('full','coverage','density','f1','tokens')],atol=1e-12,rtol=0)
    for name,stat in res['contrasts'].items():
        a,b=name.split('-');diff=np.array([np.array(matrix[q,a])-matrix[q,b] for q in sorted(detail_by)]);rng=np.random.default_rng(13)
        samples=np.vstack([diff[rng.integers(0,len(diff),size=(100,len(diff)))].mean(axis=1) for _ in range(100)])
        lohi=np.quantile(samples,[.025,.975],axis=0);ci=np.array([stat['diff'][k]['ci95'] for k in ('full','coverage','density','f1','tokens')])
        assert np.allclose(lohi.T,ci,atol=1e-12,rtol=0)
        win=int((diff[:,0]>0).sum());lose=int((diff[:,0]<0).sum())
        assert win==stat['wins'] and lose==stat['losses']
        assert abs(stat['mcnemar_two_sided']-(binomtest(win,win+lose,.5).pvalue if win+lose else 1.))<1e-12
    print(stage,len(sel),len(res['measures']),len(res['contrasts']),'verified')
if __name__=='__main__':
    for stage in (sys.argv[1:] or ['dev','test']):check(stage)
