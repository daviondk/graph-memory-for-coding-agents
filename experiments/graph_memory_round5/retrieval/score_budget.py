from common5 import *
from conditional import np
from target_io import target_rows
from collections import Counter,defaultdict
import pyarrow.parquet as pq
import pyarrow.compute as pc
def main():
    assert filehash(D/'budget_predictions.jsonl.gz')==load(D/'budget_lock.json')['pred']
    orders={(p,j):(r,o['graph']) for p,j,r,h,o in rr(R/'archive.pred.jsonl.gz')}
    paths=sorted((R/'archive_inputs').glob('*.parquet'));gold=dict(target_rows(paths));sizes={}
    for path in paths:
        panel=path.stem.rsplit('_',1)[0];offset=0
        for batch in pq.ParquetFile(path).iter_batches(batch_size=32,columns=['context']):
            c=batch.column(0);flat=pc.binary_length(pc.list_flatten(c)).to_numpy()
            off=c.offsets.to_numpy();off=off-off[0]
            for i in range(len(c)):
                key=panel,offset+i;rank=orders[key][1];y=gold[key][1]
                sizes[key]=(rank.index(y)+1,np.r_[0,np.cumsum(flat[off[i]:off[i+1]][rank])])
            offset+=len(c)
    rows=list(rr(D/'budget_predictions.jsonl.gz'));all_res={};save_rows=[]
    for k in (2,3,5):
        subset=[r for r in rows if r['allowance']==k];res={};one={};diff={}
        for arm in subset[0]['depth']:
            hit=[];size=[];read=[]
            for r in subset:
                key=r['panel'],r['idx'];n=r['depth'][arm];place,cost=sizes[key];hit.append(int(place<=n));size.append(int(cost[n]));read.append(n)
            one[arm]=np.array(hit)
            res[arm]=dict(hits=sum(hit),coverage=np.mean(hit),reads=sum(read),bytes=sum(size),mean_bytes=np.mean(size),depth=dict(Counter(read)))
        groups=np.unique([orders[r['panel'],r['idx']][0] for r in subset],return_inverse=True)[1];block=np.array([r['block'] for r in subset])
        for a in ('adaptive','empirical','count_model','linear','additive'):
            for b in (('empirical','fixed','count_model','linear','additive') if a=='adaptive' else ('fixed',)):
                v=one[a]-one[b];ci={}
                for unit,g in [('project',groups),('block',block)]:
                    cnt=np.bincount(g);s=np.bincount(g,weights=v);rng=np.random.default_rng(20261118);dist=[]
                    for _ in range(40):
                        draw=rng.integers(len(cnt),size=(250,len(cnt)));dist.extend(s[draw].sum(1)/cnt[draw].sum(1))
                    ci[unit]=np.quantile(dist,[.025,.975]).tolist()
                diff[a+'-'+b]=dict(delta=np.mean(v),ci=ci,wins=int((v>0).sum()),losses=int((v<0).sum()))
        for r in subset:
            key=r['panel'],r['idx'];place,cost=sizes[key]
            save_rows.append(dict(**r,project=orders[key][0],gold_rank=place,bytes={a:int(cost[n]) for a,n in r['depth'].items()}))
        all_res[k]=dict(n=len(subset),summary=res,contrasts=diff)
    jsonrows('budget_items.jsonl.gz',save_rows);dump('budget_results.json',dict(utc=now(),outcomes=all_res,items=filehash(D/'budget_items.jsonl.gz')))
if __name__=='__main__':main()

