"""Evaluate native line locations and enumerate the exact random fixed-quota allocation distribution."""
import collections
import itertools
import json
import math
from statistics import mean
import sys

from pyarrow import parquet
from gate import ROOT, WORK, SELECTION, INPUT, read,put,sha
sys.path.insert(0,str(SELECTION))
from patch_diagnostic import original_lines,unidiff_old,intervals
def movement_distribution(diffs,quota):
    states=collections.Counter({(0,0):1})
    for d in diffs:
        nxt=states.copy()
        for (selected,delta),count in states.items():
            if selected<quota:nxt[selected+1,delta+d]+=count
        states=nxt
    counts={v:n for (k,v),n in states.items() if k==quota}
    assert sum(counts.values())==math.comb(len(diffs),quota)
    return counts
def quantile(hist,p):
    total=sum(hist.values());running=0
    for k,v in sorted(hist.items()):
        running+=v
        if running>=p*total:return k
def main():
    for n,h in read(ROOT/'read.lock.json').items():assert sha((ROOT/n).read_bytes())==h
    sources=read(ROOT/'roster.json');route={r['id']:r for r in read(ROOT/'route.json')};menus={r['id']:r for r in read(ROOT/'menus.json.gz')}
    labels={}
    vf=WORK/'graph_memory_round3/real_swe/official_verified.parquet'
    for row in parquet.read_table(vf,columns=['instance_id','patch']).to_pylist():
        k=row['instance_id']
        if k in route:
            v=original_lines(row['patch'])
            assert v==unidiff_old(row['patch'])
            labels[k]=v
    raw=read(ROOT/'actions.json.gz');annotated=[]
    for r in raw:
        i=r['id'];assignment=route[i];truth=labels[i]
        menu=menus[i]['menu']
        paths={(v['p'],n) for v in menu.values() for n in range(v['s'],v['e']+1)}
        r['patch_exists']=bool(truth);r['possible_in_menu']=bool(paths&truth)
        for a in ('qwen','static'):
            r[a]['hits']=len(intervals(r[a]['region'])&truth)
        r['methods']={'all_qwen':'qwen','static':'static','gap':'qwen' if assignment['route_gap'] else 'static','hash':'qwen' if assignment['route_hash'] else 'static'}
        annotated.append(r)
    put('annotated.json.gz',annotated)
    n=sources['eligible'];quota=sources['quota']
    totals={}
    for m in ('all_qwen','static','gap','hash'):
        chosen=[(r,r['methods'][m]) for r in annotated]
        used=[r for r,k in chosen if k=='qwen' and r['available']]
        totals[m]={'calls':len(used),'prompt_tokens':sum(r['cost']['prompt_tokens'] for r in used),
            'completion_tokens':sum(r['cost']['completion_tokens'] for r in used),'hits':sum(r[k]['hits']>0 for r,k in chosen),
            'valid_reads':sum(bool(r[k]['region']) for r,k in chosen),'available_tasks':n,
            'hits_ids':[r['id'] for r,k in chosen if r[k]['hits']>0]}
    diffs=[int(r['qwen']['hits']>0)-int(r['static']['hits']>0) for r in annotated if r['available']]
    counts=movement_distribution(diffs,quota);k=totals['static']['hits'];hist={k+d:count for d,count in counts.items()};nalloc=sum(hist.values())
    expectation=sum(v*p for v,p in hist.items())/nalloc
    assert abs(expectation - (k+(quota/n)*sum(diffs)))<1e-12
    sample_hit=totals['gap']['hits']
    totals['expected_uniform']={'expected_hits':expectation,'central_95':[quantile(hist,.025),quantile(hist,.975)],
        'n_allocations':nalloc,'histogram':hist,'p_uniform_ge_gap':sum(p for hit,p in hist.items() if hit>=sample_hit)/nalloc,
        'expected_prompt_tokens':totals['all_qwen']['prompt_tokens']*quota/n,
        'expected_completion_tokens':totals['all_qwen']['completion_tokens']*quota/n}
    calls=[json.loads(l) for l in (ROOT/'calls.jsonl').read_bytes().splitlines()]
    groups={name:[int(r['qwen']['hits']>0)-int(r['static']['hits']>0) for r in annotated if r['available'] and route[r['id']]['route_gap']==condition]
            for name,condition in [('routed',True),('unrouted',False)]}
    for m in ('gap','hash'):
        assert totals[m]['calls']==quota
    summary={'policies':totals,'eligible':n,'quota':quota,'total':len(annotated),'with_old':sum(r['patch_exists'] for r in annotated),'menu_ceiling':sum(r['possible_in_menu'] for r in annotated),
        'attainable_fixed_quota_oracle':max(hist),'gains_losses_ties':{k:dict(collections.Counter(v)) for k,v in groups.items()},
        'native_calls':len(calls),'model_seconds':sum(r['elapsed'] for r in calls),'invalid_calls':sum(not r['valid'] for r in calls),
        'pooled_physical_reads':sum(bool(r[m]['region']) for r in annotated for m in ('qwen','static'))}
    put('results.json',summary)
    print('n, available, menu upper, quota oracle',len(annotated),n,summary['menu_ceiling'],max(hist))
    print({m:(v.get('hits',v.get('expected_hits')),v.get('calls'),v.get('prompt_tokens'),v.get('completion_tokens')) for m,v in totals.items()})
    print(totals['expected_uniform'],groups,flush=True)
if __name__=='__main__':main()
