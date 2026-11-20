from budget import *
from collections import defaultdict
def main():
    weights=load(D/'budget_model.json')['base']['weights'];pr={}
    def probs(n):
        if n not in pr:
            r=np.arange(1,n+1);pr[n]={'count_model':monotone(soft(base(r)@weights)[:8]),'harmonic':(1/r/(1/r).sum())[:8],'uniform':np.full(min(n,8),1/n)}
        return pr[n]
    dev=list(inputs(R/'full.pred.jsonl.gz'))
    arms=('count_model','harmonic','uniform');threshold={}
    for a in arms:
        values=np.concatenate([probs(len(o[0]))[a][1:] for p,j,r,o in dev]);desired=2*len(dev);tau=float(np.partition(values,-desired)[-desired])
        threshold[a]=tau,(desired-np.count_nonzero(values>tau))/max(1,np.count_nonzero(values==tau))
    lock=load(D/'transfer_lock.json')
    drop=set(lock['rows']['python']['excluded']);all_logs=[]
    for lang in ('python','java'):
        rows=([(p,j,repo,len(cost)) for p,j,k,repo,cost,_,_,a in rr(R/'python.pred.jsonl.gz') if k==3 and repo not in drop] if lang=='python' else [(p,j,repo,len(o[0])) for p,j,repo,o in inputs(R/'archive.pred.jsonl.gz')])
        desired={}
        for p,j,repo,n in rows:
            v=probs(n);d={}
            for a,(tau,mix) in threshold.items():
                gains=v[a][1:];count=np.count_nonzero(gains>tau)
                tie=sum(int(sha(f'causal-tie|{p}|{j}|{z}')[:12],16)/(16**12)<mix for z in np.flatnonzero(gains==tau))
                d[a]=int(1+count+tie)
            desired[p,j]=d
        def generate():
            for seed in range(10):
                balance=defaultdict(int);age=defaultdict(int)
                for t,(p,j,repo,n) in enumerate(sorted(rows,key=lambda z:sha(f'causal-R5|{seed}|{z[0]}|{z[1]}'))):
                    d=desired[p,j];depth={};age[repo]+=1;cap=min(12,3*age[repo]//50)
                    for a in arms:
                        bank=balance[repo,a]+3;depth[a]=min(n,bank,max(d[a],bank-cap));balance[repo,a]=bank-depth[a]
                        assert 0<=balance[repo,a]<=cap and 1<=depth[a]<=8
                    yield [p,j,repo,seed,t,depth['count_model'],depth['harmonic'],depth['uniform']]
        jsonrows('reserve_'+lang+'.jsonl.gz',generate())
    dump('reserve_lock.json',dict(utc=now(),plan=filehash(D/'RESERVE_PROTOCOL_RU.md'),code=filehash(D/'reserve.py'),threshold=threshold,outputs={lang:filehash(D/('reserve_'+lang+'.jsonl.gz')) for lang in ('python','java')}))
if __name__=='__main__':main()

