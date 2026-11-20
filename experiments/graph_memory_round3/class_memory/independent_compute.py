"""Deduplicate actual llama.cpp calls across completed branches and match speed counters against the server log."""
from collections import defaultdict, Counter
import json
import re
from independent_audit import HERE, digest, get, req_key, write
from independent_sealed import load_seals


def parse_native():
    msg=(HERE/'server.stderr').read_text(encoding='utf8',errors='replace')
    jobs=defaultdict(dict)
    regex=r'slot print_timing: id\s+\d+\s+\|\s+task\s+(\d+)\s+\|\s*(prompt eval|eval) time\s*=\s*([\d.]+) ms\s*/\s*(\d+) tokens?'
    for jid,what,ms,tokens in re.findall(regex,msg):
        jobs[jid][what]=(float(ms),int(tokens))
    return jobs


def same_timing(r, trace):
    if set(trace)!={'prompt eval','eval'}:return False
    t=r['reply']['timings'];p,pt=trace['prompt eval'];e,et=trace['eval']
    return (t['prompt_n']==pt and t['predicted_n']==et and abs(t['prompt_ms']-p)<.021 and abs(t['predicted_ms']-e)<.021)


def main():
    seals=load_seals()
    hist={}; byid={}; native=defaultdict(list)
    for folder in ('calls','online_calls'):
        hist[folder]={}
        for p in (HERE/folder).glob('*.json.gz'):
            r=get(p);rid=r['reply']['id'];k=r['key']
            assert k==p.name.split('.')[0]==req_key(r['request'])
            if rid in byid:assert r==byid[rid]
            byid[rid]=r;native[rid].append(folder);hist[folder][k]=rid
    shared=set(hist['calls'])&set(hist['online_calls'])
    reused={k for k in shared if hist['calls'][k]==hist['online_calls'][k]}
    twice=shared-reused
    diff_payloads=sum(byid[hist['calls'][k]]['reply']['choices'][0]['message'].get('content')!=
                      byid[hist['online_calls'][k]]['reply']['choices'][0]['message'].get('content') for k in twice)
    jobs=parse_native()
    links={rid:[j for j,tr in jobs.items() if same_timing(r,tr)] for rid,r in byid.items()}
    known=[lst[0] for lst in links.values() if len(lst)==1]
    assert len(set(known))==len(known)
    unknown=[rid for rid,l in links.items() if len(l)!=1]
    extras=sorted(set(jobs)-set(known),key=int)
    totals={'native_requests_by_completion_id':len(byid),
            'unique_stimuli_both':len(set(hist['calls'])|set(hist['online_calls'])),
            'distinct_stimuli_teacher':len(hist['calls']),'distinct_stimuli_online':len(hist['online_calls']),
            'stimuli_common_both':len(shared),'same_physical_receipt_across_branches':len(reused),
            'same_stimulus_computed_twice':len(twice),'among_computed_twice_different_generated_text':diff_payloads,
            'combined_logical_assignments':len(get('assignment.json'))*6 + sum(len(c['targets'])*3 for c in get('online_visible.json'))}
    for field in ['prompt_tokens','completion_tokens','total_tokens']:
        totals[field]=sum(r['reply']['usage'][field] for r in byid.values())
    for field in ['prompt_n','predicted_n','cache_n','prompt_ms','predicted_ms']:
        totals[field]=sum(r['reply']['timings'][field] for r in byid.values())
    totals['client_seconds_sum_including_queue']=sum(r['elapsed'] for r in byid.values())
    result={'totals':totals,'server_log':dict(matched_unique_native_log_tasks=len(known),unmatched_receipt_ids=unknown,
            other_log_tasks_not_assigned_to_these_decisions=extras,native_timing_records=len(jobs)),
            'shared_stimuli_computed_twice':sorted(twice),'fixed_method_sets':seals}
    write('independent_compute.json',result)


if __name__=='__main__':main()

