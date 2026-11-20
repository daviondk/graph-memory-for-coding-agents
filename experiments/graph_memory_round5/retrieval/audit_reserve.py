from common5 import *
from conditional import np
from collections import Counter
def main():
    lock=load(D/'reserve_lock.json');rows=load(D/'reserve_result.json')['outcomes'];out={}
    assert lock['threshold']==load(D/'online_lock.json')['threshold']
    refs={'java':{},'python':{}}
    for z in rr(D/'transfer_items.jsonl.gz'):
        if z['mode']=='mixed':refs[z['language']][z['panel'],z['idx']]=z['gold_rank']
    for lang,path in lock['outputs'].items():
        p=D/('reserve_'+lang+'.jsonl.gz');q=D/('online_'+lang+'.jsonl.gz')
        assert filehash(p)==path
        age=Counter();bank=Counter();deltas=Counter();nobs=Counter()
        for r,old in zip(rr(p),rr(q),strict=True):
            assert r[:5]==old[:5];panel,j,repo,seed,t,*depth=r
            key=repo,seed;age[key]+=1;cap=min(12,3*age[key]//50)
            for a,x in enumerate(depth):
                k=(repo,seed,a);bank[k]+=3-x;assert 0<=bank[k]<=cap
            g=refs[lang][panel,j];deltas[repo]+=int(g<=depth[0])-int(g<=old[5]);nobs[repo]+=1
        groups=list(nobs);sums=np.array([deltas[g]/10 for g in groups]);n=np.array([nobs[g]/10 for g in groups]);draw=np.random.default_rng(20261118).multinomial(len(n),np.full(len(n),1/len(n)),size=10000)
        out[lang]=dict(difference=sums.sum()/n.sum(),cluster_ci=np.quantile((draw@sums)/(draw@n),[.025,.975]).tolist(),small_projects=int((n<=16).sum()),small_events=int(n[n<=16].sum()),always_constant=int(np.minimum(n,16).sum()),projects=len(n),rows=n.sum())
    dump('reserve_audit.json',dict(utc=now(),effects_vs_old=out,validated=True))
if __name__=='__main__':main()

