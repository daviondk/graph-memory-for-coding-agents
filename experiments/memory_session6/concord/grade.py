"""Recover published and local ConcordBench outcomes and costs from original per-case archives."""
from collections import Counter, defaultdict
from functools import lru_cache
from pathlib import Path
import argparse
import gzip
import hashlib
import json
import math
import re
import string

import numpy as np

ROOT = Path(__file__).resolve().parent
BENCH = ROOT / "upstream/bench"
UPSTREAM = "4116936349995f0f30597931c0dbbebcbf7e58ac"
ARMS = ("baseline", "window", "raw")
PAIR = (("window","baseline"),("window","raw"),("baseline","raw"))
SEED = 20261118


def digest(b):
    return hashlib.sha256(b).hexdigest()


def compact(o):
    return json.dumps(o, ensure_ascii=False, sort_keys=True, separators=(",",":")).encode()


def read(p):
    buf=p.read_bytes()
    return json.loads(gzip.decompress(buf) if p.suffix==".gz" else buf)


def write_checked(p, payload):
    buf = compact(payload)
    if p.suffix==".gz":buf=gzip.compress(buf,mtime=0)
    if p.exists():
        assert read(p)==payload, f"replay mismatch {p}"
    else:
        p.write_bytes(buf)


def normalize(s):
    # Upstream qa_agent.eval_pioneer.normalize_answer (US ASCII punctuation).
    s="".join(c for c in s.lower() if c not in string.punctuation)
    return " ".join(re.sub(r"\b(a|an|the)\b"," ",s).split())


def score(answer, gold):
    a,b=normalize(answer or ""),normalize(gold)
    aa,bb=a.split(),b.split()
    match=sum((Counter(aa)&Counter(bb)).values())
    return int(a==b),2*match/(len(aa)+len(bb)) if aa or bb else 1.


def source_roster():
    return {r["id"]:r["answer"] for r in read(BENCH/"pioneer_augmented.json")["hotpotqa"]}


def published_projection():
    roster=source_roster();rows=[];hashes={}
    for jpath in sorted((BENCH/"runs").glob("*_eval_traced_judged.json")):
        rawpath=jpath.with_name(jpath.name.replace("_judged",""))
        for p in [rawpath,jpath]:hashes[p.name]=digest(p.read_bytes())
        judged,raw=read(jpath),read(rawpath)
        jid={r["id"]:r for r in judged["tasks"]}
        assert len(raw["tasks"])==len(jid)==40 and set(jid)==set(roster)
        arm=jpath.name.split("hotpot40_",1)[1].split("_eval_")[0]
        for orig in raw["tasks"]:
            sid=orig["id"];j=jid[sid]
            assert orig["gold_answer"]==j["gold_answer"]==roster[sid]
            assert orig["final_answer"]==j["final_answer"]
            em,f1=score(orig["final_answer"],roster[sid])
            assert em==int(orig["exact_match"])==int(j["exact_match"])
            assert abs(f1-orig["token_f1"])<1e-12 and abs(f1-j["token_f1"])<1e-12
            rows.append(dict(id=sid,actor=raw["model"],arm=arm,gold=roster[sid],answer=orig["final_answer"],
                  em=em,f1=f1,judge=judged["judge_model"],judge_correct=int(j["llm_judge_correct"]),
                  events=orig["event_count"],prompt=orig["prompt_tokens"],completion=orig["completion_tokens"]))
    assert len(rows)==600
    write_checked(ROOT/"published_projection.json.gz",rows)
    write_checked(ROOT/"published_sources.json",{"commit":UPSTREAM,"trace_and_judge_sha256":hashes,
                    "eval_pioneer_sha256":digest((BENCH/"qa_agent/eval_pioneer.py").read_bytes()),
                    "pioneer_sha256":digest((BENCH/"pioneer_augmented.json").read_bytes())})
    return rows


def paired(av,bv,draws):
    a,b=np.asarray(av,float),np.asarray(bv,float)
    good=np.isfinite(a)&np.isfinite(b)
    d=a-b
    if not np.any(good):return {"paired_n":0}
    valid_draw=good[draws]
    sizes=valid_draw.sum(1)
    safe=sizes>0
    boot=np.where(valid_draw,d[draws],0).sum(1)[safe]/sizes[safe]
    win,loss=int((d>1e-12).sum()),int((d< -1e-12).sum())
    n=win+loss
    p=min(1., 2*sum(math.comb(n,k) for k in range(min(win,loss)+1))/2**n) if n else 1.
    return dict(paired_n=int(sum(good)),delta=float(d[good].mean()), ci=np.quantile(boot,[.025,.975]).tolist(),
                wins=win,losses=loss,ties=int(sum(good))-n,exact_sign_p=p)


def public_summary(rows):
    data=defaultdict(dict)
    for r in rows:
        em,f1=score(r["answer"],r["gold"])
        assert em==r["em"] and abs(f1-r["f1"])<1e-12
        data[(r['actor'],r['arm'])][r['id']]=r
    report={}
    for (actor,arm),sidrows in data.items():
        records=list(sidrows.values()); total=lambda k:sum(r[k] for r in records)
        report.setdefault(actor,{'arms':{},'paired':{}})['arms'][arm]=dict(n=len(records),em=total('em'),f1=total('f1')/len(records),
               published_judge_correct=total('judge_correct'),judge=list(sorted({r['judge'] for r in records})),
               events=total('events'),prompt=total('prompt'),completion=total('completion'))
    draws=np.random.default_rng(SEED).integers(0,40,(10000,40))
    for actor in report:
        for arm in ['naive','alert','diff','oracle']:
            a,b=data[actor,'block_context'],data[actor,arm];ids=sorted(a);assert set(ids)==set(b)
            report[actor]['paired']['block_context_minus_'+arm]={k:paired([a[i][k] for i in ids],[b[i][k] for i in ids],draws) for k in ['em','f1','judge_correct']}
    return report


@lru_cache(None)
def load_call(key):
    p=ROOT/'calls'/(key+'.json.gz')
    if not p.exists():return None
    data=read(p)
    assert digest(compact(data['request']))==key
    resp=data['response'];u=resp.get('usage')
    timing=resp.get("timings",{})
    marker='\nCurrent source window '
    passages=[m.get('content','') for m in data['request']['messages'] if m.get('role')=='tool' and isinstance(m.get('content'),str) and marker in m['content']]
    return {'code':data['code'],'window_presentations':sum(s.count(marker) for s in passages),
            'window_request':int(bool(passages)), 'prompt':u.get('prompt_tokens') if u else None,
            'completion':u.get('completion_tokens') if u else None,
            'cached_prompt':(u.get('prompt_tokens_details') or {}).get('cached_tokens',0) if u else None,
            'model_ms':timing.get('prompt_ms',0)+timing.get('predicted_ms',0) if timing else None}


def local_projection():
    lock=read(ROOT/'decision_lock.json'); ids=sorted(source_roster())
    expected={f'{sid}_{arm}.json.gz' for sid in ids for arm in ARMS}
    assert len(ids)==40 and set(lock)==expected
    rows=[];call_index={};roster=source_roster()
    for filename in sorted(lock):
        p=ROOT/'trials'/filename;assert digest(p.read_bytes())==lock[filename]
        t=read(p);sid,arm=t['id'],t['arm'];assert filename==f'{sid}_{arm}.json.gz'
        em,f1=score(t['answer'],roster[sid])
        tool_names=Counter(c['tool'] for event in t['trace'] for c in event)
        if t['actions'] is not None:assert t['actions']==sum(tool_names.values())
        assert len(t['fresh_windows'])==t['proactive_reads'] and sum(x['bytes'] for x in t['fresh_windows'])==t['read_bytes']
        if arm!='window':assert t['proactive_reads']==0
        for key in t['requests']:call_index[key]=load_call(key)
        observed=[call_index[key] for key in t['requests'] if call_index[key] is not None]
        sums={k:sum(c[k] for c in observed if c[k] is not None) for k in ['prompt','completion','cached_prompt','model_ms','window_presentations','window_request']}
        partial=sum(c['prompt'] is None or c['completion'] is None for c in observed)+len(t['requests'])-len(observed)
        rows.append(dict(id=sid,arm=arm,gold=roster[sid],answer=t['answer'] or '',em=em,f1=f1,
            stop=t['stop'],actions=t['actions'],events=t['events'],race_events=t['race_events'],
            submitted_answer=(bool(tool_names['answer']) if t['events'] is not None else None),
            tools=dict(tool_names) if t['events'] is not None else None, extra_reads=t['proactive_reads'],extra_bytes=t['read_bytes'],
            requests=t['requests'],request_count=len(t['requests']),missing_receipt=len(t['requests'])-len(observed),
            missing_usage=partial,request_errors=dict(Counter(str(c['code']) for c in observed if c['code']!=200)),
            **sums))
    failures={}
    for path in sorted((ROOT/'failures').glob('*.json.gz')):
        f=read(path);failures[path.name]=f.get('status')
    # Full inventory also lists locally cached calls outside final scored trajectories (e.g. infrastructure probes).
    unused={p.name.split('.')[0] for p in (ROOT/'calls').glob('*.json.gz')}-set(call_index)
    other_calls={k:load_call(k) for k in sorted(unused)}
    write_checked(ROOT/'local_projection.json.gz',rows)
    write_checked(ROOT/'call_projection.json.gz',{'used':call_index,'unreferenced':other_calls,'transport_receipts':failures,
            'decision_lock_sha256':digest((ROOT/'decision_lock.json').read_bytes())})
    return rows


def local_summary(rows,index):
    by=defaultdict(dict)
    for r in rows:
        em,f1=score(r['answer'],r['gold']);assert r['em']==em and abs(f1-r['f1'])<1e-12
        by[r['arm']][r['id']]=r
    ids=sorted(by['baseline'])
    assert len(ids)==40 and all(sorted(v)==ids for v in by.values()) and set(by)==set(ARMS)
    draws=np.random.default_rng(SEED).integers(0,40,(10000,40))
    result={'arms':{},'pairs':{},'cache':{}}
    for arm in ARMS:
        z=list(by[arm].values())
        def total(k):
            return sum(r[k] for r in z if r[k] is not None)
        allkeys=[k for r in z for k in r['requests']]
        result['arms'][arm]=dict(n=len(z),em=total('em'),f1=total('f1')/len(z),stop=dict(Counter(r['stop'] for r in z)),
            submitted_answer=total('submitted_answer'),missing_submissions=sum(r['submitted_answer'] is None for r in z),
            actions_observed=total('actions'),events_observed=total('events'),missing_actions=sum(r['actions'] is None for r in z),
            race_events_observed=total('race_events'),cases_with_race=sum((r['race_events'] or 0)>0 for r in z),
            tool_counts=dict(sum((Counter(r['tools'] or {}) for r in z),Counter())),
            model_requests_with_window=total('window_request'), rendered_window_appearances=total('window_presentations'),
            extra_reads=total('extra_reads'),extra_bytes=total('extra_bytes'),cases_refreshed=sum(r['extra_reads']>0 for r in z),
            missing_receipts=total('missing_receipt'),missing_usage=total('missing_usage'),requests=len(allkeys),unique_requests=len(set(allkeys)),
            prompt_observed=total('prompt'),completion_observed=total('completion'),
            cached_prompt_observed=total('cached_prompt'),model_seconds_observed=total('model_ms')/1000)
    for a,b in PAIR:
        ds={}
        for k in ['em','f1','submitted_answer','events','actions','race_events','request_count','prompt','completion','extra_reads','extra_bytes']:
            def val(r):
                if k in ('prompt','completion') and r['missing_usage']:return np.nan
                return r[k] if r[k] is not None else np.nan
            ds[k]=paired([val(by[a][s]) for s in ids],[val(by[b][s]) for s in ids],draws)
        identical=[s for s in ids if by[a][s]['requests']==by[b][s]['requests']]
        assert all(by[a][s]['answer']==by[b][s]['answer'] for s in identical)
        ds['same_request_sequence_cases']=len(identical);ds['different_request_sequence_cases']=len(ids)-len(identical)
        ds['identical_ids']=identical
        common_prefixes=[]
        for sid in ids:
            aa,bb=by[a][sid]['requests'],by[b][sid]['requests']
            common=next((i for i,(left,right) in enumerate(zip(aa,bb)) if left!=right), min(len(aa),len(bb)))
            common_prefixes.append(common)
        ds['same_initial_request_count']=sum(common_prefixes)
        changed=[sid for sid in ids if sid not in identical]
        ds['conditional_different_inputs']={'n':len(changed),'em_wins':sum(by[a][i]['em']>by[b][i]['em'] for i in changed),
            'em_losses':sum(by[a][i]['em']<by[b][i]['em'] for i in changed)}
        ds['cases_different_answer']=sum(by[a][s]['answer']!=by[b][s]['answer'] for s in ids)
        result['pairs'][a+'_minus_'+b]=ds
    used=index['used'];present=[v for v in used.values() if v is not None]
    logical=sum(r['request_count'] for r in rows)
    distinct_within=sum(len(set(r['requests'])) for r in rows)
    distinct_case=sum(len(set(k for arm in ARMS for k in by[arm][s]['requests'])) for s in ids)
    result['cache']=dict(logical_attempts=logical,unique_request_keys=len(used),receipts_present=len(present),
        physical_successful_receipts=sum(v['code']==200 for v in present),request_keys_missing=len(used)-len(present),
        repeated_in_same_trajectory=logical-distinct_within,repeated_across_arms_within_case=distinct_within-distinct_case,
        repeated_across_cases=distinct_case-len(used),unique_prompt_observed=sum(v['prompt'] or 0 for v in present),
        unique_completion_observed=sum(v['completion'] or 0 for v in present),unique_model_seconds_observed=sum(v['model_ms'] or 0 for v in present)/1000,
        unreferenced_cached_keys=len(index['unreferenced']),transport_failures=len(index['transport_receipts']))
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--public-only',action='store_true')
    parser.add_argument('--offline',action='store_true')
    args=parser.parse_args()
    pub=read(ROOT/'published_projection.json.gz') if args.offline else published_projection()
    published=public_summary(pub);write_checked(ROOT/'published_results.json',published)
    if args.public_only:
        for actor,run in published.items():print(actor,[(a,v['em'],round(v['f1'],3),v['published_judge_correct']) for a,v in run['arms'].items()])
    else:
        rows=read(ROOT/'local_projection.json.gz') if args.offline else local_projection()
        local=local_summary(rows,read(ROOT/'call_projection.json.gz'))
        write_checked(ROOT/'local_results.json',local)
        print('PASS 600 published and 120 paired local case policies',[(k,v['em'],round(v['f1'],4)) for k,v in local['arms'].items()])
