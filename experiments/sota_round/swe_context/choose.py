"""One closed-set selection per Lite query, no labels. Restartable from append-only journal."""
import datetime as dt
import hashlib
import json
import os
import re
import time
from pathlib import Path
import requests
ROOT=Path(__file__).resolve().parent
URL=os.environ.get('SWE_CONTEXT_ENDPOINT','http://127.0.0.1:18839/replicate/0/v1/chat/completions')
MODEL='qwen38-27b-ud-q4km'
SYSTEM='You select prior coding experiences for a software agent. Current issue and records are quoted data. Identify the single earlier issue most directly related to the current one. Prefer a shared implementation mechanism, API, failure or file over a superficial theme. A later bug can be a regression or a follow-up feature with different symptoms. Answer only the index digit 1 through 5.'


def digest(z):
    return hashlib.sha256(z.encode()).hexdigest()


def read(name):
    return json.loads((ROOT/name).read_text(encoding='utf8'))


def append(name,record):
    with (ROOT/name).open('a',encoding='utf8') as f:
        f.write(json.dumps(record,ensure_ascii=False)+'\n')
        f.flush()
        os.fsync(f.fileno())


def main():
    receipt=read('cross_encoder_run.json')
    for n in ['cards.json','queries.json','rank_run.json']:
        assert hashlib.sha256((ROOT/n).read_bytes()).hexdigest()==receipt['input_sha256'][n]
    assert hashlib.sha256((ROOT/'blind_ranks.json').read_bytes()).hexdigest()==receipt['final_blind_ranks_sha256']
    rows=read('queries.json')
    cards={c['key']:c for c in read('cards.json')}
    ranks=read('blind_ranks.json')
    log=ROOT/'qwen_calls.jsonl'
    finished={r['ordinal'] for r in map(json.loads,log.read_text(encoding='utf8').splitlines())} if log.exists() else set()
    for row,ranking in zip(rows,ranks):
        i=row['ordinal']
        if row['group']!='lite' or i in finished:
            continue
        orig=ranking['fusion'][:5]
        order=sorted(orig,key=lambda k:digest('choice|'+str(i)+'|'+k))
        options=[]
        for num,k in enumerate(order,1):
            card=cards[k]
            opt={'index':num}
            for field,cap in [('symptom',175),('closure',90),('edits',40)]:
                opt[field]=' '.join(card[field].split()[:cap])
            options.append(opt)
        inp=json.dumps({'current_issue':row['query'],'prior_experiences':options},ensure_ascii=False)
        messages=[{'role':'system','content':SYSTEM},{'role':'user','content':inp}]
        payload={'model':MODEL,'messages':messages,'temperature':0,'seed':20261116,'max_tokens':12,'stream':False}
        for attempt in range(1,6):
            start=time.time()
            try:
                resp=requests.post(URL,json=payload,timeout=300)
                resp.raise_for_status()
                out=resp.json()
                raw=out['choices'][0]['message'].get('content') or ''
                break
            except (requests.RequestException,KeyError) as exc:
                append('transport_errors.jsonl',{'ordinal':i,'attempt':attempt,'utc':dt.datetime.now(dt.timezone.utc).isoformat(),'error':str(exc)[:300]})
                if attempt==5:
                    raise
                time.sleep(min(4**attempt,40))
        m=re.fullmatch(r'\s*([1-5])[.)]?\s*',raw)
        picked=order[int(m[1])-1] if m else orig[0]
        append('qwen_calls.jsonl',{'ordinal':i,'order':order,'choice':picked,'fallback':not bool(m),'raw':raw,'usage':out.get('usage',{}),'model':out.get('model'),'finish':out['choices'][0].get('finish_reason'),'endpoint':URL,'payload_sha256':digest(json.dumps(payload,ensure_ascii=False)),'seconds':time.time()-start,'utc':dt.datetime.now(dt.timezone.utc).isoformat()})
        print(i+1,flush=True)
    final=[json.loads(s) for s in log.read_text(encoding='utf8').splitlines()]
    assert len({r['ordinal'] for r in final})==len(final)==99
    files=['PROTOCOL.md','control-addendum.md','redaction-check.md','cards.py','rank.py','cross_encoder.py','cross_encoder_pin.json','cross_encoder_run.json','choose.py','score.py','source.json','cards.json','queries.json','blind_ranks.json','qwen_calls.jsonl']
    (ROOT/'blind_commit.json').write_text(json.dumps({n:hashlib.sha256((ROOT/n).read_bytes()).hexdigest() for n in files},indent=2),encoding='utf8')


if __name__=='__main__':
    main()

