"""Run only AFTER the blind prediction manifest is final. Gold is used only here."""
import collections
import csv
import hashlib
import json
import math
import random
import re
import statistics
from pathlib import Path
import pyarrow.parquet as pq
from cards import DATA, HERE


def load(name):
    return json.loads((HERE/name).read_text(encoding='utf8'))


def interval(vals):
    s=sorted(vals)
    return [s[round((len(s)-1)*.025)],s[round((len(s)-1)*.975)]]


def pair(rows,method,baseline):
    diffs=[r[method+'_1']-r[baseline+'_1'] for r in rows]
    groups=collections.defaultdict(list)
    for r,d in zip(rows,diffs):
        groups[r['repo']].append(d)
    strata=[(sum(v),len(v)) for v in groups.values()]
    rng=random.Random(20261116)
    boot=[]
    for _ in range(10000):
        rep=rng.choices(strata,k=len(strata))
        boot.append(sum(r[0] for r in rep)/sum(r[1] for r in rep))
    a,b=diffs.count(1),diffs.count(-1)
    p=min(1,2*sum(math.comb(a+b,i) for i in range(min(a,b)+1))/2**(a+b))
    return dict(wins=a,losses=b,delta=statistics.mean(diffs),repo_ci95=interval(boot),mcnemar_p=p,nrepo=len(strata))


def main():
    commit=load('blind_commit.json')
    for name,sha in commit.items():
        assert hashlib.sha256((HERE/name).read_bytes()).hexdigest()==sha
    external_receipts={}
    for name in ['recall_keyword','recall_hybrid']:
        artifact=HERE/(name+'.json')
        if artifact.is_file():
            pin=load(name+'_pin.json')
            assert hashlib.sha256(artifact.read_bytes()).hexdigest()==pin['sha256'][artifact.name]
            external_receipts[name]=pin['sha256'][artifact.name]
    gold=collections.defaultdict(set)
    for r in pq.read_table(DATA/'SWEContextBench_Relationship.parquet',columns=['related_instance_id','experience_instance_id']).to_pylist():
        gold[r['related_instance_id']].add(r['experience_instance_id'])
    library={}
    for f in sorted((DATA/'traces').glob('*.jsonl')):
        for line in f.open(encoding='utf8'):
            try:
                row=json.loads(line)
            except json.JSONDecodeError:
                continue
            msg=row.get('message',{}).get('content')
            if row.get('type')=='user' and isinstance(msg,str) and 'problem_statement:' in msg:
                m=re.search(r'(?m)^\s*instance_id:\s*([^\s]+)',msg)
                if m:
                    library[f.stem]=m[1]
                break
    assert len(library)==300
    members=set(library.values())
    meta=[];seen=set()
    for fname,group in [('SWEContextBench_Related_Lite','lite'),('SWEContextBench_Related','extension')]:
        for row in pq.read_table(DATA/(fname+'.parquet'),columns=['instance_id','repo']).to_pylist():
            if row['instance_id'] not in seen:
                seen.add(row['instance_id']);meta.append({**row,'group':group})
    qwen={r['ordinal']:r for r in map(json.loads,(HERE/'qwen_calls.jsonl').read_text(encoding='utf8').splitlines())}
    ranks=load('blind_ranks.json')
    assert len(meta)==len(ranks) and len(qwen)==99
    author_controls=[]
    for name in ['recall_keyword','recall_hybrid']:
        artifact=HERE/(name+'.json')
        if artifact.is_file():
            external=load(artifact.name)
            assert [v['ordinal'] for v in external]==list(range(99))
            for v in external:
                assert set(v[name])<=set(library)
                ranks[v['ordinal']][name]=v[name]
            author_controls.append(name)
    rows=[];bygroup=collections.defaultdict(list)
    for i,(r,m) in enumerate(zip(ranks,meta)):
        assert i==r['ordinal']
        target=gold[m['instance_id']]
        row={**m,'ordinal':i, 'gold_ids':'|'.join(sorted(target)), 'n_gold':len(target),'available':int(bool(members&target))}
        for k,rank in r.items():
            if k=='ordinal':continue
            for j in [1,3,5,10]:
                row[k+'_'+str(j)]=int(any(library[t] in target for t in rank[:j]))
        if i in qwen:
            row['qwen_1']=int(library[qwen[i]['choice']] in target)
        rows.append(row);bygroup[m['group']].append(row)
    assert len(bygroup['lite'])==99 and all(r['n_gold'] for r in rows)
    fields=list(dict.fromkeys(k for r in rows for k in r))
    with (HERE/'per_query.csv').open('w',newline='',encoding='utf8') as f:
        w=csv.DictWriter(f,fields);w.writeheader();w.writerows(rows)
    out={'unique_source_issue_ids':len(members),'source_records':len(library),'groups':{},'pairwise':{},'author_controls':author_controls,'external_prediction_hashes':external_receipts,'official':{'paper':'REM','lite_match_at_one':68,'lite_n':99,'matched_outputs_available':False}}
    groups={**bygroup, 'extension_available':[r for r in bygroup['extension'] if r['available']]}
    for g,rr in groups.items():
        if not rr:continue
        scorecols=[k for k in rr[0] if re.search(r'_(1|3|5|10)$',k)]
        out['groups'][g]={'n':len(rr),'repos':len({r['repo'] for r in rr}),'multigold':sum(r['n_gold']>1 for r in rr),'available':sum(r['available'] for r in rr),'scores':{k:sum(r[k] for r in rr) for k in scorecols}}
        method='qwen' if g=='lite' else 'fusion'
        comparators=['bm25_flat','bm25_symptom','bm25_outcome','sparse_fields','dense_flat','minilm','fusion']
        if g=='lite':
            comparators.extend(author_controls)
        out['pairwise'][g]={b:pair(rr,method,b) for b in comparators if b!=method}
    out['llm_cost']={'calls':len(qwen),'fallback':sum(v['fallback'] for v in qwen.values()),'input':sum(v['usage'].get('prompt_tokens',0) for v in qwen.values()),'output':sum(v['usage'].get('completion_tokens',0) for v in qwen.values()),'seconds':sum(v['seconds'] for v in qwen.values())}
    success=out['groups']['lite']['scores']['qwen_1']
    bounds=[]
    for common in range(max(0,success+68-99),min(success,68)+1):
        wins,loss=success-common,68-common
        prob=min(1,2*sum(math.comb(wins+loss,i) for i in range(min(wins,loss)+1))/2**(wins+loss))
        bounds.append(prob)
    out['official']['possible_exact_p_range_given_only_marginals']=[min(bounds),max(bounds)]
    out['official']['our_possible_hit_count_after_excluding_eight_unknown_missing_targets']=[max(0,success-8),min(success,91)]
    out['storage']={'input_raw_bytes':sum(p.stat().st_size for p in (DATA/'traces').glob('*.jsonl')),'record_text_bytes':sum(len(c[f].encode()) for c in load('cards.json') for f in ['symptom','closure','edits']),'json_file_bytes':(HERE/'cards.json').stat().st_size,'avg_words':statistics.mean(sum(len(c[f].split()) for f in ['symptom','closure','edits']) for c in load('cards.json'))}
    (HERE/'results.json').write_text(json.dumps(out,indent=2),encoding='utf8')
    print(json.dumps(out['groups'],indent=1))
if __name__=='__main__':
    main()

