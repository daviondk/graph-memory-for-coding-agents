"""Select exactly one archived response per ordinal; unblind only after allocation is locked."""
import argparse
from collections import Counter, defaultdict
import csv
import json
from math import comb
from pathlib import Path
import random
import time
from policy import ARCHIVE, HERE, load, save, sha, stamp

NAMES=('never','always','gate','random')
LABELS=('any','first','last')
SEED=20261116


def read_csv(path):
    with path.open(encoding='utf8',newline='') as f:
        return list(csv.DictReader(f))


def read_lines(path):
    return [json.loads(l) for l in path.read_text(encoding='utf8').splitlines() if l]


def write_csv(path, rows):
    with path.open('w',encoding='utf8',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)


def percentile(values, probability):
    return sorted(values)[round((len(values)-1)*probability)]


def summary(rows,name):
    result={'n':len(rows),'full':sum(r[name+'_full'] for r in rows),
            'prompt':sum(r[name+'_input'] for r in rows),'output':sum(r[name+'_output'] for r in rows)}
    result.update({label:sum(r[name+'_'+label] for r in rows) for label in LABELS})
    return result


def contrast(rows, treatment, control):
    clusters=defaultdict(list)
    wins=losses=ties_changed=0
    for row in rows:
        hit=row[treatment+'_any']-row[control+'_any']
        cost=row[treatment+'_input']-row[control+'_input']
        clusters[row['repo']].append((hit,cost))
        wins+=hit==1
        losses+=hit==-1
        ties_changed+=(not hit and row[treatment+'_key']!=row[control+'_key'])
    N=len(rows)
    counts=[(len(v),sum(s for s,_ in v),sum(t for _,t in v)) for v in clusters.values()]
    rng=random.Random(SEED)
    res=[]
    for _ in range(10000):
        subset=rng.choices(counts,k=len(counts))
        n=sum(x[0] for x in subset)
        res.append((sum(x[1] for x in subset)/n,sum(x[2] for x in subset)/n))
    ndisc=wins+losses
    p=min(1,2*sum(comb(ndisc,i) for i in range(min(wins,losses)+1))/2**ndisc)
    return {'wins':wins,'losses':losses,'changed_choice_same_grade':ties_changed,
            'delta_accuracy':(wins-losses)/N,'nrepo':len(counts),'p_exact_paired_descriptive':p,
            'delta_accuracy_cluster_ci95':[percentile([x[0] for x in res],q) for q in (.025,.975)],
            'delta_prompt_per_query':sum(x[2] for x in counts)/N,
            'delta_prompt_per_query_cluster_ci95':[percentile([x[1] for x in res],q) for q in (.025,.975)]}


def uniform_null(rows):
    n=len(rows)
    k=sum(r['gate_full'] for r in rows)
    outcomes=Counter(r['always_any']-r['never_any'] for r in rows)
    base=sum(r['never_any'] for r in rows)
    denom=comb(n,k)
    ways=Counter()
    for g in range(outcomes[1]+1):
        for h in range(outcomes[-1]+1):
            z=k-g-h
            if 0<=z<=outcomes[0]:
                ways[base+g-h]+=comb(outcomes[1],g)*comb(outcomes[-1],h)*comb(outcomes[0],z)
    assert sum(ways.values())==denom
    observed=sum(r['gate_any'] for r in rows)
    deltas=[r['always_input']-r['never_input'] for r in rows]
    short_cost=sum(r['never_input'] for r in rows)
    rng=random.Random(SEED)
    costs=[short_cost+sum(rng.sample(deltas,k)) for _ in range(20000)]
    dist={score:cnt/denom for score,cnt in sorted(ways.items())}
    # Exact central confidence envelope for the random assignment score.
    cdf=0
    lo=hi=None
    for score,prob in dist.items():
        cdf+=prob
        if cdf>=.025 and lo is None:lo=score
        if cdf>=.975 and hi is None:hi=score
    return {'random_size':k,'probabilities':dist,'expected_hits':sum(s*p for s,p in dist.items()),
            'central95_hits':[lo,hi],'probability_random_ge_gate':sum(cnt for s,cnt in ways.items() if s>=observed)/denom,
            'expected_prompt_tokens':short_cost+k*sum(deltas)/n,'central95_prompt_tokens_mc':[percentile(costs,.025),percentile(costs,.975)],
            'token_draws':len(costs),'comparison':'Random equal-k assignment on these 99 potential response pairs'}


def evaluate(parent):
    begin=time.perf_counter()
    lock=load(HERE/'decision_lock.json');registration=load(HERE/'registration.json')
    assert sha(HERE/'registration.json')==lock['source_registration'] and sha(HERE/'assignments.json')==lock['assignments']
    assert sha(HERE/'postings.json')==lock['index'] and sha(HERE/'policy.py')==registration['policy']
    assert sha(HERE/'PROTOCOL.md')==registration['protocol']
    for n,h in registration['inputs'].items():assert sha(parent/n)==h
    arm_dir=parent/'matched_reader'
    main=load(parent/'blind_commit.json')
    matched=load(arm_dir/'blind_commit.json')
    assert sha(parent/'qwen_calls.jsonl')==main['qwen_calls.jsonl']
    assert sha(arm_dir/'calls.jsonl')==matched['predictions'] and sha(arm_dir/'freeze.json')==matched['freeze']
    full={v['ordinal']:v for v in read_lines(parent/'qwen_calls.jsonl')}
    short={v['ordinal']:v for v in read_lines(arm_dir/'calls.jsonl') if v['arm']=='no_edits'}
    qrows={int(v['ordinal']):v for v in read_csv(parent/'per_query.csv') if v['group']=='lite'}
    library={v['trace_key']:v['instance_id'] for v in read_csv(parent/'evaluation_library.csv')}
    gold=defaultdict(list)
    for v in read_csv(parent/'evaluation_relations.csv'):
        ids=gold[v['related_instance_id']]
        eid=v['experience_instance_id']
        if eid not in ids:ids.append(eid)
    assigned=load(HERE/'assignments.json')
    assert len(assigned)==len(full)==len(short)==len(qrows)==99 and len(library)==300
    rows=[]
    for row in assigned:
        i=row['ordinal']
        a,b=full[i],short[i]
        assert a['order']==b['order'] and set(row['slate'])==set(a['order']) and row['slate']==b['base_slate']
        q=qrows[i]
        labels=gold[q['instance_id']]
        assert set(labels)==set(q['gold_ids'].split('|')) and labels
        found={'ordinal':i,'issue_id':q['instance_id'],'repo':q['repo'],'n_signals':len(row['distinctive_signals']),
               'gold_any':'|'.join(labels),'gold_first':labels[0],'gold_last':labels[-1]}
        for name,expose in [('always',True),('never',False),('gate',row['full']),('random',row['random_full'])]:
            x=a if expose else b
            choice=library[x['choice']]
            found.update({name+'_full':int(expose),name+'_key':x['choice'],name+'_instance_id':choice,
                          name+'_any':int(choice in labels),name+'_first':int(choice==labels[0]),name+'_last':int(choice==labels[-1]),
                          name+'_input':x['usage']['prompt_tokens'],name+'_output':x['usage']['completion_tokens']})
        assert found['always_any']==int(q['qwen_1'])
        rows.append(found)
    assert len({r['ordinal'] for r in rows})==99
    stats={n:summary(rows,n) for n in NAMES}
    assert stats['random']['full']==stats['gate']['full']==lock['n_full']
    by_repo=[]
    influence=[]
    for repo in sorted({r['repo'] for r in rows}):
        group=[r for r in rows if r['repo']==repo]
        keep=[r for r in rows if r['repo']!=repo]
        by_repo.append({'repo':repo,'n':len(group),'gate_full':sum(r['gate_full'] for r in group),
                        **{f'{p}_{k}':summary(group,p)[k] for p in NAMES for k in ['any','prompt']}})
        influence.append({'excluded_repo':repo,'retained':len(keep),'gate_vs_never_hit_delta':sum(r['gate_any']-r['never_any'] for r in keep),
                          'gate_vs_always_hit_delta':sum(r['gate_any']-r['always_any'] for r in keep)})
    result={'n':len(rows),'repo_count':len(by_repo),'outcomes':stats,'full_vs_short':contrast(rows,'always','never'),
            'gate_vs':{m:contrast(rows,'gate',m) for m in ('never','always','random')},
            'uniform':uniform_null(rows),'oracle_between_two_outputs':sum(max(r['always_any'],r['never_any']) for r in rows),
            'cohorts':{str(i):{m:summary([r for r in rows if r['gate_full']==i],m) for m in NAMES} for i in (0,1) if any(r['gate_full']==i for r in rows)},
            'empirically_nondominated':[m for m in NAMES if not any(stats[j]['any']>=stats[m]['any'] and stats[j]['prompt']<=stats[m]['prompt'] and (stats[j]['any']>stats[m]['any'] or stats[j]['prompt']<stats[m]['prompt']) for j in NAMES)],
            'outcomes_sha':{str(f.relative_to(parent)):sha(f) for f in [parent/'qwen_calls.jsonl',arm_dir/'calls.jsonl',parent/'per_query.csv',parent/'evaluation_library.csv',parent/'evaluation_relations.csv']}}
    write_csv(HERE/'per_query.csv',rows);write_csv(HERE/'per_repo.csv',by_repo);write_csv(HERE/'leave_one_repo.csv',influence)
    save(HERE/'results.json',result)
    artifacts=['registration.json','decision_lock.json','postings.json','assignments.json','PROTOCOL.md','policy.py','evaluate.py','results.json','per_query.csv','per_repo.csv','leave_one_repo.csv']
    save(HERE/'result_receipt.json',{'utc':stamp(),'seconds':time.perf_counter()-begin,'replayed_model_calls':99,'new_model_calls':0,
         'files':{n:sha(HERE/n) for n in artifacts}})
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--parent',type=Path,default=ARCHIVE)
    result=evaluate(parser.parse_args().parent)
    print(json.dumps({k:result[k] for k in ['outcomes','gate_vs','uniform','empirically_nondominated','oracle_between_two_outputs']},indent=1))

