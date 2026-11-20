"""Label-free chronology inputs for the original 300 trajectories and 99 tasks."""
import csv
import json
import pyarrow.parquet as pq
from prepare import ROOT,load_inputs,parquet,save,sha,stamp

def dump(name,rows):
    with (ROOT/name).open('w',newline='',encoding='utf8') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)

def run():
    orig=ROOT.parents[1]/'sota_round'/'swe_context'
    docs,_,_=load_inputs()
    times=json.loads((ROOT/'github_times.json').read_text(encoding='utf8'))
    refs=json.loads((ROOT/'case_refs.json').read_text(encoding='utf8'))
    source=[]
    for rec in csv.DictReader((orig/'evaluation_library.csv').open(encoding='utf8')):
        iid=rec['instance_id']
        repo=docs[iid]['repo'];n=iid.rsplit('-',1)[1]
        evidence=times[repo].get(n,{})
        source.append({**rec,'repo':repo,'source_pr':n,'source_merge':evidence.get('merge'),
                       'source_merge_source':evidence.get('merge_source','GHArchive') if evidence.get('merge') else 'unknown',
                       'source_url':'https://github.com/'+repo+'/pull/'+n})
    queries=[]
    for j,row in enumerate(pq.read_table(parquet('SWEContextBench_Related_Lite'),columns=['instance_id','repo','created_at']).to_pylist()):
        iid=row['instance_id'];repo=row['repo'];r=refs[iid];n=str(r['pull_number'])
        ev=times[repo].get(n,{})
        pr_open=ev.get('open') or stamp(row['created_at'])
        dates=[v['open'] for v in r['issue_clock']]
        cut=min([d for d in dates+[pr_open,stamp(row['created_at'])] if d])
        good=bool(pr_open and dates and all(dates))
        queries.append({'ordinal':j,'target':iid,'repo':repo,'target_pr':n,'cutoff_utc':cut,
                        'opening_complete':int(good),'pr_open':pr_open,'pr_merge':ev.get('merge'),
                        'issue_urls':'|'.join(v['url'] for v in r['issue_clock']),'issue_opens':'|'.join(d or '?' for d in dates),
                        'issue_sources':'|'.join(v['source'] for v in r['issue_clock']),
                        'target_pr_url':'https://github.com/'+repo+'/pull/'+n})
    assert len(queries)==99 and len(source)==300
    dump('source_times_lite.csv',source);dump('query_times_lite.csv',queries)
    save('lite_times_receipt.json',{n:sha((ROOT/n).read_bytes()) for n in ['source_times_lite.csv','query_times_lite.csv','issue_dates.json','github_times.json','case_refs.json']})
    print('known source dates',sum(bool(r['source_merge']) for r in source),'complete cutoffs',sum(r['opening_complete'] for r in queries))
if __name__=='__main__':run()

