from collections import Counter, defaultdict
from pathlib import Path
from datetime import datetime,timezone
import json,random,math
from run import P,readgz,load

def boot(items):
    groups=list(items.values())
    if not groups:return None
    rng=random.Random(17112026);v=[]
    for _ in range(2000):
        draw=rng.choices(groups,k=len(groups))
        a=sum(x[0] for x in draw);n=sum(x[1] for x in draw);v.append(a/n)
    v.sort()
    return {'difference':sum(x[0] for x in groups)/sum(x[1] for x in groups),
            'project_boot95':[v[49],v[1949]],'macro_project_difference':sum(x[0]/x[1] for x in groups)/len(groups),
            'projects':len(groups)}

def stamp(ms):return datetime.fromtimestamp(ms/1000,timezone.utc).isoformat()
def evaluate(kind):
    all_inputs,ys=load(kind);inputs={r['id']:r for r in all_inputs}
    preds={r['id']:r for r in readgz(P/(kind+'_predictions.jsonl.gz'))}
    choices={r['id']:r['accepted'] for r in readgz(P/(kind+'_allocation.jsonl.gz'))}
    assert set(preds)==set(choices)
    ids=list(preds)
    target='typed' if kind=='jobs' else 'recent8'
    methods=[s for s in preds[ids[0]]['p'] if s not in ('matching','typed_matching','sparse','uncertain')]
    allocs=sorted(set(a for picks in choices.values() for a in picks))
    read_count={};read_bytes={}
    for method,mask in [('always','all'),('uncertain','uncertain'),('sparse','sparse')]:
        chosen=[i for i in ids if kind=='jobs' and (mask=='all' or preds[i]['p'][mask])]
        read_count[method]=len(chosen);read_bytes[method]=sum(len(json.dumps(inputs[i]['reasons'],separators=(',',':')).encode()) for i in chosen)
    stats={}
    all_pass=sum(ys[i]['passed'] for i in ids)
    for arm in sorted(set(methods+allocs)):
        row={}
        if arm in methods:
            pro={i:preds[i]['p'][arm] for i in ids}
            high=[i for i in ids if pro[i]>=.5]
            row.update(brier=sum((pro[i]-ys[i]['passed'])**2 for i in ids)/len(ids),
                       threshold_retries=len(high),threshold_recoveries=sum(ys[i]['passed'] for i in high))
        if arm in allocs:
            selected=[i for i in ids if arm in choices[i]]
            hit=sum(ys[i]['passed'] for i in selected);sec=sum(ys[i]['duration_s'] for i in selected)
            row.update(selected=len(selected),recovered=hit,recall=hit/all_pass,ppv=hit/len(selected),
                       actual_retry_runtime_hours=sec/3600)
        stats[arm]=row
    contrasts={}
    test_pairs=[(target,'global_context'),(target,'repo_status'),('repo_status','status'),('repo','global'),('recent8','last_repo'),('context_all','repo_status'),('teacher_'+target,target),('explore_'+target,target)]
    if kind=='jobs':test_pairs += [('typed','global_type'),('typed_if_uncertain','typed'),('typed_if_uncertain','repo_status'),('typed_if_sparse','typed')]
    for a,b in test_pairs:
        if a==b:continue
        affected={};bc=defaultdict(lambda:[0,0]);ac=defaultdict(lambda:[0,0]);wins=losses=0
        for i in ids:
            repo=inputs[i]['repo'];y=ys[i]['passed']
            if a in methods and b in methods:
                delta=(preds[i]['p'][a]-y)**2-(preds[i]['p'][b]-y)**2
                bc[repo][0]+=delta;bc[repo][1]+=1
            if a in allocs and b in allocs:
                d=(int(a in choices[i])-int(b in choices[i]))*y;ac[repo][0]+=d;ac[repo][1]+=1
                wins+=d>0;losses+=d<0
        if bc:affected['delta_brier']=boot(bc)
        if ac:affected.update(delta_rescues_per_opportunity=boot(ac),additional_recoveries=wins,lost_recoveries=losses)
        contrasts[a+' vs '+b]=affected
    projects={inputs[i]['repo'] for i in ids};prior_projects={r['repo'] for r in all_inputs if r['id'] not in preds}
    matchfield='typed_matching' if kind=='jobs' else 'matching'
    strata={}
    for label,which in [('no_matching_receipt',lambda i:preds[i]['p'][matchfield]==0),('one_or_more',lambda i:preds[i]['p'][matchfield]>0),
                        ('project_in_warmup',lambda i:inputs[i]['repo'] in prior_projects),('new_project',lambda i:inputs[i]['repo'] not in prior_projects)]:
        group=[i for i in ids if which(i)]
        if group:strata[label]={'n':len(group),'recovered':sum(ys[i]['passed'] for i in group),
             'target_brier':sum((preds[i]['p'][target]-ys[i]['passed'])**2 for i in group)/len(group),
             'repo_status_brier':sum((preds[i]['p']['repo_status']-ys[i]['passed'])**2 for i in group)/len(group)}
    categories=Counter('/'.join(inputs[i].get('reasons',[])) or 'none' for i in ids) if kind=='jobs' else None
    return {'heldout':len(ids),'recovered':all_pass,'n_projects':len(projects),'prior_seen_projects':len(projects&prior_projects),
            'total':len(inputs),'train':len(inputs)-len(ids),'time_from':stamp(all_inputs[0]['decision_at']),'time_to':stamp(all_inputs[-1]['decision_at']),
            'test_start':stamp(min(inputs[i]['decision_at'] for i in ids)),'all_retry_runtime_hours':sum(ys[i]['duration_s'] for i in ids)/3600,
            'rates':stats,'paired':contrasts,'strata':strata,'diagnosis_reads':read_count if categories else None,'diagnosis_bytes':read_bytes if categories else None,
            'reason_support':categories if categories else None}

if __name__=='__main__':
    out={k:evaluate(k) for k in ('builds','jobs')}
    import sys
    if '--check' in sys.argv:assert out==json.loads((P/'results.json').read_bytes())
    else:(P/'results.json').write_text(json.dumps(out,indent=2,sort_keys=True))
    print('Verified' if '--check' in sys.argv else 'Scored',[(k,z['heldout']) for k,z in out.items()])
