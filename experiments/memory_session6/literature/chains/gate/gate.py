"""Causal gated lexical evidence, counterfactual permuted control, and exact decision lock."""
from pathlib import Path
import sys
BASE=Path(__file__).resolve().parent
CUE=BASE.parent/'cue'
sys.path.insert(0,str(CUE))
from common import digest,load,save
from predict import online_records,lexical_scores
METHODS=('recency','path','global','gate','blind')

def choose(r):
    cache,records,_,_,_=online_records(r['history'])
    q=set(r['query']);pval=lexical_scores(records,q,'path')
    recent=lambda p:(-cache[p][0],p)
    best=max(pval.values());top=sorted((p for p,s in pval.items() if s==best),key=recent)
    def pick(vals):return min(vals,key=lambda p:(-vals[p],*recent(p)))
    # It is a read-count comparison of five separately deployable rules.
    total_words=sum(len(v['stable8']) for v in records.values())
    global_score=lexical_scores(records,q,'stable8')
    methods={
        'path':dict(choice=top[0],records=0,ids=0),
        'recency':dict(choice=min(records,key=recent),records=0,ids=0),
        'global':dict(choice=pick({p:pval[p]+global_score[p] for p in records}),records=len(records),ids=total_words)}
    literal=any(q.intersection(v['path']) for v in records.values())
    base=dict(positive=best>0,any_literal_path_overlap=literal,unique=len(top)==1)
    if len(top)>1:
        considered={p:records[p] for p in top}
        score=lexical_scores(considered,q,'stable8')
        order=sorted(top,key=lambda p:digest(('cue-gate-blind-v1|'+r['issue']+'|'+p).encode()))
        deranged={p:order[(i+1)%len(order)] for i,p in enumerate(order)}
        assert all(p!=m for p,m in deranged.items())
        blinded={p:score[deranged[p]] for p in top}
        budget=sum(len(records[p]['stable8']) for p in top)
        methods['gate']=dict(choice=pick(score),records=len(top),ids=budget)
        methods['blind']=dict(choice=pick(blinded),records=len(top),ids=budget)
        base.update(distinct_cues=len({tuple(sorted(records[p]['stable8'])) for p in top}),discriminates=len(set(score.values()))>1)
    else:
        methods['gate']=dict(choice=top[0],records=0,ids=0);methods['blind']=dict(methods['gate'])
        base.update(distinct_cues=None,discriminates=False)
    return dict(cohort=r['cohort'],repo=r['repo'],issue=r['issue'],sequence=r['sequence'],prefix=r['prefix'],
                shared_main_repo=r['shared_main_repo'],previously_in_main_history=r['previously_in_main_history'],
                candidates=sorted(cache),top=top,methods=methods,**base)

def main():
    features=load(BASE/'features.json.gz');sources=load(BASE/'sources.json')
    assert digest((BASE/'features.json.gz').read_bytes())==sources['source_features_sha256']
    old={(r['repo'],r['issue']):r for r in load(CUE/'decisions.json.gz')}
    rows=[choose(r) for r in features]
    for r in rows:
        if r['cohort']=='original':
            orig=old[r['repo'],r['issue']]
            assert r['methods']['path']['choice']==orig['methods']['path']['choice']
            assert r['methods']['global']['choice']==orig['methods']['stable8']['choice']
        assert r['methods']['gate']['choice'] in r['top'] and r['methods']['blind']['choice'] in r['top']
    save(BASE/'decisions.json.gz',rows)
    import collections
    n=dict(collections.Counter(r['cohort'] for r in rows))
    save(BASE/'decision_lock.json',dict(counts=n,methods=list(METHODS),sha256={f:digest((BASE/f).read_bytes()) for f in ('PROTOCOL.md','sources.py','gate.py','sources.json','features.json.gz','decisions.json.gz')},
            cue_code={f:digest((CUE/f).read_bytes()) for f in ('predict.py','common.py','project_cues.py')},writer=digest((CUE.parent/'write'/'retain.py').read_bytes())))
    print('Locked without target patches:',n)

if __name__=='__main__':main()
