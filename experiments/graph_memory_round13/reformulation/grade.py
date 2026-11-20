"""Evaluate frozen per-prefix rankings on navigation and separately on actual old->merge changed files."""
from collections import Counter, defaultdict
import json,math,random,statistics
from prefix import D,get,save,h,enc
from navigation import verify_lock
METHODS=('last_read','last_scope','bm25','strong','graph','shuffled')
def point(rank):
    return (float(rank==1),float(0<rank<=3),1/rank if rank else 0.)
def quantile(xs,q):
    a=sorted(xs);z=(len(a)-1)*q;l=int(z);frac=z-l
    return a[l]*(1-frac)+a[min(l+1,len(a)-1)]*frac
def one(row,ranks,target,endpoint):
    tgt=set(target);candidates=set(row['docs']);mp={}
    for m,lst in ranks.items():
        assert set(lst)==candidates and len(lst)==len(candidates)
        mp[m]=next((i+1 for i,p in enumerate(lst) if p in tgt),0)
    return {'id':row['id'],'iid':row['iid'],'repo':row['repo'],'which':endpoint,'targets':sorted(tgt),'n_candidates':len(candidates),'reachable':bool(candidates&tgt),'rank':mp}
def ag(rows):
    n=len(rows)
    scores={}
    for m in METHODS:
        ranks=[r['rank'][m] for r in rows]
        scores[m]={'h1':sum(p==1 for p in ranks),'h3':sum(0<p<=3 for p in ranks),'mrr':sum(1/p for p in ranks if p)/n if n else None}
    return {'n':n,'tasks':len(set(r['iid'] for r in rows)),'repos':len(set(r['repo'] for r in rows)),'ceiling':sum(r['reachable'] for r in rows),'score':scores}
def contrast(rows,other):
    group=defaultdict(list);n=len(rows)
    for r in rows:
        a=point(r['rank']['graph']);b=point(r['rank'][other]);group[r['iid']].append(tuple(i-j for i,j in zip(a,b)))
    vals=[v for g in group.values() for v in g];units=[(len(g),*(sum(v[i] for v in g) for i in range(3))) for g in group.values()]
    rng=random.Random(301754);bs=[[] for _ in range(3)]
    for j in range(5000):
        sampled=rng.choices(units,k=len(units));s=[sum(k) for k in zip(*sampled)]
        for i in range(3):bs[i].append(s[i+1]/s[0])
    return {key:{'mean_delta':sum(v[i] for v in vals)/n,'wins':sum(v[i]>0 for v in vals),'losses':sum(v[i]<0 for v in vals),'ties':sum(v[i]==0 for v in vals),'ci95_cluster_task':[quantile(bs[i],.025),quantile(bs[i],.975)]} for i,key in enumerate(('h1','h3','mrr'))}
def main():
    verify_lock();inputs=get('inputs.json.gz');pred={r['id']:r for r in get('frozen_rankings.json.gz')};nl={r['id']:r for r in get('navigation_labels.json.gz')};pr={r['iid']:r for r in get('patch_labels.json.gz')};split=get('input.lock.json')['split']
    all_rows=[];overlap=Counter();statuses=Counter()
    for row in inputs:
        key=row['id'];rnk=pred[key]['rank'];n=nl[key];g=pr[row['iid']]
        if n['target']:
            all_rows.append(one(row,rnk,[n['target']['path']],'next'))
        if n['plain']:
            all_rows.append(one(row,rnk,[n['plain']['path']],'plain'))
        statuses['unavailable' if g['status']!='ok' else 'direct' if g['strict'] else 'not_direct']+=1
        if g['status']=='ok' and g['strict']:
            if g['prod']:
                all_rows.append(one(row,rnk,g['prod'],'patch'))
                if n['target']:
                    overlap['joint']+=1
                    if n['target']['path'] in g['prod']:overlap['next_was_production_change']+=1
            else:statuses['direct_with_no_production_change']+=1
            if g['all_py']:all_rows.append(one(row,rnk,g['all_py'],'patch_all_py'))
    save('per_anchor_scores.json.gz',all_rows)
    summaries={};pairs={}
    first={};[first.setdefault(r['iid'],r['id']) for r in inputs]
    for end in ('next','plain','patch','patch_all_py'):
        grp=[r for r in all_rows if r['which']==end]
        sets={'all':grp,'external':[r for r in grp if r['repo'] in split['external']],'dev':[r for r in grp if r['repo'] in split['dev']],'first_per_task':[r for r in grp if first[r['iid']]==r['id']],'reachable':[r for r in grp if r['reachable']]}
        summaries[end]={label:ag(vals) for label,vals in sets.items()}
        if end in ('next','patch'):
            pairs[end]={subset:{m:contrast(v,m) for m in ('strong','last_scope','shuffled')} for subset,v in sets.items() if subset in ('all','external')}
    bytes_=[len(enc(r['docs'])) for r in inputs];nc=[len(r['docs']) for r in inputs]
    count_pr=Counter('unavailable' if g['status']!='ok' else 'direct' if g['strict'] else 'not_direct' for g in pr.values())
    res={'source_histories':len(get('roster.json')),'anchors':len(inputs),'anchor_tasks':len(pr),'censored_next':sum(not y['target'] for y in nl.values()),'pr_tasks':dict(count_pr),'pr_anchor_status':statuses,'endpoints':summaries,'joint_endpoints':overlap,
    'retention':{'candidates_median':statistics.median(nc),'candidates_p90':quantile(nc,.9),'candidates_max':max(nc),'empty':sum(not n for n in nc),'document_bytes_median':statistics.median(bytes_),'document_bytes_p90':quantile(bytes_,.9),'document_bytes_max':max(bytes_)}}
    save('results.json',res);save('paired_effects.json',pairs)
    for end,sv in summaries.items():print(end,sv['all'],flush=True)
    print('joint',overlap,'resource',res['retention'])
if __name__=='__main__':main()
