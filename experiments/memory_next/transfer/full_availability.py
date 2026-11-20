"""Score-time availability decomposition across distinct official targets."""
import collections
import json
import pyarrow.parquet as pq
from prepare import ROOT,parquet,load_inputs,save,stamp
from lite_inputs import dump

def run():
    assert (ROOT/'results.json').exists()
    docs,_,_=load_inputs()
    refs=json.loads((ROOT/'case_refs.json').read_text(encoding='utf8'))
    times=json.loads((ROOT/'github_times.json').read_text(encoding='utf8'))
    rel=collections.defaultdict(set)
    for row in pq.read_table(parquet('SWEContextBench_Relationship'),columns=['related_instance_id','experience_instance_id']).to_pylist():rel[row['related_instance_id']].add(row['experience_instance_id'])
    lite=set(pq.read_table(parquet('SWEContextBench_Related_Lite'),columns=['instance_id']).column(0).to_pylist())
    tasks={r['instance_id']:r for r in pq.read_table(parquet('SWEContextBench_Related'),columns=['instance_id','repo','created_at']).to_pylist()}
    rows=[]
    for iid,q in tasks.items():
        ref=refs[iid];repo=q['repo'];pn=str(ref['pull_number'])
        open_pr=times[repo].get(pn,{}).get('open') or stamp(q['created_at'])
        dates=[d['open'] for d in ref['issue_clock']]
        cutoff=min(d for d in [open_pr,stamp(q['created_at']),*dates] if d)
        complete=bool(open_pr and dates and all(dates))
        stat=[]
        for did in sorted(rel[iid]):
            d=docs.get(did)
            if not d:stat.append('absent');continue
            num=did.rsplit('-',1)[1]
            if d['repo'].lower()==repo.lower() and num==pn:stat.append('same_target_pr');continue
            dt=times[d['repo']].get(num,{}).get('merge')
            stat.append('uncertain' if not dt else 'after_or_at' if dt>=cutoff else 'past' if complete else 'uncertain')
        label='past' if 'past' in stat else 'unknown' if 'uncertain' in stat else 'not_past_or_absent'
        rows.append({'target':iid,'repo':repo,'lite':int(iid in lite),'target_pr':pn,'cutoff':cutoff,'complete_cutoff':int(complete),'refs':'|'.join(sorted(rel[iid])),'link_states':'|'.join(stat),'any_past_gold':label,'any_same_target_pr':int('same_target_pr' in stat)})
    dump('full_chronology.csv',rows)
    o={}
    for scope,rs in [('all',rows),('lite',[r for r in rows if r['lite']]),('other',[r for r in rows if not r['lite']])]:
        o[scope]={'targets':len(rs),'repos':len({r['repo'] for r in rs}),'unique_target_prs':len({(r['repo'],r['target_pr']) for r in rs}),'chronology':dict(collections.Counter(r['any_past_gold'] for r in rs)),'same_pr':sum(r['any_same_target_pr'] for r in rs),'complete_cutoffs':sum(r['complete_cutoff'] for r in rs)}
    save('full_availability.json',o);print(json.dumps(o))
if __name__=='__main__':run()

