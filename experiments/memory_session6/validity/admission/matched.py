from collections import Counter,defaultdict
import itertools
from common import *
def prob(d,q,k):
    if d is None:return 0.
    if d<k:return q
    return q*sum(math.comb(d,i)*q**i*(1-q)**(d-i) for i in range(k))
def profile(keys):
    # Recency stack for evaluator only. A deployed per-key coin LRU needs at most k stored keys.
    rec=[];out=[]
    for x in keys:
        d=rec.index(x) if x in rec else None;out.append(d)
        if d is not None:rec.pop(d)
        rec.insert(0,x)
    return out
def fit(h,k,target):
    total=sum(h.values());lo=0.;hi=1.
    for _ in range(70):
        q=(lo+hi)/2
        writes=total*q-sum(n*prob(d,q,k) for d,n in h.items())
        if writes<target:lo=q
        else:hi=q
    return (lo+hi)/2
def check_formula():
    for seq in [('a','b','a','c','a','b','c','d','a'),('a','a','b','c','a','b','b')]:
        unique=sorted(set(seq));ds=profile(seq)
        for k in (1,2,4):
            for q in (.02,.3,.7,1):
                hit=[0.]*len(seq);en=[0.]*len(seq)
                for flags in itertools.product((False,True),repeat=len(unique)):
                    use={x for x,y in zip(unique,flags) if y};w=q**len(use)*(1-q)**(len(unique)-len(use));arr=[]
                    for j,x in enumerate(seq):
                        if x not in use:continue
                        if x in arr:hit[j]+=w;arr.remove(x)
                        else:en[j]+=w
                        arr.insert(0,x);arr=arr[:k]
                assert all(abs(z-prob(d,q,k))<1e-12 and abs(enter-(q-z))<1e-12 for z,enter,d in zip(hit,en,ds))
def main():
    sourcecheck();check_formula()
    if not (ROOT/'matched_design.json').exists():write('matched_design.json',dict(created=stamp(),hashes=hashes(['matched.py','MATCHED_PRELOCK.md','results.json','decisions.jsonl.gz'])))
    assert hashes(read('matched_design.json')['hashes'])==read('matched_design.json')['hashes']
    res=read('results.json')['cohorts'];split=read('design_lock.json')['split'];h=defaultdict(Counter)
    for r in rows(INPUT):
        ds=profile([v[2] for v in r['literal_calls']]);h[split[r['repo']]].update(ds)
    qs={}
    for test,train in [('A','B'),('B','A')]:
        qs[test]={str(k):{p:fit(h[train],k,res[train][f'cmd/{k}/{p}']['enrollments']) for p in ('twohit','edit_twohit')} for k in (1,2,4)}
    if (ROOT/'calibration_lock.json').exists():assert qs==read('calibration_lock.json')['q']
    else:write('calibration_lock.json',dict(created=stamp(),q=qs,design_sha=digest((ROOT/'matched_design.json').read_bytes())))
    agg=defaultdict(lambda:defaultdict(Counter))
    for r in rows(INPUT):
        c=split[r['repo']];old={};events=r['literal_calls'];ds=profile([v[2] for v in events])
        for (_,ed,cmd,ids),d in zip(events,ds):
            stale=cmd in old and old[cmd]<ed;old[cmd]=ed
            for k in (1,2,4):
                for target in ('twohit','edit_twohit'):
                    q=qs[c][str(k)][target];hit=prob(d,q,k)
                    v=Counter(hits=hit,after_edit_hits=hit*stale,enrollments=q-hit,metadata_updates=q)
                    for g in ('all',c,'repo:'+r['repo']): agg[g][f'cmd/{k}/{target}'].update(v)
    write('matched_results.json',{g:{p:dict(m) for p,m in data.items()} for g,data in agg.items()})
if __name__=='__main__':main()

