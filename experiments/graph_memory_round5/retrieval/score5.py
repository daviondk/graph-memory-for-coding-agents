"""Independent scoring process. Open test labels only with a signed prediction receipt."""
from conditional import np
from common5 import *
from target_io import target_rows
from collections import defaultdict
import sys
def stats(rows,contrasts):
    group,idx=np.unique([r['project'] for r in rows],return_inverse=True);g=len(group);ns=np.bincount(idx)
    metrics={};values={}
    for m in rows[0]['ranks']:
        v=np.array([r['ranks'][m] for r in rows]);x=np.column_stack([v==1,v<=3,v<=5,1/v])
        s=np.stack([np.bincount(idx,weights=t) for t in x.T],axis=1)
        metrics[m]=dict(hits=[int(i) for i in x[:,:3].sum(0)],micro=x.mean(0).tolist(),macro=(s/ns[:,None]).mean(0).tolist())
        values[m]=(v,x,s)
    rng=np.random.default_rng(20261118);boot=rng.multinomial(g,np.full(g,1/g),size=10000)
    signs=2*rng.integers(2,size=(50000,g),dtype=np.int8)-1
    bs_n=boot@ns
    result={}
    for a,b in contrasts:
        va,xa,sa=values[a];vb,xb,sb=values[b];dif=sa-sb;v=xa-xb
        bootstrap=(boot@dif)/bs_n[:,None];ci=np.quantile(bootstrap,[.025,.975],axis=0).T
        obs=int(dif[:,0].sum());pos=int((v[:,0]>0).sum());neg=int((v[:,0]<0).sum())
        perm=((abs(signs@dif[:,0])>=abs(obs)).sum()+1)/50001
        result[a+'-'+b]=dict(difference=v.mean(0).tolist(),cluster_ci=ci.tolist(),top1_wins=pos,top1_losses=neg,top1_signflip_p=perm,rank_better=int((va<vb).sum()),rank_worse=int((va>vb).sum()))
    return dict(n=len(rows),projects=g,metrics=metrics,contrasts=result)
def main(tag):
    assert tag in ('rank','neural')
    # The previously frozen weights bind the neural experiment even if an archive aggregate is read first.
    neural_lock=load(D/'neural_devlock.json')
    assert neural_lock['sha']==filehash(D/'neural_preregistered_weights.json')
    pred=D/(tag+'_predictions.jsonl.gz');lock=load(D/(tag+'_decisions.json'))
    assert filehash(pred)==lock['pred']
    if tag=='rank':
        assert load(D/'ranking_lock.json')['hashes']['target_io.py']==filehash(D/'target_io.py')
    else:
        assert lock['weights']==neural_lock['sha']
        assert neural_lock['inference']==filehash(D/'neural_rank.py') and neural_lock['features']==filehash(D/'graph_data.py')
    gold=dict(target_rows((R/'archive_inputs').glob('*.parquet')))
    by=defaultdict(list);rows=[];ids=set()
    for p in rr(pred):
        panel,j,k=p['panel'],p['idx'],p['query'];name,y=gold[panel,j]
        assert name==p['project'] and (panel,j,k) not in ids
        ids.add((panel,j,k));n=len(p['orders']['graph']);assert 0<=y<n
        assert all(sorted(v)==list(range(n)) for v in p['orders'].values())
        ranks={m:o.index(y)+1 for m,o in p['orders'].items()}
        record=dict(panel=panel,idx=j,query=k,project=name,candidates=n,gold=y,ranks=ranks)
        by[k].append(record);rows.append(record)
    assert len(rows)=={'rank':36000,'neural':448}[tag]
    jsonrows(tag+'_items.jsonl.gz',rows)
    contrasts=([('adaptive','linear'),('adaptive','additive'),('adaptive','placebo'),('adaptive','graph'),('adaptive','without_graph'),('linear','graph'),('additive','graph')] if tag=='rank' else [('edge','direct'),('edge','placebo'),('edge','no_encoder'),('direct','no_encoder'),('edge','graph'),('direct','graph'),('edge','unix'),('direct','graph_unix_rrf0')])
    summaries={}
    for k,data in by.items():
        summary=stats(data,contrasts)
        strata={}
        for panel in sorted({r['panel'] for r in data}):
            sub=[r for r in data if r['panel']==panel];strata[panel]={m:sum(z['ranks'][m]==1 for z in sub) for m in data[0]['ranks']};strata[panel]['n']=len(sub)
        summary['stratum_top1']=strata;summaries[k]=summary
    dump(tag+'_result.json',dict(utc=now(),metrics=['top1','top3','top5','MRR'],items=filehash(D/(tag+'_items.jsonl.gz')),by_query=summaries))
if __name__=='__main__':main(sys.argv[1])

