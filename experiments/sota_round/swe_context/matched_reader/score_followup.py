"""Unseal labels after all 198 predictions are locked; never feed them back."""
import csv
import json
from pathlib import Path
import re
from collections import defaultdict
import os
from experiment import ARMS, HERE, PARENT, jsonl, read, save, sha, validate
from score import pair


def evaluate():
    validate()
    commit=read(HERE/'blind_commit.json')
    assert commit['calls']==198 and commit['freeze']==sha(HERE/'freeze.json') and commit['predictions']==sha(HERE/'calls.jsonl')
    data=Path(os.environ.get('SWE_CONTEXT_DATA','D:/CodexResearch/x20-swe-context'))
    lib={}
    for path in sorted((data/'traces').glob('*.jsonl')):
        for line in path.open(encoding='utf8'):
            try:r=json.loads(line)
            except json.JSONDecodeError:continue
            msg=r.get('message',{}).get('content')
            if r.get('type')=='user' and isinstance(msg,str) and 'problem_statement:' in msg:
                m=re.search(r'(?m)^\s*instance_id:\s*([^\s]+)',msg)
                if m:lib[path.stem]=m[1]
                break
    assert len(lib)==300
    with (PARENT/'per_query.csv').open(encoding='utf8',newline='') as f:
        gold={int(r['ordinal']):r for r in csv.DictReader(f) if r['group']=='lite'}
    assert len(gold)==99
    primary=jsonl(PARENT/'qwen_calls.jsonl')
    calls=jsonl(HERE/'calls.jsonl')
    by={(r['arm'],r['ordinal']):r for r in calls}
    native=read(PARENT/'blind_ranks.json')
    report=[];costs={}
    for a in ['primary',*ARMS]:
        subset=primary if a=='primary' else [c for c in calls if c['arm']==a]
        costs[a]={'n':len(subset),'input':sum(c['usage']['prompt_tokens'] for c in subset),
                  'output':sum(c['usage']['completion_tokens'] for c in subset),'seconds':sum(c['seconds'] for c in subset),
                  'fallback':sum(c['fallback'] for c in subset),'models':sorted({c['model'] for c in subset})}
    for old in primary:
        i=old['ordinal']; g=gold[i]
        labels=set(g['gold_ids'].split('|'))
        orig=native[i]['fusion'][:5]
        item={'ordinal':i,'repo':g['repo'],'primary_1':int(lib[old['choice']] in labels),
              'primary_top5':int(any(lib[k] in labels for k in orig)),'primary_retriever_1':int(lib[orig[0]] in labels)}
        assert item['primary_1']==int(g['qwen_1']) and item['primary_top5']==int(g['fusion_5'])
        for arm in ARMS:
            r=by[arm,i];slate=r['base_slate']
            item.update({arm+'_1':int(lib[r['choice']] in labels),arm+'_changed':int(old['choice']!=r['choice']),
                         arm+'_top5':int(any(lib[k] in labels for k in slate)),arm+'_retriever_1':int(lib[slate[0]] in labels),
                         arm+'_overlap':len(set(orig)&set(slate)),arm+'_same_set':int(set(orig)==set(slate))})
            if arm=='no_edits':assert slate==orig and r['order']==old['order']
            else:assert item[arm+'_top5']==int(g['recall_hybrid_5'])
        report.append(item)
    with (HERE/'paired.csv').open('w',encoding='utf8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(report[0]));w.writeheader();w.writerows(report)
    counts={k:sum(r[k] for r in report) for k in report[0] if k not in ('ordinal','repo')}
    pairs={arm:pair(report,arm,'primary') for arm in ARMS}
    ordered=sorted(ARMS,key=lambda a:pairs[a]['mcnemar_p'])
    previous=0
    for rank,arm in enumerate(ordered):
        p=min(1,max(previous,(len(ARMS)-rank)*pairs[arm]['mcnemar_p']))
        pairs[arm]['holm_p']=p;previous=p
    save(HERE/'results.json',{'n':len(report),'counts':counts,'paired':pairs,'costs':costs,'primary_score_source_sha256':sha(PARENT/'per_query.csv'),'locked_predictions_sha256':commit['predictions']})
    print(json.dumps({'counts':counts,'paired':pairs}))


if __name__=='__main__':
    evaluate()

