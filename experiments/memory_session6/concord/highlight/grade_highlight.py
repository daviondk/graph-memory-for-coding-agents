"""Verify locked decisions, compare prompts with/without cue, score all paired tasks."""
import gzip
import json
import sys
from collections import Counter
from pathlib import Path
import numpy as np

HERE=Path(__file__).resolve().parent
BASE=HERE.parent
sys.path.insert(0,str(BASE))
from grade import compact,digest,paired,read,score,write_checked
from cue import WORDS
ARMS=('baseline','correction','control')
CONTRASTS=(('correction','control'),('correction','baseline'),('control','baseline'))
PREFIX='Current source detail ('


def get_call(k):
    p=BASE/'calls'/(k+'.json.gz')
    old=p.exists()
    if not old:
        p=HERE/'calls'/(k+'.json.gz')
    assert p.exists(),p
    r=read(p)
    req=r['request'];assert digest(compact(req))==k
    response=r['response']
    u=response.get('usage',{})
    choices=response.get('choices',[])
    tool_calls=(choices[0].get('message',{}).get('tool_calls') or []) if choices else []
    action=[]
    for c in tool_calls:
        fun=c['function'];args=fun['arguments']
        try:args=json.loads(args)
        except (ValueError,TypeError):pass
        action.append([fun['name'],args])
    return req,dict(status=r['code'],tool_names=[x[0] for x in action],action_signature=digest(compact(action)),prompt=u.get('prompt_tokens'),completion=u.get('completion_tokens'),
                    cached_prompt=u.get('prompt_tokens_details',{}).get('cached_tokens',0),original_receipt=old)


def from_traces():
    design=read(HERE/'design_lock.json')
    assert all(digest((HERE/f).read_bytes())==h for f,h in design['sha256'].items())
    lock=read(HERE/'decision_lock.json'); roster=set(design['roster'])
    assert len(roster)==40 and set(lock)=={f'{s}_{a}.json.gz' for s in roster for a in ARMS if a!='baseline'}
    main_lock=read(BASE/'decision_lock.json')
    assert digest((BASE/'decision_lock.json').read_bytes())==design['baseline_lock_sha256']
    gold={r['id']:r['gold'] for r in read(BASE/'local_projection.json.gz') if r['arm']=='baseline'}
    index={};rows=[];answers=[]
    for sid in sorted(roster):
        for arm in ARMS:
            old=arm=='baseline'; root=BASE if old else HERE
            fn=f'{sid}_{arm}.json.gz'
            p=root/'trials'/fn
            assert digest(p.read_bytes())==(main_lock if old else lock)[fn]
            t=read(p);assert t['id']==sid and t['arm']==arm
            cues=[] if old else t['opportunities'][design['chosen']]
            cues_by_step={e['request']:e for e in cues}
            assert len(cues_by_step)==len(cues)
            issued=[]; first_cue_prompt=None; first_unmarked_request=None
            for step,k in enumerate(t['requests'],1):
                req,rec=get_call(k)
                index[k]=rec
                msgs=req['messages']
                assert all(PREFIX not in (m.get('content') or '') for m in msgs[:-1])
                last=msgs[-1].get('content') or ''
                if step in cues_by_step:
                    e=cues_by_step[step]
                    assert e['prior_exposed'] and last.endswith(e['cue'])
                    assert e['cue']==PREFIX+e['locator']+'): '+e[arm]
                    assert e['correction']!=e['control']
                    issued.append(e['cue'])
                    if first_cue_prompt is None:
                        first_cue_prompt=rec['prompt']
                        unmarked=list(msgs)
                        if last==e['cue']:
                            unmarked=unmarked[:-1]
                        else:
                            assert last.endswith('\n'+e['cue'])
                            unmarked[-1]={**unmarked[-1],'content':last[:-(len(e['cue'])+1)]}
                        first_unmarked_request=digest(compact({**req,'messages':unmarked}))
                else:
                    assert PREFIX not in last
            names=Counter(c['tool'] for ev in t['trace'] for c in ev)
            if t['actions'] is not None:assert t['actions']==sum(names.values())
            em,f1=score(t['answer'],gold[sid])
            row=dict(id=sid,arm=arm,gold=gold[sid],answer=t['answer'],em=em,f1=f1,stop=t['stop'],
                     submitted=bool(names['answer']),actions=t['actions'],events=t['events'],race_events=t['race_events'],
                     read_file=names['read_file'],grep=names['grep'],glob=names['glob'],extra_reads=0,extra_read_bytes=0,
                     requests=t['requests'],request_count=len(t['requests']),cues=len(cues),eligible=sum(len(e['eligible']) for e in cues),
                     cue_bytes=sum(len(s.encode()) for s in issued),phrase_words=sum(len(WORDS.findall(e[arm])) for e in cues),
                     phrase_bytes=sum(len(e[arm].encode()) for e in cues),fallback_controls=sum(e['control']=='Source record refreshed' for e in cues),
                     both_candidate_words_equal=sum(len(WORDS.findall(e['correction']))==len(WORDS.findall(e['control'])) for e in cues),
                     first_cue_request=cues[0]['request'] if cues else None,cue_details=[{u:e[u] for u in ('request','locator','revision','correction','control','tool_id','part')} for e in cues],
                     first_cue_prompt=first_cue_prompt,first_unmarked_request=first_unmarked_request,receipt_sources=t.get('receipt_sources'),sha256=(main_lock if old else lock)[fn])
            for k in ('prompt','completion','cached_prompt'):
                vals=[index[x][k] for x in t['requests']]
                row[k]=sum(vals) if None not in vals else None
            rows.append(row)
            if not old:
                answers.append({k:t[k] for k in ('id','arm','answer')})
    assert sorted(answers,key=lambda r:(r['id'],r['arm']))==sorted(read(HERE/'answers_for_judge.json'),key=lambda r:(r['id'],r['arm']))
    write_checked(HERE/'projection.json.gz',rows)
    write_checked(HERE/'receipt_projection.json.gz',index)
    return rows,index


def summarize(rows,index):
    by={arm:{r['id']:r for r in rows if r['arm']==arm} for arm in ARMS}
    ids=sorted(by['baseline'])
    assert len(ids)==40 and all(sorted(x)==ids for x in by.values())
    draws=np.random.default_rng(20261118).integers(0,40,(10000,40))
    out={'arms':{},'pair':{},'cache':{}}
    metrics=('em','f1','request_count','actions','events','race_events','read_file','grep','glob','extra_reads','prompt','completion','cues','cue_bytes')
    for a,z in by.items():
        rs=list(z.values())
        for r in rs:
            assert (r['em'],r['f1'])==score(r['answer'],r['gold'])
        keys=[k for r in rs for k in r['requests']]
        report={k:sum(r[k] for r in rs) for k in metrics if all(r[k] is not None for r in rs)}
        report['f1']/=40
        report.update(n=len(rs),submitted=sum(r['submitted'] for r in rs),cue_cases=sum(r['cues']>0 for r in rs),
                      eligible=sum(r['eligible'] for r in rs),same_word_length=sum(r['both_candidate_words_equal'] for r in rs),
                      generic_control=sum(r['fallback_controls'] for r in rs),phrase_bytes=sum(r['phrase_bytes'] for r in rs),phrase_words=sum(r['phrase_words'] for r in rs),
                      unique_requests=len(set(keys)),cached_prompt=sum(r['cached_prompt'] for r in rs if r['cached_prompt'] is not None),
                      missing_receipts=sum(k not in index for k in keys),missing_usage=sum(index[k]['prompt'] is None or index[k]['completion'] is None for k in keys),
                      stops=dict(Counter(r['stop'] for r in rs)))
        out['arms'][a]=report
    for a,b in CONTRASTS:
        z={k:paired([by[a][s][k] if by[a][s][k] is not None else np.nan for s in ids],[by[b][s][k] if by[b][s][k] is not None else np.nan for s in ids],draws) for k in metrics}
        z['same_request_sequence']=sum(by[a][s]['requests']==by[b][s]['requests'] for s in ids)
        z['different_answer']=sum(by[a][s]['answer']!=by[b][s]['answer'] for s in ids)
        z['same_first_event']=sum(bool(by[a][s]['cue_details']) and bool(by[b][s]['cue_details']) and by[a][s]['cue_details'][0]==by[b][s]['cue_details'][0] for s in ids)
        def events(r):
            return [(e['request'],e['locator'],e['correction'],e['control']) for e in r['cue_details']]
        z['same_event_sequence']=sum(events(by[a][s])==events(by[b][s]) for s in ids)
        # For the primary pair both branches must receive the same first event and identical pre-cue provider inputs.
        if (a,b)==('correction','control'):
            for s in ids:
                ra,rb=by[a][s],by[b][s]
                assert bool(ra['cues'])==bool(rb['cues'])
                if ra['cues']:
                    j=ra['first_cue_request']-1
                    assert ra['cue_details'][0]==rb['cue_details'][0]
                    assert ra['requests'][:j]==rb['requests'][:j] and ra['requests'][j]!=rb['requests'][j]
                    assert ra['first_unmarked_request']==rb['first_unmarked_request']==by['baseline'][s]['requests'][j]
                else:assert ra['requests']==rb['requests']
            affected=[s for s in ids if by[a][s]['cues']]
            match={}
            draws_first=np.random.default_rng(20261118).integers(0,len(affected),(10000,len(affected)))
            for l,r in ((a,b),(a,'baseline'),(b,'baseline')):
                def firstvalue(s,arm):
                    row=by[arm][s]
                    if arm=='baseline':
                        return index[by[a][s]['first_unmarked_request']]['prompt']
                    return row['first_cue_prompt']
                vals=[[firstvalue(s,arm) for s in affected] for arm in (l,r)]
                ds=paired(*vals,draws_first)
                differences=[x-y for x,y in zip(*vals)]
                ds.update(min_tokens=min(differences),max_tokens=max(differences),median_tokens=float(np.median(differences)))
                match[l+'-'+r]=ds
            z['first_intervention_prompt_token_difference']=match
            direct={}
            def at(s,arm):
                if arm=='baseline':
                    return index[by[a][s]['first_unmarked_request']]
                row=by[arm][s]
                return index[row['requests'][row['first_cue_request']-1]]
            for arm in ARMS:
                receipts=[at(s,arm) for s in affected]
                direct[arm]=dict(attempted_answer=sum('answer' in x['tool_names'] for x in receipts),
                                  first_tool=dict(Counter(x['tool_names'][0] if x['tool_names'] else '[none]' for x in receipts)))
            direct['primary_different_names']=sum(at(s,a)['tool_names']!=at(s,b)['tool_names'] for s in affected)
            direct['primary_different_name_or_arguments']=sum(at(s,a)['action_signature']!=at(s,b)['action_signature'] for s in affected)
            z['descriptive_first_model_action']=direct
        out['pair'][a+'-'+b]=z
    new=[r for r in rows if r['arm']!='baseline']
    source=Counter(k for r in new for k in r['receipt_sources'])
    logical=sum(r['request_count'] for r in new)
    local=sum(len(set(r['requests'])) for r in new)
    within=sum(len({k for r in new if r['id']==sid for k in r['requests']}) for sid in ids)
    keys={k for r in new for k in r['requests']};fresh={k for k in keys if not index[k]['original_receipt']}
    out['cache']=dict(extension_logical=logical,distinct_extension_keys=len(keys),repeated_within_trajectory=logical-local,
                      across_arms_in_same_case=local-within,across_cases=within-len(keys),new_unique_receipts=len(fresh),
                      old_unique_receipts=len(keys)-len(fresh),receipt_sources=dict(source),
                      errors=sum(index[k]['status']!=200 for k in keys),
                      new_physical_prompt=sum(index[k]['prompt'] or 0 for k in fresh),new_physical_completion=sum(index[k]['completion'] or 0 for k in fresh))
    return out


if __name__=='__main__':
    if '--offline' in sys.argv:
        rows,index=read(HERE/'projection.json.gz'),read(HERE/'receipt_projection.json.gz')
    else:
        rows,index=from_traces()
    res=summarize(rows,index)
    write_checked(HERE/'results.json',res)
    print(res['arms'])
    for key,v in res['pair'].items():
        print(key,'em',v['em'],'f1',v['f1'])
    print(res['cache'])
