"""A new project-disjoint author-archive evaluation of the frozen R4 + identifier alignment candidate."""
from run import *
from grade import stats,sign_test

A=D/'replication'
def build_plan():
    previous={r['project'] for r in readgz(D/'decisions.jsonl.gz')}
    train=set()
    for p,spec in load(D/'roster.json').items():
        if 'train' in spec:
            proj=pq.read_table(p,columns=['repo_name']).column(0)
            train.update(proj[j].as_py() for j,i in spec['train'])
    known=previous|train;wanted={};audit={}
    for p in sorted(A.glob('python*.parquet')):
        projects=pq.read_table(p,columns=['repo_name']).column(0).to_pylist()
        counts=Counter(); ids=[]
        for j in sorted(range(len(projects)),key=lambda j:digest(f'R6-alignment-replication|{p.stem}|{j}')):
            repo=projects[j]
            if repo in known or counts[repo]>=15:continue
            counts[repo]+=1;ids.append(j)
            if len(ids)==1000:break
        wanted[p.stem]=sorted(ids);audit[p.stem]=dict(total=len(projects),eligible=sum(r not in known for r in projects),
            selected=len(ids),projects=len(counts))
    save('replication/roster.json',wanted)
    save('replication/roster_lock.json',dict(utc=now(),roster=sha(A/'roster.json'),source=sha(A/'source.json'),
        prereg=sha(A/'prereg.json'),n_prior_projects=len(previous),n_train_projects=len(train),panels=audit))
    return wanted

def one(task):
    panel,ids=task;p=A/(panel+'.parquet');allowed=set(ids)
    inc=pickle.loads((R/'models.pkl').read_bytes())[3,'graph']
    complete=pickle.loads((D/'models.pkl').read_bytes())['full']
    alignment=pickle.loads((D/'ablation_models.pkl').read_bytes())['r4_alignment']
    cols=load(D/'ablation_fit_lock.json')['cols']['r4_alignment']
    crop=author_function('repo_author_utils.py','crop_code_lines');jac=author_function('repo_author_similarity.py','jaccard_similarity');tok=Adapter()
    load_module('common','publisher_common.py');load_module('arms','publisher_arms.py');pub=load_module('repobench','publisher_repobench.py')
    xx=[];meta=[];offset=[0]
    for j,r in enumerate(rows(p,['code','context','repo_name'])):
        if j not in allowed:continue
        q=crop(r['code'],3);docs=r['context'];n=len(docs)
        base=features(q,encode(docs),3);f,ls=make(q,docs)
        xx.append(np.column_stack([base,f,ls]));offset.append(offset[-1]+n)
        orders={'jaccard':sorted(range(n),key=lambda j:jac(q,docs[j],tok),reverse=True),'bm25':pub.bm25_rank(q,docs)}
        stimulus=digest(digest(q)+''.join(sorted(digest(t) for t in docs)))
        meta.append(dict(panel=panel,idx=j,project=r['repo_name'],n=n,stimulus=stimulus,orders=orders))
    if not xx:return []
    x=np.concatenate(xx)
    scores={'r4':inc.predict_proba(x[:,:43])[:,1],'full':complete.predict_proba(x)[:,1],
       'alignment':alignment.predict_proba(x[:,cols])[:,1]}
    for row,lo,hi in zip(meta,offset[:-1],offset[1:]):
        for a,v in scores.items():row['orders'][a]=np.argsort(-v[lo:hi],kind='stable').tolist()
    return meta

def main():
    assert sha(D/'replicate.py')==load(A/'prereg.json')['source']
    wanted=build_plan();dec=[]
    with ProcessPoolExecutor(3) as pool:
        for v in pool.map(one,wanted.items()):dec.extend(v)
    writegz('replication/decisions.jsonl.gz',dec)
    save('replication/decision_lock.json',dict(utc=now(),n=len(dec),decisions=sha(A/'decisions.jsonl.gz'),
        roster=sha(A/'roster_lock.json')))
    # Gold read starts here; public archive conversion transported values without exposing them to selection or ranking.
    target={};out=[]
    for p in sorted(A.glob('python*.parquet')):
        x=pq.read_table(p,columns=['repo_name','gold_snippet_index'])
        for i in wanted[p.stem]:target[p.stem,i]=(x.column(0)[i].as_py(),x.column(1)[i].as_py())
    for r in dec:
        p=r['panel'];j=r['idx'];repo,g=target[p,j];assert repo==r['project']
        assert all(sorted(v)==list(range(r['n'])) for v in r['orders'].values())
        out.append(dict(panel=p,idx=j,project=repo,stimulus=r['stimulus'],n=r['n'],gold=g,invalid=not 0<=g<r['n'],
             ranks={a:v.index(g)+1 if g in v else None for a,v in r['orders'].items()}))
    writegz('replication/pairs.jsonl.gz',out)
    # Reuse same audited cluster code: its reference arm "full" denotes the new method under contrast.
    ref=[dict(r,ranks=dict(r['ranks'],full=r['ranks']['alignment'],original_full=r['ranks']['full'])) for r in out]
    result=stats(ref);raw=stats(out)
    sums={p:stats([r for r in ref if r['panel']==p],False) for p in wanted if wanted[p]}
    previous_stimuli={r[4] for r in readgz(D/'stimulus_audit.jsonl.gz')}
    uniq={}
    for r in ref:
        if r['stimulus'] not in previous_stimuli:uniq.setdefault(r['stimulus'],r)
    save('replication/results.json',dict(utc=now(),primary_mapping='stats.full denotes frozen r4_alignment; original_full is R6 full',
         stats=result,raw=raw,panels=sums,p=sign_test(ref,'full','r4'),unique_and_not_previously_seen=stats(list(uniq.values())),
         unique_stimuli=len({r['stimulus'] for r in ref}),overlap_previous_stimuli=sum(r['stimulus'] in previous_stimuli for r in ref),
         pairs_sha=sha(A/'pairs.jsonl.gz')))
    print('external evaluation',result['n'],result['projects'],result['items']['full'],result['items']['r4'],flush=True)
if __name__=='__main__':main()
