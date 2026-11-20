"""Scoring-only diagnostic: compare released PR data, never use current fixes in predictions."""
import collections
import csv
import hashlib
import json
import re

import pyarrow.parquet as pq
from prepare import ROOT,load_inputs,parquet,save,sha
from lite_inputs import dump

def footprint(patch):
    files=set();changes=collections.Counter();file='';hunk=False
    for line in (patch or '').splitlines():
        if line.startswith('diff --git '):
            m=re.search(r' b/(.+)$',line)
            file=m[1] if m else '';hunk=False
            if file:files.add(file)
        elif line.startswith('@@'):
            hunk=True
        elif hunk and file and line[:1] in {'+','-'} and line[1:].strip():
            changes[(file,line[:1],' '.join(line[1:].split()))]+=1
    return files,changes

def run():
    assert (ROOT/'results.json').is_file()
    docs,_,_=load_inputs()
    targets={r['instance_id']:r for r in pq.read_table(parquet('SWEContextBench_Related_Lite'),columns=['instance_id','patch']).to_pylist()}
    full_links=list(csv.DictReader((ROOT/'lite_source_links.csv').open(encoding='utf8')))
    qs={r['target']:r for r in csv.DictReader((ROOT/'lite_chronology.csv').open(encoding='utf8'))}
    times=json.loads((ROOT/'github_times.json').read_text(encoding='utf8'))
    rows=[]
    for r in full_links:
        if r['gold']!='True' or r['source'] not in docs:continue
        src=docs[r['source']];p=src['patch'] or '';t=targets[r['target']]['patch'] or ''
        sf,sc=footprint(p);tf,tc=footprint(t);u=(sc|tc).total()
        n=r['source'].rsplit('-',1)[1]
        dt=times[src['repo']].get(n,{}).get('open')
        if not dt:dt=src.get('created_at')
        q=qs[r['target']]
        cutoff=min(d for d in [q['pr_open'],*q['issue_times'].split('|')] if d and d!='?')
        rows.append({**dict((k,r[k]) for k in ['ordinal','target','source','same_pr','chosen_qwen','source_in_lite_library']),'source_open':dt,'source_open_before_target_issue': '' if not dt else dt<cutoff,'source_merge_at_issue':r['issue_start'],
                     'patch_bytes_equal':bool(p and p==t),'changed_lines_exact':bool(sc and sc==tc),'files_equal':bool(sf and sf==tf),
                     'lines_jaccard':(sc&tc).total()/u if u else 0,'src_lines':sc.total(),'target_lines':tc.total(),
                     'src_patch_sha256':sha(p.encode()),'target_patch_sha256':sha(t.encode())})
    dump('lite_patch_overlap.csv',rows)
    summary={}
    for key,subset in [('gold_same_pr',[r for r in rows if r['same_pr']=='True']),('gold_other_pr',[r for r in rows if r['same_pr']=='False']),('qwen_hits_same_pr',[r for r in rows if r['same_pr']=='True' and r['chosen_qwen']=='True'])]:
        summary[key]={'link_pairs':len(subset),'targets':len({r['target'] for r in subset}),'patch_bytes_equal':sum(r['patch_bytes_equal'] for r in subset),'changed_lines_exact':sum(r['changed_lines_exact'] for r in subset),'same_files':sum(r['files_equal'] for r in subset),'mean_line_jaccard':sum(r['lines_jaccard'] for r in subset)/max(1,len(subset))}
    for cond in ['any_gold','qwen_correct']:
        ss=[r for r in rows if r['source_in_lite_library']=='True' and (cond=='any_gold' or r['chosen_qwen']=='True')]
        summary[cond+'_source_pr_opened_before_issue']={str(exc):len({r['target'] for r in ss if r['source_open_before_target_issue'] is True and (not exc or r['same_pr']!='True')}) for exc in [False,True]}
    save('lite_patch_overlap.json',summary)
    print(json.dumps(summary))
if __name__=='__main__':run()

