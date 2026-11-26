"""Independent witness of DPP choices from direct determinants and every full-ranking invariant."""
from core import *
def main():
    pred=read(D/'forecasts.json.gz');seal=read(D/'forecast-seal.json');grams=read(D/'check-grams.json.gz');assert seal['data']==sha(D/'forecasts.json.gz')
    count=0;comparisons=0
    for q,r in pred.items():
        ranks=r['rank'];n=len(r['ids']);orig=ranks['qwen'];obs=set(i for i,v in enumerate(r['seen']) if v);assert orig==ranks['dpp_0']
        for m,x in ranks.items():
            assert sorted(x)==list(range(n))
            if 'mask' in m or m in ('history','historic_static'):assert all(not r['seen'][i] for i in x[:n-len(obs)])
        if not obs:assert ranks['dpp_mask']==ranks['history']==ranks['dpp']
        if q not in grams:continue
        G=np.asarray(grams[q]);assert hashlib.sha256(G.astype('<f8').tobytes()).hexdigest()==r['grams']
        for name,beta,start in (('dpp',.8,[]),('dpp_05',.5,[]),('dpp_095',.95,[]),('history',.8,list(obs))):
            ker=(1-beta)*np.eye(n)+beta*G;chosen=list(start)
            for i in ranks[name][:min(8,n-len(start))]:
                rem=[j for j in range(n) if j not in chosen];vals=[]
                for j in rem:
                    a=chosen+[j];sign,logdet=np.linalg.slogdet(ker[np.ix_(a,a)]);assert sign>0
                    vals.append(logdet-np.log(orig.index(j)+1))
                best=max(vals);assert best-vals[rem.index(i)]<1e-9
                comparisons+=len(rem);count+=1;chosen.append(i)
    print('Validated all complete rankings and',count,'steps against direct candidate determinants in',comparisons,'comparisons.')
    return count,comparisons
if __name__=='__main__':main()
