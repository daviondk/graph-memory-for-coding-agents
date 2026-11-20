"""Verify the sealed decisions and join with authoritative gold only after all scoring rules are locked."""
from collections import Counter,defaultdict
from itertools import combinations
from pathlib import Path
import os
for name in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS'):
    os.environ[name]='1'
import numpy as np
import pyarrow.parquet as pq

from run import D,R,R5,E,load,now,panel_name,readgz,save,sha,writegz

SEED=260619
METRICS=['hit1','hit3','hit5','mrr']
def metrics(ranks):
    r=np.asarray(ranks)
    return np.column_stack([r==1,r<=3,r<=5,np.where(np.isfinite(r),1/r,0)])
def stats(rows,cluster=True):
    arms=list(rows[0]['ranks'])
    projects,g=np.unique([r['project'] for r in rows],return_inverse=True);count=np.bincount(g);ng=len(count)
    matrices={a:metrics([r['ranks'][a] or np.inf for r in rows]) for a in arms}
    vals={a:{'hits':[int(v) for v in x[:,:3].sum(0)],'mrr':x[:,3].mean(),
             'macro':[float(np.mean(np.bincount(g,weights=c)/count)) for c in x.T]} for a,x in matrices.items()}
    ans=dict(n=len(rows),projects=ng,invalid=sum(r['invalid'] for r in rows),metrics=METRICS,items=vals)
    if not cluster:return ans
    pairs=[('full',a) for a in arms if a not in {'full','r5_graph'}]
    pairs += [('direct','r4'),('r4','bm25')]
    for a in ['semlith','unix','r5_unix','jaccard']:
        if a in arms:pairs.append(('r4',a))
    diffs={};rng=np.random.default_rng(SEED)
    # Store multiplicities for a common set of cluster bootstrap draws across all contrasts.
    weights=rng.multinomial(ng,np.full(ng,1/ng),size=10000).astype('float64')
    denom=(weights@count)[:,None]
    for a,b in pairs:
        if a not in arms or b not in arms:continue
        d=matrices[a]-matrices[b];s=np.asarray([np.bincount(g,weights=c) for c in d.T]).T
        ci=np.quantile((weights@s)/denom,[.025,.975],axis=0)
        top=d[:,0]
        diffs[a+'-'+b]=dict(delta=d.mean(0).tolist(),lo=ci[0].tolist(),hi=ci[1].tolist(),
             macro=(s/count[:,None]).mean(0).tolist(),wins=int((top>0).sum()),losses=int((top<0).sum()))
    ans['diff']=diffs
    return ans

def sign_test(rows,a,b):
    p,g=np.unique([r['project'] for r in rows],return_inverse=True)
    d=[int(r['ranks'][a]==1)-int(r['ranks'][b]==1) for r in rows]
    s=np.bincount(g,weights=d); s=s[s!=0]
    rng=np.random.default_rng(SEED);above=0;obs=abs(sum(s))
    if not len(s):return 1.
    for _ in range(100):
        v=2*rng.integers(2,size=(500,len(s)),dtype='int8')-1
        above+=int((abs(v@s)>=obs).sum())
    return (above+1)/50001

def main():
    lock=load(D/'decision_lock.json')
    assert lock['predictions']==sha(D/'decisions.jsonl.gz') and lock['fit']==sha(D/'fit_lock.json')
    assert load(D/'method_lock.json')['protocol']==sha(D/'PROTOCOL_RU.md')
    assert load(D/'fit_lock.json')['sha']==sha(D/'models.pkl')
    native=load(D/'native_decision_lock.json')
    assert native['method']==sha(D/'native_lock.json')
    external={}
    for c in native['configurations']:
        assert sha(D/c['file'])==c['sha']
        for p,i,repo,found,order in readgz(D/c['file']):external[p,i]=(repo,found,order)
    enc=load(D/'encoder_receipt.json');assert enc['pred']==sha(D/'new_encoder.jsonl.gz')
    abl=load(D/'ablation_decision_lock.json')
    assert abl['decisions']==sha(D/'ablation_decisions.jsonl.gz')
    controls={(s,p,i):(pr,n,h,q,o) for s,p,i,pr,n,h,q,o in readgz(D/'ablation_decisions.jsonl.gz')}
    am=load(D/'author/data_lock.json')
    ae=load(D/'author/encoder_receipt.json')
    assert am['base']==sha(D/'author/base_decisions.jsonl.gz')
    assert ae['pred']==sha(D/'author/new_encoder.jsonl.gz')
    keys={(r['panel'],r['idx']):r['rank'] for r in readgz(D/'author/new_encoder.jsonl.gz')}
    easy_hard={ (r['panel'],r['idx']):r['rank'] for r in readgz(D/'new_encoder.jsonl.gz') }
    assert len(easy_hard)==load(D/'data_lock.json')['n']
    # Freeze scorer text and external decisions before opening any gold.
    save('grade_lock.json',dict(utc=now(),grade=sha(D/'grade.py'),primary=sha(D/'decision_lock.json'),
         fresh_native=sha(D/'native_decision_lock.json'),fresh_unix=sha(D/'encoder_receipt.json'),
         ablation=sha(D/'ablation_decision_lock.json'),author_encoder=sha(D/'author/encoder_receipt.json'),
         author_base=sha(D/'author/data_lock.json')))
    plan=load(D/'roster.json'); targets={}
    for path,stages in plan.items():
        path=Path(path)
        if 'train' in stages:continue
        tab=pq.read_table(path,columns=['gold_snippet_index','repo_name'])
        for stage,ids in stages.items():
            for local,global_i in ids:
                key=stage,panel_name(path.stem),global_i
                assert key not in targets
                targets[key]=(int(tab.column(0)[local].as_py()),tab.column(1)[local].as_py())
    found=[]; data=[];sub=[]
    for r in readgz(D/'decisions.jsonl.gz'):
        stage,panel,idx,repo=[r[k] for k in ['stage','panel','idx','project']]
        gold,actual=targets[stage,panel,idx];assert actual==repo
        orders=r['orders']
        pr,n,h,q,ctrl=controls[stage,panel,idx]
        assert (pr,n,h,q)==(repo,r['n'],r['input_hash'],r['query_hash'])
        orders.update(ctrl)
        if stage=='fresh':
            nr,num,rank=external[panel,idx];assert nr==repo and sorted(rank)==list(range(r['n']))
            orders['semlith']=rank;found.append(num)
        ranks={a:v.index(gold)+1 if gold in v else None for a,v in orders.items()}
        row=dict(stage=stage,panel=panel,idx=idx,project=repo,n=r['n'],gold=gold,invalid=not 0<=gold<r['n'],ranks=ranks)
        data.append(row)
        if stage=='fresh' and (panel,idx) in easy_hard:
            rr=easy_hard[panel,idx];assert sorted(rr)==list(range(r['n']))
            sub.append(dict(row,stage='fresh_encoder',ranks={**ranks,'unix':rr.index(gold)+1 if gold in rr else None}))
    assert len(data)==len(targets) and len(external)==len(found) and len(sub)==len(easy_hard)
    author_items=[]
    for r in readgz(D/'author/base_decisions.jsonl.gz'):
        p,i=r['panel'],r['idx'];a=r['orders']
        if r['changed']:a['unix']=keys[p,i]
        assert set(a)=={'bm25','jaccard','full','r4','unix'} and all(sorted(v)==list(range(r['n'])) for v in a.values())
        source='archive' if p.startswith('java') else 'fresh'
        gold,repo=targets[source,p,i];assert repo==r['project']
        author_items.append(dict(stage='author',panel=p,idx=i,project=repo,n=r['n'],gold=gold,
             invalid=not 0<=gold<r['n'],ranks={k:v.index(gold)+1 if gold in v else None for k,v in a.items()}))
    assert len(author_items)==330
    writegz('paired.jsonl.gz',data+sub+author_items)
    bins=defaultdict(list); strata=defaultdict(list)
    for r in data+sub+author_items:
        k=r['stage']+'_'+r['panel'].split('_')[0];bins[k].append(r)
        strata[k+'/'+r['panel']].append(r);strata[k+'/'+r['panel'].split('_')[-1]].append(r)
    overall={k:stats(v) for k,v in bins.items()}
    full={k:stats(v,False) for k,v in strata.items()}
    hard=stats(strata['fresh_encoder_python/hard'])
    hard_author=stats(strata['author_python/hard'])
    # Pair outcomes of only one copy of every complete query-and-candidate stimulus.
    hashes={(s,p,i):h for s,p,i,repo,h,order,dup,crop,m in readgz(D/'stimulus_audit.jsonl.gz')}
    uniq={}
    for k,v in bins.items():
        one={}
        for r in sorted(v,key=lambda x:(x['panel'],x['idx'])):
            stage=r['stage']
            if stage=='fresh_encoder':stage='fresh'
            if stage=='author':continue
            h=hashes[stage,r['panel'],r['idx']]
            one.setdefault(h,r)
        if one:uniq[k]=stats(list(one.values()),False)
    coefs={
        'Java 2000, full versus R4':sign_test(bins['primary_java'],'full','r4'),
        'Java 320, full versus UniXcoder':sign_test(bins['strict_java'],'full','unix')}
    ordered=sorted(coefs,key=coefs.get);p_adj={};mx=0.
    for j,k in enumerate(ordered):
        mx=max(mx,min(1,(len(ordered)-j)*coefs[k]));p_adj[k]=mx
    repo_sets={k:{r['project'] for r in v} for k,v in bins.items()}
    overlap={a+' / '+b:len(repo_sets[a]&repo_sets[b]) for a,b in combinations(bins,2)}
    valid={k:len({(r['project'],r['idx'],r['panel']) for r in v}) for k,v in bins.items()}
    report=dict(utc=now(),seed=SEED,bootstrap=10000,sign_permutations=50000,primary_p_raw=coefs,
         primary_p_holm=p_adj,overall=overall,strata=full,deduplicated=uniq,
         fresh_encoder_hard=hard,author_encoder_hard=hard_author,project_overlap=overlap,
         unique_ids=valid,native_python_mean_returned=float(np.mean(found)),native_python_zero_returned=found.count(0),
         native_python_only_original_order=sum(n==0 for n in found),pairs_hash=sha(D/'paired.jsonl.gz'))
    save('results.json',report)
    print({k:[v['n'],v['projects'],v['items']['full']['hits'][0],v['items']['r4']['hits'][0]] for k,v in overall.items()})
    print(coefs,p_adj)
if __name__=='__main__':main()
