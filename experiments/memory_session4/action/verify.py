"""Portable replay verification from fixed pre-attempt projections and observed CI receipts."""
from pathlib import Path
import json,hashlib,heapq,math
from collections import defaultdict,deque
from run import readgz
from model import stable
P=Path(__file__).resolve().parent
def h(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def check_seals():
    for n in ['input_lock.json','tail_input_lock.json']:
        d=json.loads((P/n).read_bytes());d=d.get('sha256',d)
        for f,digest in d.items():assert h(P/f)==digest,(n,f)
    if (P/'checksums.json').exists():
        for f,d in json.loads((P/'checksums.json').read_bytes()).items():assert h(P/f)==d,f
def chronological(kind,tail=False):
    rows=readgz(P/(kind+'_inputs.jsonl.gz'));r={a['id']:a for a in rows}
    ys={a['id']:a for a in readgz(P/(kind+'_labels.jsonl.gz'))}
    preds={a['id']:a for a in readgz(P/(kind+'_predictions.jsonl.gz'))}
    assert set(r)==set(ys);assert set(preds)<=set(r)
    training=set(r)-set(preds);history=defaultdict(list);events=[]
    def keys(x):
        detail=(x['status'],x['event'],x['language'],x['matrix'])
        z={'all':('all',),'status':('s',x['status']),'project':('p',x['repo']),'ps':('ps',x['repo'],x['status']),
           'context':('ctx',detail),'pc':('pc',x['repo'],detail)}
        sig=tuple(x.get('reasons',[]));z.update(type=('t',x['status'],sig),pt=('pt',x['repo'],x['status'],sig));return z
    def sm(key,prior,c=8,limit=None):
        values=history[key][-limit:] if limit else history[key]
        return (sum(values)+c*prior)/(len(values)+c)
    for x in sorted(rows,key=lambda x:(x['decision_at'],x['id'])):
        while events and events[0][0]<x['decision_at']:
            _,prior=heapq.heappop(events);o=r[prior]
            for k in keys(o).values():history[k].append(ys[prior]['passed'])
        i=x['id'];k=keys(x)
        if i in preds:
            g=sm(k['all'],.5,2);s=sm(k['status'],g);ctx=sm(k['context'],s);ps=sm(k['ps'],s);pred=preds[i]['p']
            assert math.isclose(pred['repo_status'],ps,abs_tol=1e-13)
            assert math.isclose(pred['recent8'],sm(k['pc'],ctx,limit=8),abs_tol=1e-13)
            if 'typed' in pred:
                gt=sm(k['type'],s);pt=sm(k['pt'],gt,limit=8) if x['reasons'] else ps
                assert math.isclose(pred['typed'],pt,abs_tol=1e-13)
                assert pred['uncertain']==int(.35<=ps<=.65)
        heapq.heappush(events,(ys[i]['available_after'],i))
    # Independent recomputation of squared error and actual quota recovery. Baseline and candidate signatures.
    result=json.loads((P/('tail_results.json' if tail else 'results.json')).read_bytes())
    if not tail:result=result[kind]
    allocations=preds if tail else {x['id']:x for x in readgz(P/(kind+'_allocation.jsonl.gz'))}
    for arm,v in result['rates'].items():
        if 'brier' in v and arm in next(iter(preds.values()))['p']:
            computed=sum((x['p'][arm]-ys[x['id']]['passed'])**2 for x in preds.values())/len(preds)
            assert math.isclose(computed,v['brier'],abs_tol=1e-13),(kind,arm)
        if 'selected' in v:
            ids=[i for i,x in allocations.items() if arm in x.get('accepted',x.get('selected',[]))]
            assert len(ids)==v['selected'] and sum(ys[i]['passed'] for i in ids)==v['recovered'],(kind,arm)
    if not tail:
        ordered=sorted(preds,key=lambda i:(r[i]['decision_at'],i));expected={x for x in result['rates'] if 'selected' in result['rates'][x]}
        for b in range(0,len(ordered),100):
            ids=ordered[b:b+100];quota=max(1,int(len(ids)*.2+.5))
            assert all(sum(a in allocations[i]['accepted'] for i in ids)==quota for a in expected)
    return len(preds)
if __name__=='__main__':
    check_seals();n=[chronological('builds'),chronological('jobs'),chronological('tail',True)]
    print('PASS complete chronological feedback verification; held-out examples',n)
