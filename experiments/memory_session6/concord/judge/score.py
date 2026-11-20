"""Re-score a blind verdict file; resample the forty questions, not the 600 correlated rows."""
from collections import Counter, defaultdict
import gzip
import hashlib
import json
import math
from pathlib import Path

import numpy as np
from missing import bounds

ROOT=Path(__file__).resolve().parent

def read(path):
    blob=path.read_bytes()
    return json.loads(gzip.decompress(blob) if path.suffix=='.gz' else blob)

def pair(a,b,arm,ids,draws):
    x=np.array([a[arm,t] - b[t] for t in ids])
    w,l=int(sum(x>0)),int(sum(x<0))
    p=min(1, 2*sum(math.comb(w+l,k) for k in range(min(w,l)+1))/2**(w+l))
    return dict(delta=float(x.mean()),ci=np.quantile(x[draws].mean(axis=1),[.025,.975]).tolist(),wins=w,losses=l,p_exact=p)

def main():
    assignments=read(ROOT/'assignments.json.gz')
    verdicts=read(ROOT/'verdicts.json.gz')
    calls=read(ROOT/'decision_lock.json')
    usage=Counter()
    for fname,expected in calls.items():
        path=ROOT/'calls'/fname
        assert hashlib.sha256(path.read_bytes()).hexdigest()==expected
        rec=read(path)
        usage.update({k:v for k,v in rec['response']['usage'].items() if k in ('prompt_tokens','completion_tokens')})
        raw=rec['response']['choices'][0]['message']['content']
        if raw and raw.strip().startswith('{'):
            try:
                obj=json.loads(raw)
            except ValueError:
                continue
            # A string-valued boolean is an upstream parser hazard. Flag if encountered.
            if 'correct' in obj and type(obj['correct']) is not bool:
                usage['non_boolean']+=1
    published=read(ROOT.parent/'published_projection.json.gz')
    ids=sorted({r['id'] for r in assignments})
    draws=np.random.default_rng(18112026).integers(len(ids),size=(10000,len(ids)))
    ref={(r['actor'],r['arm'],r['id']):r['judge_correct'] for r in published}
    grid=Counter()
    by_qa=defaultdict(list)
    sums=defaultdict(Counter)
    uniq=defaultdict(list)
    local={}
    for r in assignments:
        actor,arm,t=r['actor'],r['arm'],r['id']
        z=verdicts[r['key']]
        target=sums[actor+' | '+arm]
        target['n']+=1
        if z is None:
            target['missing']+=1
        else:
            target['correct']+=int(z)
        if r['source']=='released':
            label=ref[actor,arm,t]
            target['authors_correct']+=label
            if z is not None:
                tag=('TP' if z else 'FN') if label else ('FP' if z else 'TN')
                grid[tag]+=1
                by_qa[t].append(int(z==label))
                uniq[r['key']].append(int(z==label))
        else:
            local[arm,t]=int(bool(z))
    assert len(ref)==600 and len(local)==120
    match=np.array([sum(by_qa[t]) for t in ids])
    n=np.array([len(by_qa[t]) for t in ids])
    counts={k:grid[k] for k in ('TP','FN','TN','FP')}
    stats={'unique_inputs':len(verdicts),'logical_by_source':{'released':600,'local':120},'unique_public_prompts':len(uniq),'unique_local_prompts':len({r['key'] for r in assignments if r['source']=='local'}),'unparseable_unique':sum(z is None for z in verdicts.values()),'physical_calls':len(calls),'usage':dict(usage),'author_agreement':{'matrix':counts,'accuracy':match.sum()/n.sum(),'cluster_ci':np.quantile(match[draws].sum(axis=1)/n[draws].sum(axis=1),[.025,.975]).tolist(),'sensitivity':grid['TP']/(grid['TP']+grid['FN']),'specificity':grid['TN']/(grid['TN']+grid['FP']),'unique_equal_weight_agreement':float(np.mean([np.mean(v) for v in uniq.values()]))},'sums':dict(sums),'local_pairs':{}}
    total_public=int(n.sum())
    stats['author_agreement'].update(graded=total_public,missing=600-total_public,accuracy_bounds_all_600=[float(match.sum()/600),float((match.sum()+600-total_public)/600)])
    for arm,base in [('window','baseline'),('window','raw'),('baseline','raw')]:
        stats['local_pairs'][arm+' minus '+base]=pair(local,{t:local[base,t] for t in ids},arm,ids,draws)
        stats['local_pairs'][arm+' minus '+base]['incomplete_verdict_bounds']=bounds([r for r in assignments if r['source']=='local'],verdicts,arm,base)
    path=ROOT/'results.json'
    if path.exists():
        assert read(path)==stats
    else:
        path.write_text(json.dumps(stats,indent=2),encoding='utf8')
    print(json.dumps({k:stats[k] for k in ('unique_inputs','author_agreement','local_pairs')},indent=2))

if __name__=='__main__':
    main()
