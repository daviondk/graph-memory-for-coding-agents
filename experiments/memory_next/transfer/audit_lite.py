"""Read linked labels only after blind rank freeze, and classify existing Lite picks by PR chronology."""
import collections
import csv
import json
from pathlib import Path
import pyarrow.parquet as pq
from prepare import ROOT,load_inputs,parquet,save,sha,stamp

EARLIER=ROOT.parents[1]/'sota_round'/'swe_context'
CLOCKS=['issue_start','pr_open','pr_merge']


def normrepo(s):
    return s.lower()


def judge(merge,same,observed,complete):
    if same:return 'nonpast'
    if not observed or not merge:return 'unknown'
    if merge>=min(observed):return 'nonpast'
    return 'past' if complete else 'unknown'


def combine(status):
    if 'past' in status:return 'past'
    if 'unknown' in status:return 'unknown'
    return 'nonpast_or_absent'


def run():
    assert (ROOT/'blind_freeze.json').exists()
    docs,_,_=load_inputs()
    qrows=pq.read_table(parquet('SWEContextBench_Related_Lite'),columns=['instance_id','repo','created_at']).to_pylist()
    rel=collections.defaultdict(list)
    for r in pq.read_table(parquet('SWEContextBench_Relationship'),columns=['related_instance_id','experience_instance_id']).to_pylist():
        v=r['experience_instance_id']
        if v not in rel[r['related_instance_id']]:rel[r['related_instance_id']].append(v)
    lib={r['trace_key']:r['instance_id'] for r in csv.DictReader((EARLIER/'evaluation_library.csv').open())}
    members=set(lib.values())
    qwen={v['ordinal']:lib[v['choice']] for v in map(json.loads,(EARLIER/'qwen_calls.jsonl').read_text(encoding='utf8').splitlines())}
    backups={
        'fusion':{r['ordinal']:lib[r['fusion'][0]] for r in json.loads((EARLIER/'blind_ranks.json').read_text(encoding='utf8'))},
        'recall_hybrid':{r['ordinal']:lib[r['recall_hybrid'][0]] for r in json.loads((EARLIER/'recall_hybrid.json').read_text(encoding='utf8'))},
    }
    t=json.loads((ROOT/'github_times.json').read_text());refs=json.loads((ROOT/'case_refs.json').read_text())
    rows=[];links=[]
    for i,q in enumerate(qrows):
        target=q['instance_id'];repo=q['repo'];ref=refs[target];pr=str(ref['pull_number']);issues=[str(s) for s in ref['issue_numbers']]
        events=t[repo]
        pe=events.get(pr,{})
        pr_open=pe.get('open') or stamp(q['created_at'])
        issue_times=[x['open'] for x in ref['issue_clock']]
        observed=[s for s in [pr_open,*issue_times] if s]
        complete=bool(pr_open and issues and all(issue_times))
        cuts=[(observed,complete),([pr_open] if pr_open else [],bool(pr_open)),([pe['merge']] if pe.get('merge') else [],bool(pe.get('merge')))]
        g=rel[target];picked=qwen[i]
        out={'ordinal':i,'target':target,'repo':repo,'target_pr':pr,'target_issues':'|'.join(issues),'issue_times':'|'.join(d or '?' for d in issue_times),
             'pr_open':pr_open,'pr_merge':pe.get('merge'),'fully_observed_start':complete,'pr_open_source':pe.get('open_source','GHArchive') if pe.get('open') else 'release created_at','pr_merge_source':pe.get('merge_source','GHArchive') if pe.get('merge') else 'unknown',
             'issue_clock_sources':'|'.join(x['source'] for x in ref['issue_clock']),'target_issue_urls':'|'.join(x['url'] for x in ref['issue_clock']),'target_pr_url':'https://github.com/'+repo+'/pull/'+pr,
             'gold':'|'.join(g),'qwen':picked,'ngold':len(g),'qwen_any_correct':picked in g,'qwen_first_correct':picked==g[0],'qwen_last_correct':picked==g[-1]}
        pickers={'qwen':picked,'fusion':backups['fusion'][i],'recall_hybrid':backups['recall_hybrid'][i]}
        for arm,exp in pickers.items():out[arm+'_any_correct']=exp in g
        statuses={}
        same={}
        for exp in dict.fromkeys([*g,*pickers.values()]):
            exp_repo=docs[exp]['repo'] if exp in docs else exp.rsplit('-',1)[0].replace('__','/')
            num=exp.rsplit('-',1)[1];ev=t.get(exp_repo,{}).get(num,{})
            is_same=normrepo(exp_repo)==normrepo(repo) and num==pr
            stat={c:judge(ev.get('merge'),is_same,*cut) for c,cut in zip(CLOCKS,cuts)}
            statuses[exp]=stat;same[exp]=is_same
            links.append({'ordinal':i,'target':target,'source':exp,'gold':exp in g,'chosen_qwen':exp==picked,'source_in_lite_library':exp in members,'same_pr':is_same,
                          'source_pr_url':'https://github.com/'+exp_repo+'/pull/'+num,'merge':ev.get('merge'),'merge_source':ev.get('merge_source','GHArchive') if ev.get('merge') else 'unknown',**stat})
            if exp==picked:
                out.update(qwen_source_merge=ev.get('merge'),qwen_source_url=links[-1]['source_pr_url'],qwen_merge_source=links[-1]['merge_source'])
        out['same_pr_among_gold']=any(same[v] for v in g)
        out['same_pr_qwen']=same[picked]
        for c in CLOCKS:
            for rule,ids in [('any',g),('first',[g[0]]),('last',[g[-1]])]:
                out[c+'_'+rule+'_gold_available']=combine([statuses[e][c] if e in members else 'absent' for e in ids])
            for arm,exp in pickers.items():out[c+'_'+arm+'_clock']=statuses[exp][c]
        rows.append(out)
    for name,rr in [('lite_chronology.csv',rows),('lite_source_links.csv',links)]:
        with (ROOT/name).open('w',encoding='utf8',newline='') as f:
            w=csv.DictWriter(f,fieldnames=list(rr[0]));w.writeheader();w.writerows(rr)
    npr=len(set((r['repo'].lower(),r['target_pr']) for r in rows))
    obj={'n':len(rows),'unique_target_prs':npr,'all_issue_open_confirmed':sum(r['fully_observed_start'] for r in rows),
         'same_target_pr_among_gold':sum(r['same_pr_among_gold'] for r in rows),'same_target_pr_for_qwen':sum(r['same_pr_qwen'] for r in rows),'qwen_correct_same_pr':sum(r['same_pr_qwen'] and r['qwen_any_correct'] for r in rows),'clocks':{}}
    for c in CLOCKS:
        m={}
        for rule in ['any','first','last']:
            m[rule+'_gold_availability']=dict(collections.Counter(r[c+'_'+rule+'_gold_available'] for r in rows))
            m[rule+'_qwen_hits']=dict(collections.Counter(r[c+'_qwen_clock'] for r in rows if r['qwen_'+rule+'_correct']))
        for arm in ['qwen','fusion','recall_hybrid']:
            m[arm+'_all_picks']=dict(collections.Counter(r[c+'_'+arm+'_clock'] for r in rows))
            m[arm+'_correct_picks']=dict(collections.Counter(r[c+'_'+arm+'_clock'] for r in rows if r[arm+'_any_correct']))
        obj['clocks'][c]=m
    obj['source_hashes']={n:sha((EARLIER/n).read_bytes()) for n in ['evaluation_library.csv','qwen_calls.jsonl','blind_ranks.json','recall_hybrid.json']}
    save('lite_chronology.json',obj)
    print(json.dumps(obj,ensure_ascii=False,indent=1))


if __name__=='__main__':run()

