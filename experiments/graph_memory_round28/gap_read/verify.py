"""Recompute paid strings, support, once-vs-repeat coverage, and paired primary intervals."""
from collections import defaultdict
from store import *
import importlib.util
import numpy as np
spec=importlib.util.spec_from_file_location('r25_gold_for_replay',R25/'analyse.py');goldmod=importlib.util.module_from_spec(spec);spec.loader.exec_module(goldmod)
def group(items):
    by=defaultdict(list)
    for e,l,h in items:
        if l<h:by[e].append((l,h))
    ret={}
    for e,sp in by.items():
        cur=[]
        for l,h in sorted(sp):
            if cur and cur[-1][1]>=l:cur[-1]=(cur[-1][0],max(cur[-1][1],h))
            else:cur.append((l,h))
        ret[e]=cur
    return ret
def total(x):return sum(h-l for spans in x.values() for l,h in spans)
def intersect(a,b):
    return sum(max(0,min(h,z)-max(l,y)) for e,s in a.items() for l,h in s for y,z in b.get(e,()))
def check(name):
    seal=read(D/f'{name}-seal.json');results=read(D/f'{name}-results.json')
    f=D/f'{name}-forecasts.json.gz';assert sha(f)==seal['rows'] and results['forecast']==sha(D/f'{name}-seal.json')
    c=open_db();t=source.c.tok() if name=='mdd' else source.Tokenizer.from_file(str(source.TOK))
    inp=read(R25/f'{name}-choices.json.gz');native=read(R25/f'{name}-opened.json.gz')
    gold=goldmod.targets(name,inp);rowpath=D/f'{name}-outcomes.json.gz';assert sha(rowpath)==results['per_query']
    met={r['q']:r for r in read(rowpath)};checked=0;votes=defaultdict(list);different={'online':0,'equal':0}
    for q,z in read(f).items():
        orig=inp[q];valid=[group(k) for k in gold[q]];vis=group(orig['base']);r=met[q];cut=orig['cut']
        txt=c.execute('select body from fields where ds=? and t=? and e=?',(name,str(r['t']),cut['e'])).fetchone()[0] if cut else ''
        assert z['arms']['both']==native[q]['arms']['both']
        def verify(op,m,novel):
            spans=[(e,l,h) for e,l,h,*_ in op];address=group(spans)
            wire='\n'.join(f'[{e}:{anchor}] '+txt[l:h] for e,l,h,n,anchor,side,nh in op);paid=len(t.encode(wire,add_special_tokens=False).ids)
            assert paid==m['tokens']<=256 and len(op)==m['requests']
            got=group(orig['base']+[list(k) for k in spans]);cov=max(intersect(got,g)/total(g) for g in valid)
            twice=intersect(address,vis)
            assert cov==m['coverage'] and int(cov==1)==m['full'] and twice==m['already'] and total(address)==m['output_chars']
            if novel:assert not twice and len(op)<=6
        for a,op in z['arms'].items():verify(op,r['arms'][a],a!='both');checked+=1
        for a,(x,y) in z['eq'].items():
            m,n=r['eq'][a];assert m['tokens']==n['tokens']
            verify(x,m,True);verify(y,n,a!='both');checked+=2
        votes[r['t']].append(r['eq']['window'][0]['full']-r['eq']['window'][1]['full'])
        different['online']+=z['arms']['gap']!=z['arms']['window'];different['equal']+=z['eq']['window'][0]!=z['eq']['window'][1]
    c.close();keys=sorted(votes);ns=np.array([len(votes[k]) for k in keys]);tot=np.array([sum(votes[k]) for k in keys]);rng=np.random.default_rng(263117);draw=[]
    for _ in range(200):
        ix=rng.integers(len(ns),size=(100,len(ns)));draw.extend(tot[ix].sum(axis=1)/ns[ix].sum(axis=1))
    contrast=results['paired']['window-equal']['metrics']['full']
    assert np.allclose(np.quantile(draw,[.025,.975]),contrast['ci95'],atol=1e-12,rtol=0)
    assert abs(tot.sum()/ns.sum()-contrast['delta'])<1e-12
    return {'queries':len(met),'groups':len(keys),'individual_outcomes':checked,'exact_pairs':2*len(met),'actual_different_gap_window':different,'results':sha(D/f'{name}-results.json')}
if __name__=='__main__':save(D/'verified.json',{s:check(s) for s in ('ise','mdd')})
