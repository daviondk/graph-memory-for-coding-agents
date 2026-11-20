from collections import Counter
from concurrent.futures import ThreadPoolExecutor
import re,json
from source import ROOT,R8,base,h,official_ids,index,inputs,member,write_json

UNSAFE_REPO=re.compile(r'jwt|two.factor|security|oauth|authenticat|crypto|securedrop|pyopenssl|greedybear|bridgecrew|sancus|exploit|malware|airbrake|rocketry|missile|genomics|synbio|pyrail-security|pyhanko|safety-db|checkov|vdrs-solutions',re.I)
UNSAFE_QUERY=re.compile(r'\b(?:CVE|exploit(?:s|ed|ation)?|vulnerabilit(?:y|ies)|arbitrary code execution|security|code scanning|injection|denial.of.service|penetration|weapon|warhead|rocket|malware|ransomware|path traversal|authentication bypass|genome editing|pathogen|virus culture)\b',re.I)
BANDS=[(0,20000),(20000,50000),(50000,80000)]
def screening(tn):
    t,n=tn
    if UNSAFE_REPO.search(t):return {'issue':t,'reason':'domain','bytes':n}
    q,qhash=inputs(t)
    if UNSAFE_QUERY.search(q):return {'issue':t,'reason':'issue domain','bytes':n}
    raw=member(base(t)+'corpus.jsonl')
    rows=[json.loads(x) for x in raw.splitlines()]
    unique={r['_id'] for r in rows}
    assert len(unique)==len(rows) and not any(r.get('title') for r in rows)
    return {'issue':t,'repo':t.rsplit('-',1)[0],'reason':'eligible' if 11<=len(rows)<=450 else 'function count','bytes':n,'functions':len(rows),'corpus_sha256':h(raw),'query_file_sha256':qhash}
def main():
    ids,sha=official_ids()
    old={f.stem for f in (R8/'loc_predictions').glob('*.json')}
    archive={p.split('loc-bench-function_')[1].split('/')[0]:s[1] for p,s in index().items() if p.startswith('datasets/loc-bench-function_') and p.endswith('/corpus.jsonl')}
    assert ids<=archive.keys()
    selected=[];trace=[];used=set()
    for lo,hi in BANDS:
        candidates=sorted(((t,s) for t,s in archive.items() if t in ids and t not in old and lo<s<=hi),key=lambda x:h('R9-witness-v1|'+x[0]))
        with ThreadPoolExecutor(max_workers=8) as pool:
            screen=list(pool.map(screening,candidates))
        n=0
        for row in screen:
            row['band']=f'{lo}-{hi}'
            if row['reason']=='eligible' and row['repo'] not in used and n<6:
                selected.append(row.copy());used.add(row['repo']);n+=1
        trace.extend(screen)
    audit={'n_archive':len(archive),'n_official':len(ids),'n_in_archive_and_official':len(ids&archive.keys()),'n_previously_scored_in_test':len(ids&old),'n_test_remaining':len(ids-old),'n_outside_size':sum(archive[t]>80000 for t in ids-old),'counts':dict(Counter(r['reason'] for r in trace)),'n_eligible_repo':len({r['repo'] for r in trace if r['reason']=='eligible'}),'sampling_trace':trace,'selected':selected,'official_split_sha256':sha,'protocol_sha256':h((ROOT/'PROTOCOL.md').read_bytes()),'sampling_code_sha256':h((ROOT/'sample.py').read_bytes())}
    write_json(ROOT/'sample.json',audit)
    print('selected',len(selected),'functions',sum(r['functions'] for r in selected),'bands',dict(Counter(r['band'] for r in selected)),flush=True)
if __name__=='__main__':main()
