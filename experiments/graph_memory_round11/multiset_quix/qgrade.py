from qutil import Q,R9,R10,sha,put,load
import numpy as np
from collections import Counter,defaultdict
import statistics
from grade import signif

def main():
    for p,h in load(Q/'read_seal.json').items():assert sha(Q/p)==h
    tasks={};counts=defaultdict(Counter);perdir=[];tb={};floor=[]
    for p in sorted((Q/'old').glob('*.gz')):
        old=load(p);f=load(Q/'future'/p.name);sets=old['sets'];query=set(f['changed'])
        truth=sum(1<<i for i,a in enumerate(sets) if set(a)&query)
        flips=sum(1<<i for i,(a,b) in enumerate(f['labels']) if a!=b)
        union=set().union(*(set(a) for a in sets));missed=[old['names'][i] for i in range(len(sets)) if (flips&~truth)&1<<i]
        d=dict(task=old['task'],direction=old['direction'],n=len(sets),exact=truth.bit_count(),changed=flips.bit_count(),missed=missed,old_unique_lines=len(union),max_line=max(union),q=len(query),q_in_old=len(union&query),insertions=sum(o[0]=='insert' for o in f['operations']),operations=len(f['operations']))
        perdir.append(d);tasks[old['task'],old['direction']]=(len(sets),truth,flips)
    raw=load(Q/'readouts.json.gz');methods=sorted({r[4] for r in raw})
    for t,d,b,s,a,pred,capacity,meta in raw:
        n,truth,flips=tasks[t,d];assert capacity==n*b and pred&truth==truth
        counts[t,b,s,a].update(n=n,extra=(pred^truth).bit_count(),reruns=pred.bit_count(),stale=(flips&~pred).bit_count(),false_negative=(truth&~pred).bit_count(),flips=flips.bit_count(),exact=truth.bit_count())
        if a=='exact' and b==16 and s==0:floor.append(dict(task=t,direction=d,n=n,minimum=min(meta['dense'],meta['sparse']),dense=meta['dense'],sparse=meta['sparse'],fits=meta['exact_fits']))
    ids=sorted({t for t,d in tasks});rng=np.random.default_rng(11073);idx=rng.choice(len(ids),size=(10000,len(ids)),replace=True)
    for b in [16,64,256]:
        tb[b]={}
        for a in methods:
            vals=[sum((counts[t,b,s,a] for t in ids),Counter()) for s in range(32)]
            df=[statistics.mean((counts[t,b,s,a]['extra']-counts[t,b,s,'exact']['extra'])/counts[t,b,s,a]['n'] for s in range(32)) for t in ids]
            tb[b][a]={k:statistics.mean(row[k] for row in vals) for k in ['extra','stale','reruns','n','flips','exact','false_negative']}
            tb[b][a]['extra_by_salt']=[v['extra'] for v in vals]
            tb[b][a]['issue_effect_vs_exact']=signif(df,idx)
            tb[b][a]['by_issue']={t:{k:statistics.mean(counts[t,b,s,a][k] for s in range(32)) for k in ['extra','stale']} for t in ids}
    put(Q/'results.json',dict(summary=tb,directions=perdir,exact_serialized=floor,independent_algorithms=len(ids)))
    for b in [16,64,256]:print(b,[(m,tb[b][m]['extra'],tb[b][m]['stale']) for m in methods])
    print('n',tb[256]['exact']['n'],'flip',tb[256]['exact']['flips'],'rerun',tb[256]['exact']['reruns'])
if __name__=='__main__':main()