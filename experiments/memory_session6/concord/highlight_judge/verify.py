"""Independent semantic grading summary from the frozen raw payloads."""
from collections import Counter
import gzip
import hashlib
import json
import math
from pathlib import Path
import sys

import numpy as np

ROOT=Path(__file__).resolve().parent
C=ROOT.parent
sys.path.insert(0,str(C/'judge'))
from missing import bounds

def read(path):
    data=path.read_bytes()
    return json.loads(gzip.decompress(data) if path.suffix=='.gz' else data)

def main():
    logs=read(ROOT/'decision_lock.json')
    for name,h in logs.items():
        p=C/name
        assert hashlib.sha256(p.read_bytes()).hexdigest()==h
    z={};all_rows=[];all_verdicts={}
    missing=Counter()
    for d in (C/'judge',ROOT):
        verdicts=read(d/'verdicts.json.gz')
        for r in read(d/'assignments.json.gz'):
            if r.get('source','local')!='local':continue
            value=verdicts[r['key']]
            if r['key'] in all_verdicts:assert all_verdicts[r['key']]==value
            all_verdicts[r['key']]=value;all_rows.append(r)
            if value is None:missing[r['arm']]+=1
            z.setdefault(r['arm'],{})[r['id']]=int(bool(value))
    ids=sorted(z['baseline'])
    names=sorted(set(z)-{'raw','baseline','window'})
    assert len(names)==2 and all(len(z[k])==40 for k in z)
    idx=np.random.default_rng(18112026).integers(0,40,size=(10000,40))
    contrasts={}
    for arm,base in [(names[0],names[1])]+[(a,b) for a in names for b in ('baseline','raw')]:
        arr=np.array([z[arm][t]-z[base][t] for t in ids])
        w,l=int(sum(arr>0)),int(sum(arr<0))
        contrasts[arm+' minus '+base]={'wins':w,'losses':l,'delta':float(arr.mean()),'ci':np.quantile(arr[idx].mean(axis=1),[.025,.975]).tolist(),'p_exact':min(1,2*sum(math.comb(w+l,k) for k in range(min(w,l)+1))/2**(w+l))}
        contrasts[arm+' minus '+base]['incomplete_verdict_bounds']=bounds(all_rows,all_verdicts,arm,base)
    result={'n_questions':len(ids),'correct':{k:sum(v.values()) for k,v in z.items()},'missing':dict(missing),'previous_requests':sum(k.startswith('judge/') for k in logs),'new_calls':sum(k.startswith('highlight_judge/') for k in logs),'contrasts':contrasts}
    target=ROOT/'results.json'
    if target.exists():
        assert read(target)==result
    else:
        target.write_text(json.dumps(result,indent=2),encoding='utf8')
    print(json.dumps(result,indent=2))
if __name__=='__main__':
    main()
