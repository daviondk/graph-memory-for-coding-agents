import base64,statistics
from collections import Counter,defaultdict
import numpy as np
from util12 import D,load,dump,sha,digest
from adaptive import decode,upd,MODES
from grade12 import tally
from patches import encode_patch,apply_patch
from write import SEEDS
from cpu import bench,peak
def main():
    for p,h in load(D/'adaptive_seal.json').items():assert sha(D/p)==h
    rawrows=[];groups=defaultdict(Counter);costs=[]
    for p in sorted((D/'events').glob('*.gz')):
        e=load(p);n=e['n'];t=e['task'];events=e['events'];qs=load(D/'probes'/p.name);keys=qs['keys'];now={};past={};refs=[];prev={}
        target=min((z for z in events if z['phase']==1),key=lambda z:digest('R12-cpu-event|'+t+'|'+str(z['step'])))['step']
        q=min(keys,key=lambda k:digest('R12-cpu-probe|'+t+k))
        for ev in events:
            bit=1<<ev['i'];now={w:v&~bit for w,v in now.items() if v&~bit}
            for w in ev['words']:now[w]=now.get(w,0)|bit;past[w]=past.get(w,0)|bit
            refs.append((dict(now),dict(past)))
        for step,ph,b,s,a,enc,meta in load(D/'adaptive_states'/p.name):
            raw=base64.b64decode(enc);old=prev.get((b,s,a),bytes([91,n,s,0,0,0,0,0])+bytes(n*b-8))
            fn=decode(raw);answers={w:fn(w) for w in keys}
            score=tally(answers,*refs[step],set(qs['changed_definitions']),set(qs['guaranteed_absent']),n)
            wire,rg=encode_patch(old,raw);assert apply_patch(old,wire)==raw
            score.update(wire=len(wire),changed_rep=meta['change'],bloom=int(meta['tag']==1),gcs=int(meta['tag']==2),events=1)
            groups[t,ph,b,a].update(score)
            rawrows.append([t,step,ph,b,s,a,base64.b64encode(bytes(answers[k] for k in keys)).decode(),dict(score)])
            if s==0 and step==target:
                ev=events[step];build=lambda:upd(old,ev['i'],ev['words'],a)[0];assert build()==raw
                costs.append(dict(task=t,b=b,mode=a,write=bench(build),cold=bench(lambda:decode(raw)(q)),hot=bench(lambda:fn(q)),heap=peak(build)))
            prev[b,s,a]=raw
    totals={};effects={};ids=sorted({t for t,ph,b,m in groups});ix=np.random.default_rng(12041).integers(0,len(ids),(10000,len(ids)))
    for ph in [0,1]:
        for b in [64,256]:
            for a in MODES:
                vals=sum((groups[t,ph,b,a] for t in ids),Counter())
                totals[f'{ph}/{b}/{a}']=dict(fp=vals['fp']/vals['tn_all'],chg_fp=vals['chg_fp']/vals['chg_tn'],stale=vals['stale']/max(1,vals['stale_possible']),wire=vals['wire']/vals['events'],gcs=vals['gcs']/len(SEEDS),bloom=vals['bloom']/len(SEEDS),switches=vals['changed_rep']/len(SEEDS),missed=vals['missed'],per_task={t:dict(groups[t,ph,b,a]) for t in ids})
                for comp in ['fixed_bloom','fixed_gcs']:
                    ds=np.array([groups[t,ph,b,a]['fp']/groups[t,ph,b,a]['tn_all']-groups[t,ph,b,comp]['fp']/groups[t,ph,b,comp]['tn_all'] for t in ids]);sim=ds[ix].mean(1)
                    effects[f'{ph}/{b}/{a}-{comp}']={'mean':float(ds.mean()),'lo':float(np.quantile(sim,.025)),'hi':float(np.quantile(sim,.975)),'diffs':ds.tolist()}
    ctable={}
    for b in [64,256]:
        for a in MODES:
            rs=[z for z in costs if z['mode']==a and z['b']==b]
            ctable[f'{b}/{a}']={m:statistics.median(z[m]['cpu_us'] for z in rs) for m in ['write','cold','hot']}
    dump(D/'adaptive_reads.json.gz',rawrows);dump(D/'adaptive_results.json',dict(summary=totals,effects=effects,costs=costs,timing=ctable))
if __name__=='__main__':main()