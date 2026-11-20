from conditional import np
from common5 import *
from collections import defaultdict
def main():
    lock=load(D/'online_lock.json');vals={}
    for lang in ('python','java'):
        path=D/('online_'+lang+'.jsonl.gz');assert filehash(path)==lock['outputs'][lang]
        ref={(r['panel'],r['idx']):(r['project'],r['gold_rank']) for r in rr(D/'transfer_items.jsonl.gz') if r['language']==lang and r['mode']=='mixed'}
        costs={(p,j):np.r_[0,np.cumsum(np.asarray(c)[arms['graph']]+1)] for p,j,k,repo,c,_,_,arms in rr(R/'python.pred.jsonl.gz') if k==3} if lang=='python' else {}
        keys=sorted(ref);idx={key:i for i,key in enumerate(keys)};n=len(keys);gold=np.array([ref[key][1] for key in keys]);gp,g=np.unique([ref[key][0] for key in keys],return_inverse=True);cnt=np.bincount(g)
        depths=np.zeros((10,n,3),dtype=np.int8);rows_seen=set()
        for p,j,repo,seed,t,*d in rr(path):
            key=p,j;assert repo==ref[key][0];depths[seed,idx[key]]=d
        assert np.all(depths>=1)
        nums=np.random.default_rng(20261118).multinomial(len(gp),np.full(len(gp),1/len(gp)),size=10000);den=nums@cnt
        d_out={};allhits={}
        for a,d in [('fixed',np.full((10,n),3)),*[(a,depths[:,:,col]) for col,a in enumerate(('count_model','harmonic','uniform'))]]:
            hit=(d>=gold);allhits[a]=hit;per=hit.mean(1);v=(hit.astype(float)-(gold<=3)[None,:]).mean(0);sums=np.bincount(g,weights=v)
            reads=d.mean(1);match=[]
            for dbar,h in zip(reads,per):
                low=int(np.floor(dbar));mix=dbar-low;refmatch=(gold<=low).mean()*(1-mix)+(gold<=low+1).mean()*mix
                match.append(h-refmatch)
            stat=dict(coverage=per.mean(),coverage_range=[per.min(),per.max()],coverage_seeds=per.tolist(),mean_depth=reads.mean(),mean_slots=reads.mean()*n,slots_range=[reads.min()*n,reads.max()*n],delta_fixed=v.mean(),cluster_ci=np.quantile((nums@sums)/den,[.025,.975]).tolist(),delta_equal_cost=np.mean(match),strata={})
            for level in ('easy','hard'):
                sl=np.array([key[0].endswith(level) for key in keys]);stat['strata'][level]=dict(coverage=hit[:,sl].mean(),depth=d[:,sl].mean())
            if costs:
                token=np.array([sum(costs[key][di]-1 for key,di in zip(keys,draw)) for draw in d]);stat['token_mean']=token.mean()
            d_out[a]=stat
        comparisons={}
        for a in ('uniform','harmonic'):
            v=(allhits['count_model'].astype(float)-allhits[a]).mean(0);sums=np.bincount(g,weights=v)
            comparisons['count_model-'+a]=dict(delta=v.mean(),cluster_ci=np.quantile((nums@sums)/den,[.025,.975]).tolist())
        vals[lang]=dict(n=n,projects=len(gp),stats=d_out,paired=comparisons)
    dump('online_result.json',dict(utc=now(),outcomes=vals,seed_order=list(range(10))))
if __name__=='__main__':main()

