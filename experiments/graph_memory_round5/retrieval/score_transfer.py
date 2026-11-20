from conditional import np
from common5 import *
from target_io import target_rows
from collections import defaultdict
def analyze(rows):
    n=len(rows);ids=np.unique([r['project'] for r in rows],return_inverse=True)[1];ng=ids.max()+1;cnt=np.bincount(ids)
    groups=np.random.default_rng(20261118).multinomial(ng,np.full(ng,1/ng),size=10000);den=groups@cnt
    stats={};arr={};contrasts={}
    for a in rows[0]['depth']:
        h=np.array([r['gold_rank']<=r['depth'][a] for r in rows],int);d=np.array([r['depth'][a] for r in rows]);arr[a]=h
        stat=dict(n=n,hits=h.sum(),coverage=h.mean(),reads=d.sum(),depth=d.mean())
        if rows[0].get('token_cost'):stat['total_tokens']=sum(r['token_cost'][a] for r in rows)
        stats[a]=stat
    for a in arr:
        for b in ('fixed','uniform','harmonic','count_model'):
            if a==b:continue
            v=arr[a]-arr[b];tot=np.bincount(ids,weights=v);ci=np.quantile((groups@tot)/den,[.025,.975]).tolist()
            contrasts[a+'-'+b]=dict(delta=v.mean(),ci=ci,wins=(v>0).sum(),losses=(v<0).sum())
    return dict(projects=ng,metrics=stats,contrasts=contrasts)
def main():
    assert load(D/'transfer_lock.json')['pred']==filehash(D/'transfer_predictions.jsonl.gz')
    python=dict(target_rows((D.parents[1]/'graph_memory_round3/repo/inputs').glob('python_*_test_*.parquet')))
    rank={(p,j):(o['graph'],cost) for p,j,k,proj,cost,_,_,o in rr(R/'python.pred.jsonl.gz') if k==3}
    base={(r['panel'],r['idx']):r['gold_rank'] for r in rr(D/'budget_items.jsonl.gz') if r['allowance']==3}
    grouped=defaultdict(list);records=[]
    for row in rr(D/'transfer_predictions.jsonl.gz'):
        key=row['panel'],row['idx']
        if row['language']=='python':
            repo,gold=python[key];assert repo==row['project'];o,c=rank[key]
            place=1+o.index(gold) if gold in o else len(o)+1
            seq=np.r_[0,np.cumsum(np.array(c)[o])];row['token_cost']={a:int(seq[d])+max(0,d-1) for a,d in row['depth'].items()};row['invalid']=gold not in o
        else:place=base[key]
        row['gold_rank']=place
        grouped[row['language'],row['mode']].append(row);records.append(row)
    out={}
    for (lang,mode),rows in grouped.items():
        res=analyze(rows)
        strata={}
        for g in ('easy','hard'):
            sl=[r for r in rows if r['panel'].endswith(g)];strata[g]={a:dict(coverage=sum(r['gold_rank']<=r['depth'][a] for r in sl)/len(sl),depth=sum(r['depth'][a] for r in sl)/len(sl)) for a in sl[0]['depth']}
        res['strata']=strata
        if mode=='level':assert all(abs(v['depth']-3)<1e-12 for ci in strata.values() for v in ci.values())
        out[lang+'-'+mode]=res
    jsonrows('transfer_items.jsonl.gz',records)
    dump('transfer_results.json',dict(utc=now(),items=filehash(D/'transfer_items.jsonl.gz'),groups=out))
if __name__=='__main__':main()

