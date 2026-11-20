"""Read fixed supplementary states; score only against the original R9 outcomes."""
import base64,statistics
from collections import Counter,defaultdict
import numpy as np
from common import ROOT,R9,PANELS,load,put,verify
from ef_reader import decode
from ef_build import build,transform
from timing import measure
from grade import signif

def main():
    verify(load(ROOT/'ef_seal.json'))
    native={(p,x['task'],x['direction'],x['node']):x for p in PANELS for x in load(R9/p/'outcomes.json')}
    timelist=load(ROOT/'timing_results.json')['issues'];costs=[];rows=[]
    counted=defaultdict(Counter)
    for path in sorted((ROOT/'ef_states').rglob('*.gz')):
        x=load(path);p,t,d=x['panel'],x['issue'],x['direction'];o=load(ROOT/'old'/p/path.name)
        n=len(o['nodes']);q=load(ROOT/'future'/p/path.name)['changed'];coords=[(p,t,d,w) for w in o['nodes']]
        exact=sum((1<<i) for i,ss in enumerate(o['sets']) if bool(set(q).intersection(ss)))
        inscope=sum(1<<i for i,c in enumerate(coords) if c in native)
        flip=sum(1<<i for i,c in enumerate(coords) if c in native and native[c]['changed'])
        keys,vals,cards=transform(o)
        for r in x['states']:
            raw=base64.b64decode(r['data']);b=r['b'];s=r['salt'];out=decode(raw)(q)
            assert len(raw)==b*n and out&exact==exact
            row=dict(n=inscope.bit_count(),exact=(exact&inscope).bit_count(),extra=((out^exact)&inscope).bit_count(),missed_flips=(flip&~out).bit_count(),false_negatives=(exact&~out).bit_count())
            counted[p,t,b,s].update(row)
            rows.append([p,t,d,b,s,exact,out,r['parameters'],row])
            if r['salt']==0 and t in timelist:
                cap=b*n
                assert build(n,0,cap,keys,vals,cards)[0]==raw
                costs.append(dict(panel=p,issue=t,direction=d,b=b,write=measure(lambda:build(n,0,cap,keys,vals,cards)),read=measure(lambda:decode(raw)(q))))
    summary={};pooled=load(ROOT/'results.json')['per_issue']['pooled']
    for pn in ['pooled']+PANELS:
        chosen=[(p,t) for p,t,b,s in counted if s==0 and b==64 and (pn=='pooled' or p==pn)]
        summary[pn]={}
        for b in [64,256]:
            totals=[sum((counted[p,t,b,s] for p,t in chosen),Counter()) for s in range(32)]
            byissue={t:statistics.mean(counted[p,t,b,s]['extra'] for s in range(32)) for p,t in chosen}
            groups=[[i for i,(p,t) in enumerate(chosen) if p==group] for group in PANELS if any(p==group for p,t in chosen)]
            rng=np.random.default_rng(10097)
            ix=np.concatenate([rng.choice(g,size=(10000,len(g)),replace=True) for g in groups],axis=1)
            diffs=[(byissue[t]-pooled[str(b)]['xor_map'][t]['mean_extra'])/counted[p,t,b,0]['n'] for p,t in chosen]
            rs=[r for r in rows if r[3]==b and r[0] in {p for p,t in chosen}]
            cx=[r for r in costs if r['b']==b and r['panel'] in {p for p,t in chosen}]
            summary[pn][b]=dict(byissue=byissue,effect_ef_minus_xor=signif(diffs,ix),extra_mean=statistics.mean(r['extra'] for r in totals),extra_range=[min(r['extra'] for r in totals),max(r['extra'] for r in totals)],n=totals[0]['n'],false_negative=sum(r['false_negatives'] for r in totals),stale=sum(r['missed_flips'] for r in totals),widths=dict(Counter(r[7]['q'] for r in rs)),write_cpu_ms=statistics.median(r['write']['cpu_ns'] for r in cx)/1e6,cold_read_cpu_us=statistics.median(r['read']['cpu_ns'] for r in cx)/1e3)
    put(ROOT/'ef_graded.json.gz',dict(columns=['panel','issue','direction','b','salt','exact_mask','output','parameters','counts'],rows=rows));put(ROOT/'ef_results.json',dict(summary=summary,timing=costs))
    for b in (64,256):print(b,summary['pooled'][b])
if __name__=='__main__':main()