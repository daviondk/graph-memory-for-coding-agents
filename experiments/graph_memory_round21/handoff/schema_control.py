"""Secondary same-wire control for the frozen Ragability reader; exact-request cache shared with reader.py."""
import gzip
import json
import shutil
import sqlite3
from collections import Counter,defaultdict
from pathlib import Path

import reader
from prepare import CACHE,ROOT,dump,sha
from score import contrast


def cells():
    db=sqlite3.connect((CACHE/'rag-refs.sqlite').resolve().as_uri()+'?mode=ro',uri=True)
    pred=ROOT/'pointer-forecasts.jsonl.gz'
    assert sha(pred.read_bytes())==json.loads((ROOT/'pointer-forecast-lock.json').read_bytes())['forecasts']
    reqs={}; rows=[]
    with gzip.open(pred,'rt') as f:
        for r in map(json.loads,f):
            if (r['source'],r['budget'],r['limit'],r['policy'])!=('rag',512,'one','schema_e5'): continue
            ids=sorted(set(sum(r['ids'],[])))
            sources=[db.execute('SELECT body FROM evidence WHERE id=?',(bytes.fromhex(h),)).fetchone()[0].decode('utf8') for h in ids]
            msg='\n\n'.join(f'Source {i+1}\n'+s for i,s in enumerate(sources)) or '(No sources)'
            req=reader.request(msg)
            key=sha(json.dumps(req,sort_keys=True).encode())
            reqs[key]=req
            rows.append(dict(case=r['case'],arm='schema_e5',ids=ids,request=key))
    db.close()
    return reqs,rows


def run():
    private=CACHE/'schema-extra'
    private.mkdir(exist_ok=True)
    shutil.copyfile(ROOT/'reader-protocol.json',private/'reader-protocol.json')
    reader.ROOT=private
    reader.prep=cells
    reader.arun()
    for f in ('reader-input-lock.json','reader-forecasts.json','reader-forecast-lock.json'):
        shutil.copyfile(private/f,ROOT/('schema-'+f))
    rows=json.loads((ROOT/'schema-reader-input-lock.json').read_text())['rows']
    pred={a['request']:a['answer'] for a in json.loads((ROOT/'schema-reader-forecasts.json').read_text())}
    prev=json.loads((ROOT/'reader-results.json').read_text())
    gold={v['case']:v for v in json.loads((CACHE/'rag-gold.json').read_text()) if v['eligible']}
    tab=Counter(); compare=defaultdict(dict)
    for cell in prev['graded']:
        if cell['arm']=='paired': compare[cell['case']]['paired']=dict(both=int(cell['outcome']=='TP'))
    for cell in rows:
        if cell['case'] not in gold: continue
        row=gold[cell['case']]
        visible=any(set(s)<=set(cell['ids']) for s in (row['pair'],row['alternative']))
        flag=pred[cell['request']]=='C'
        o='TP' if flag and visible else 'FP' if flag else 'FN' if visible else 'TN'
        tab[o]+=1
        compare[cell['case']]['schema_e5']=dict(both=int(o=='TP'))
    old={d['request'] for d in json.loads((ROOT/'reader-forecasts.json').read_text())}
    delta=contrast(compare,'paired','schema_e5',{k:g['article'] for k,g in gold.items()})
    dump(ROOT/'schema-reader-results.json',dict(table=tab,contrast=delta,additional_unique_requests=len(set(pred)-old),cases=len(compare)))
    print(tab,delta)
if __name__=='__main__': run()

