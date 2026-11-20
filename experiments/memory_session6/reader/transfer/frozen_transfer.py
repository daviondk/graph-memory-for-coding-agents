"""Evaluate two fixed routers on an independent TREC year with paired writer controls."""
from collections import defaultdict
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import sys

import numpy as np

ROOT=Path(__file__).resolve().parent
PARENT=ROOT.parent
SOURCE=ROOT/'sources'
sys.path.insert(0,str(PARENT))
from prepare import features
from switch import apply, estimate


def checked_write(path, text):
    if path.exists():
        assert path.read_text(encoding='utf8')==text,path
    else:
        path.write_bytes(text.encode())


def official(run):
    exe=PARENT/'sources/trec_eval-d95ca64e14a47d763ae349fb65e6d8cde4141dbd/trec_eval'
    if os.name=='nt':
        def local(p):
            return '/mnt/'+p.drive[0].lower()+'/'+p.as_posix()[3:]
        cmd=['wsl','-d',os.getenv('TREC_WSL','CodexX20MSR'),'--',local(exe)]
    else:
        local=str
        cmd=[str(exe)]
    raw=subprocess.check_output(cmd+['-c','-q','-l','2','-M','500','-m','ndcg_cut.3,5',
                                     local(SOURCE/'qrels.txt'),local(run)],text=True)
    return {(sid,int(m.rsplit('_',1)[1])):float(v) for m,sid,v in (s.split() for s in raw.splitlines())}


def load_outcomes():
    topics=json.loads((SOURCE/'topics.json').read_bytes())
    roster={f"{s['number']}_{r['number']}":(str(s['number']),r,i) for s in topics for i,r in enumerate(s['turn'])}
    qrels=defaultdict(dict)
    for line in (SOURCE/'qrels.txt').read_text().splitlines():
        q,_,doc,level=line.split()
        assert doc not in qrels[q]
        qrels[q][doc]=int(level)
    names=sorted(qrels,key=lambda q:tuple(map(int,q.split('_'))))
    rows={}
    for name in names:
        group,r,past=roster[name]
        rows[name]={'id':name,'group':group,'features':features(r['raw_utterance'],past),
                    'query_unchanged':r['raw_utterance'].strip()==r.get('automatic_rewritten_utterance','').strip()}
    for arm,source in [('on','automatic'),('off','raw')]:
        run=SOURCE/f'{source}.run'
        refs=official(run)
        runs=defaultdict(list)
        for line in run.read_text().splitlines():
            q,_,d,_,score,_=line.split()
            runs[q].append((float(score),d))
        for q in names:
            pairs=runs[q]
            assert len(pairs)==len({d for _,d in pairs})
            rank=[d for _,d in sorted(pairs,reverse=True)[:5]]
            grades=[]
            for k in [3,5]:
                discount=lambda a:sum(max(0,v)/math.log2(i+2) for i,v in enumerate(a[:k]))
                ideal=discount(sorted(qrels[q].values(),reverse=True))
                value=discount([qrels[q].get(d,0) for d in rank])/ideal if ideal else 0.
                assert abs(value-refs[q,k])<=0.000051
                grades.append(value)
            rows[q][arm]={'rank':rank,'grades':grades}
        for i,k in enumerate([3,5]):
            assert abs(np.mean([rows[q][arm]['grades'][i] for q in names])-refs['all',k])<.000051
    return list(rows.values())


def evaluate():
    inputs=PARENT/'models.json'
    assert hashlib.sha256(inputs.read_bytes()).hexdigest()==json.loads((PARENT/'replay_receipt.json').read_bytes())['sha256']['models.json']
    models=json.loads(inputs.read_bytes())
    rows=([json.loads(l) for l in (ROOT/"rows.jsonl").read_text().splitlines()]
          if "--offline" in sys.argv else load_outcomes())
    data=np.array([[r[a]['grades'] for a in ['off','on']] for r in rows])
    x=np.array([r['features'] for r in rows])
    groups=np.array([r['group'] for r in rows])
    skip_first=x[:,2]==0
    policies={'ser_full':apply(models['ser_full'],x),'cast_full':apply(models['cast_full'],x),
              'skip_first':skip_first}
    results={}
    for name,action in policies.items():
        m=estimate(data,action,groups)
        for j,l in enumerate(['primary','secondary']):
            y=np.where(action,data[:,1,j],data[:,0,j])
            ctrl=np.where(skip_first,data[:,1,j],data[:,0,j])
            delta=y-ctrl
            labels,inv=np.unique(groups,return_inverse=True)
            draws=np.random.default_rng(20261118).integers(0,len(labels),(10000,len(labels)))
            boot=np.bincount(inv,weights=delta)[draws].sum(1)/np.bincount(inv)[draws].sum(1)
            m[l].update(gain_vs_skip_first=float(delta.mean()),ci_vs_skip_first=np.quantile(boot,[.025,.975]).tolist())
        results[name]=m
        for i,r in enumerate(rows):
            r.setdefault('actions',{})[name]='on' if action[i] else 'off'
    results['audit']={'all_topics':len(set(groups)), 'first_turns':int((~skip_first).sum()),
          'first_positively_graded_differences':int(np.sum((~skip_first)&(abs(data[:,0,0]-data[:,1,0])>1e-12))),
          'first_differing_top_fives':sum(r['features'][2] and r['on']['rank']!=r['off']['rank'] for r in rows),
          'empty_runs':{a:sum(not r[a]['rank'] for r in rows) for a in ['off','on']},
          'same_raw_and_rewritten':sum(r['query_unchanged'] for r in rows)}
    checked_write(ROOT/'rows.jsonl',''.join(json.dumps(r,separators=(',',':'))+'\n' for r in rows))
    checked_write(ROOT/'results.json',json.dumps(results,indent=2))
    for n in policies:
        print(n, results[n]['reads'],results[n]['primary'],results[n]['secondary']['gate'])
    print(results['audit'])


if __name__=='__main__':
    evaluate()

