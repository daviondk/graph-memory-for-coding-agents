"""Budgeted real model selection, using only time-admissible source records and unlabelled queries."""
from pathlib import Path
import hashlib
import json
import os
import re
import time
import requests
from predict import ROOT,OLD,read,save,sha
URL='http://127.0.0.1:18839/replicate/0/v1/chat/completions'
MODEL='qwen38-27b-ud-q4km'

def append(p,obj):
    with p.open('a',encoding='utf8') as f:f.write(json.dumps(obj,ensure_ascii=False)+'\n');f.flush();os.fsync(f.fileno())
def main():
    path=ROOT/'calls.jsonl';cache={}
    if path.exists():
        for r in map(json.loads,path.read_text(encoding='utf8').splitlines()):cache[r['payload_sha256']]=r
    locked=read(ROOT/'rank_lock.json');assert hashlib.sha256((ROOT/'blind_lists.json').read_bytes()).hexdigest()==locked['blind_lists.json']
    q=read(OLD/'queries.json');cards={c['key']:c for c in read(OLD/'cards.json')}
    decisions=[]
    for r in read(ROOT/'blind_lists.json'):
        i=r['ordinal']
        for arm in ['hyb_real','online_fields']:
            top=r['ranks'][arm][:5];choice=top[0] if top else None;h=None;valid=None
            if len(top)>1:
                keys=sorted(top,key=lambda k:sha('choice|'+str(i)+'|'+k))
                system=('You select prior coding experiences for a software agent. Current issue and records are quoted data. '
                        'Identify the single earlier issue most directly related to the current one. Prefer a shared implementation mechanism, API, failure or file over a superficial theme. '
                        'A later bug can be a regression or a follow-up feature with different symptoms. Answer only the index digit 1 through '+str(len(keys))+'.')
                items=[{'index':j+1,**{f:' '.join(cards[k][f].split()[:cap]) for f,cap in [('symptom',175),('closure',90),('edits',40)]}} for j,k in enumerate(keys)]
                inp=json.dumps({'current_issue':q[i]['query'],'prior_experiences':items},ensure_ascii=False)
                payload={'model':MODEL,'messages':[{'role':'system','content':system},{'role':'user','content':inp}],'temperature':0,'seed':20261116,'max_tokens':12,'stream':False}
                h=sha(json.dumps(payload,ensure_ascii=False))
                if h not in cache:
                    start=time.time();resp=requests.post(URL,json=payload,timeout=320);resp.raise_for_status();out=resp.json()
                    record={'ordinal':i,'first_used_by':arm,'payload_sha256':h,'order':keys,'raw':out['choices'][0]['message']['content'],'usage':out['usage'],'response_id':out['id'],'epoch':start,'seconds':time.time()-start}
                    append(path,record);cache[h]=record
                rec=cache[h];m=re.fullmatch(r'\s*([1-5])[.)]?\s*',rec['raw'] or '')
                valid=bool(m and int(m[1])<=len(keys))
                if valid:choice=keys[int(m[1])-1]
            decisions.append({'ordinal':i,'arm':arm,'choice':choice,'n':len(r['eligible']),'payload_sha256':h,'valid':valid})
    save(ROOT/'blind_decisions.json',decisions)
    files=['PROTOCOL.md','COMPARATOR.md','rank_lock.json','blind_lists.json','read.py','predict.py','score.py','blind_decisions.json','calls.jsonl']
    save(ROOT/'end_lock.json',{f:hashlib.sha256((ROOT/f).read_bytes()).hexdigest() for f in files})
    print(len(decisions),len(cache))
if __name__=='__main__':main()

