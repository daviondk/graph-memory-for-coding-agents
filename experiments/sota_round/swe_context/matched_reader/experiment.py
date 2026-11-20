"""Prepare, execute and audit the two matched readers. No labels are loaded."""
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import time

import requests

HERE = Path(__file__).resolve().parent
PARENT = HERE.parent
sys.path.insert(0, str(PARENT))
import choose as original

ARMS = ('no_edits', 'recall_five')


def read(path):
    return json.loads(path.read_text(encoding='utf8'))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def stamp():
    return datetime.now(timezone.utc).isoformat()


def jsonl(path):
    return [json.loads(line) for line in path.read_text(encoding='utf8').splitlines() if line] if path.is_file() else []


def save(path, obj):
    tmp = path.with_suffix('.tmp')
    tmp.write_text(json.dumps(obj, indent=2, ensure_ascii=False)+'\n', encoding='utf8')
    tmp.replace(path)


def append(path, obj):
    with path.open('a', encoding='utf8') as handle:
        handle.write(json.dumps(obj, ensure_ascii=False)+'\n')
        handle.flush()
        os.fsync(handle.fileno())


def payload(task, slate, cards, redact):
    order = sorted(slate, key=lambda k: original.digest('choice|'+str(task['ordinal'])+'|'+k))
    records=[]
    for ix,key in enumerate(order,1):
        option={'index':ix}
        for field,cap in [('symptom',175),('closure',90),('edits',40)]:
            option[field] = '' if redact and field=='edits' else ' '.join(cards[key][field].split()[:cap])
        records.append(option)
    inp=json.dumps({'current_issue':task['query'],'prior_experiences':records},ensure_ascii=False)
    messages=[{'role':'system','content':original.SYSTEM},{'role':'user','content':inp}]
    return {'model':original.MODEL,'messages':messages,'temperature':0,'seed':20261116,'max_tokens':12,'stream':False}, order


def build_plan():
    for name,h in read(PARENT/'blind_commit.json').items():
        assert sha(PARENT/name)==h, name
    assert sha(PARENT/'recall_hybrid.json')==read(PARENT/'recall_hybrid_pin.json')['sha256']['recall_hybrid.json']
    priors=jsonl(PARENT/'qwen_calls.jsonl')
    assert len(priors)==99
    gold_free={r['ordinal']:r for r in priors}
    tasks=read(PARENT/'queries.json')[:99]
    cards={c['key']:c for c in read(PARENT/'cards.json')}
    ranks=read(PARENT/'blind_ranks.json')
    ext=read(PARENT/'recall_hybrid.json')
    plans=[]
    for i,task in enumerate(tasks):
        assert task['ordinal']==ranks[i]['ordinal']==ext[i]['ordinal']==i and task['group']=='lite'
        orig=ranks[i]['fusion'][:5]
        full,orig_order=payload(task,orig,cards,False)
        assert orig_order==gold_free[i]['order']
        assert original.digest(json.dumps(full,ensure_ascii=False))==gold_free[i]['payload_sha256']
        for arm in sorted(ARMS,key=lambda a:original.digest(a+'|'+str(i))):
            slate=orig if arm=='no_edits' else ext[i]['recall_hybrid'][:5]
            assert len(set(slate))==5
            body,order=payload(task,slate,cards,arm=='no_edits')
            plans.append(({'ordinal':i,'arm':arm,'base_slate':slate,'order':order,'payload_sha256':original.digest(json.dumps(body,ensure_ascii=False))},body))
    return plans


def freeze(plans):
    plan=HERE/'slates.json'
    lock=HERE/'freeze.json'
    assert not lock.exists() and not (HERE/'calls.jsonl').exists()
    save(plan,[p for p,_ in plans])
    files={n:sha(HERE/n) for n in ['experiment.py','score_followup.py','PROTOCOL.md','slates.json']}
    parents={n:sha(PARENT/n) for n in ['blind_commit.json','recall_hybrid_pin.json','recall_hybrid.json']}
    save(lock,{'utc':stamp(),'local':files,'parent':parents,'jobs':len(plans),'original_payload_hashes_matched':99})


def validate():
    lock=read(HERE/'freeze.json')
    for folder,entries in [(HERE,lock['local']),(PARENT,lock['parent'])]:
        for n,h in entries.items():
            assert sha(folder/n)==h,n


def run(plans):
    validate()
    assert [p for p,_ in plans]==read(HERE/'slates.json')
    calls=HERE/'calls.jsonl'
    prior=jsonl(calls)
    done={(r['ordinal'],r['arm']):r for r in prior}
    assert len(done)==len(prior)
    for row,body in plans:
        key=row['ordinal'],row['arm']
        if key in done:
            assert done[key]['payload_sha256']==row['payload_sha256']
            continue
        for attempt in range(1,6):
            start=time.monotonic()
            try:
                r=requests.post(original.URL,json=body,timeout=300)
                r.raise_for_status()
                out=r.json()
                ch=out['choices'][0]
                raw=ch['message'].get('content') or ''
                usage=out['usage']
                assert usage['prompt_tokens']>0 and 0<=usage['completion_tokens']<=12
                break
            except (requests.RequestException,KeyError) as exc:
                append(HERE/'transport_errors.jsonl',{**row,'utc':stamp(),'attempt':attempt,'error':str(exc)[:240]})
                if attempt==5:raise
                time.sleep(min(4**attempt,40))
        match=re.fullmatch(r'\s*([1-5])[.)]?\s*',raw)
        choice=row['order'][int(match[1])-1] if match else row['base_slate'][0]
        append(calls,{**row,'choice':choice,'raw':raw,'fallback':not bool(match),'usage':usage,'response_id':out.get('id'),'model':out.get('model'),'finish':ch.get('finish_reason'),'endpoint':original.URL,'seconds':time.monotonic()-start,'utc':stamp()})
    rows=jsonl(calls)
    assert len(rows)==len({(r['arm'],r['ordinal']) for r in rows})==198
    assert Counter(r['arm'] for r in rows)=={arm:99 for arm in ARMS}
    save(HERE/'blind_commit.json',{'locked_utc':stamp(),'freeze':sha(HERE/'freeze.json'),'predictions':sha(calls),'calls':len(rows)})


if __name__=='__main__':
    args=argparse.ArgumentParser()
    args.add_argument('action',choices=['prepare','run'])
    mode=args.parse_args().action
    plans=build_plan()
    if mode=='prepare':freeze(plans)
    else:run(plans)

