"""Generate causal-prefix decisions, seal independently of scoring, and score complete public task families."""
import argparse
import csv
from collections import Counter,defaultdict
import gzip
import hashlib
import json
from pathlib import Path
import random
import statistics
import time
from replay import Memory,parse_read,effect
from sources import ROOT,sha,js
BUDGETS={'tiny':(4,16384),'main':(16,65536),'large':(64,262144)}
POLICIES={'literal':('strict','literal'),'exact':('strict','exact'),'contained':('strict','contained'),'range':('strict','range'),'coarse':('coarse','range'),'optimistic':('optimistic','range')}
def gzread(p):
    with gzip.open(p,'rt',encoding='utf8') as f:return json.load(f)
def read(n):return json.loads((ROOT/n).read_text(encoding='utf8'))
def newline(obj):return (json.dumps(obj,separators=(',',':'),ensure_ascii=False)+'\n').encode()
def dataset():
    listed=read('sources.json')
    assert len(listed)==1441 and not any('error' in v for v in listed)
    for v in listed:
        data=gzread(ROOT/'events'/v['model']/(v['id']+'.json.gz'))
        assert data['source']==v and data['verified_cwd']=='/testbed'
        yield data
def predict():
    started=time.perf_counter()
    table=[];effects_total=Counter();per_model_counts=Counter()
    curr=ROOT/'predictions.jsonl.gz'
    with curr.open('wb') as raw,gzip.GzipFile(fileobj=raw,mode='wb',mtime=0,compresslevel=5) as dest:
        for data in dataset():
            v=data['source'];repo=v['id'].rsplit('-',1)[0]
            banks={(b,g):Memory(*cap) for b,cap in BUDGETS.items() for g in ['strict','coarse','optimistic']}
            counts=Counter()
            for batch,group in enumerate(data['groups']):
                cmds=[e['command'] for e in group];ops=[parse_read(c) for c in cmds];effects=[effect(c) for c in cmds]
                counts['calls']+=len(group);counts['batches']+=1
                effects_total.update(e[0] for e in effects)
                mixed=len(group)>1 and any(y[0]!='read' for y in effects)
                if mixed:counts['mixed_write_batches']+=1
                for j,(cmd,op) in enumerate(zip(cmds,ops)):
                    if not op:continue
                    counts['supported_requests']+=1
                    if mixed:counts['supported_in_mixed']+=1
                    pred={}
                    # Commands in a tool-call batch are known at dispatch. No response object here.
                    if not mixed:
                        for b,cap in BUDGETS.items():
                            for method,(gate,mode) in POLICIES.items():
                                ans=banks[(b,gate)].lookup(op,cmd,mode)
                                if ans is not None:pred[b+'/'+method]=sha(ans.encode())
                    dest.write(newline({'id':v['id'],'model':v['model'],'batch':batch,'j':j,'pred':pred}))
                # All predictions for this entire batch have now been recorded. Reveal its outcomes.
                if mixed or any(x[0]=='unknown' for x in effects) or any(e['result'] is None for e in group):
                    for (b,g),bank in banks.items():
                        if g!='optimistic':bank.flush()
                else:
                    edits={path for kind,paths in effects for path in paths}
                    if edits:
                        for (b,g),bank in banks.items():
                            if g!='optimistic':bank.flush(edits if g=='strict' else None)
                if mixed:continue
                for op,cmd,e in zip(ops,cmds,group):
                    res=e['result']
                    if res is None:counts['missing_results']+=1
                    if not op:continue
                    if res is not None and res['rc']==0 and res['visible']:
                        assert 'text' in res
                        counts['full_visible_success']+=1
                        for bank in banks.values():bank.write(op,cmd,res['text'])
                    elif res and res['rc']!=0:
                        for (b,g),bank in banks.items():
                            if g!='optimistic':bank.flush({op.path})
            counts.update({'orphan_tools':data['orphan_tools']})
            table.append({'id':v['id'],'model':v['model'],'repo':repo,**dict(counts),'peak_main_payload':banks['main','strict'].peak})
            per_model_counts[v['model']]+=1
    js('exposures.json',table)
    names=['PROTOCOL.md','DESIGN_ADDENDUM.md','sources.py','replay.py','evaluate.py','sources.json','list.json','predictions.jsonl.gz','exposures.json']
    js('prediction_lock.json',{'files':{n:sha((ROOT/n).read_bytes()) for n in names},'timing_seconds':time.perf_counter()-started,
        'source_sha256':sha(''.join(x['sha256'] for x in read('sources.json')).encode()),'models':per_model_counts,'effects':effects_total})
    print('sealed',per_model_counts,flush=True)
def cluster_summary(by,model_key):
    allgroups=defaultdict(list)
    for x in by:
        if model_key=='pooled' or x['model']==model_key:allgroups[x['id']].append(x)
    def vals(rows):
        a=sum(x['range_correct'] for x in rows);b=sum(x['exact_correct'] for x in rows);n=sum(x['requests'] for x in rows)
        return a-b,n
    groups=[vals(rows) for rows in allgroups.values()]
    rr=random.Random(17112026);boot=[]
    for _ in range(4000):
        sam=rr.choices(groups,k=len(groups));den=sum(t[1] for t in sam)
        if den:boot.append(100*sum(t[0] for t in sam)/den)
    boot.sort()
    return {'unique_issues':len(groups),'issues_improved':sum(a>0 for a,b in groups),'issues_worse':sum(a<0 for a,b in groups),
            'additional_correct':sum(a for a,b in groups),'delta_pp':100*sum(a for a,b in groups)/max(1,sum(b for a,b in groups)),
            'issue_cluster_CI95_pp':[boot[int(len(boot)*.025)],boot[int(len(boot)*.975)-1]] if boot else None}
def score(check=False):
    for n,h in read('prediction_lock.json')['files'].items():assert sha((ROOT/n).read_bytes())==h,n
    sums=defaultdict(Counter);by=[];stale=[];errors=Counter()
    with gzip.open(ROOT/'predictions.jsonl.gz','rt',encoding='utf8') as pred:
        for data in dataset():
            v=data['source'];task=Counter()
            for batch,gr in enumerate(data['groups']):
                for j,e in enumerate(gr):
                    if not parse_read(e['command']):continue
                    x=json.loads(next(pred))
                    assert (v['id'],v['model'],batch,j)==(x['id'],x['model'],x['batch'],x['j'])
                    r=e['result']
                    if r is None:
                        errors[(v['model'],'unscored')]+=1
                        continue
                    task['requests']+=1
                    for b in BUDGETS:
                        for method in POLICIES:
                            name=b+'/'+method;h=x['pred'].get(name)
                            hit=h is not None;correct=hit and r['rc']==0 and h==r['sha'];wrong=hit and not correct
                            if b=='main':
                                task[method+'_correct']+=int(correct);task[method+'_stale']+=int(wrong)
                            for model in [v['model'],'pooled']:
                                s=sums[(model,name)]
                                s['n']+=1;s['attempted']+=int(hit);s['correct']+=int(correct);s['stale']+=int(wrong)
                                s['correct_bytes']+=r['bytes'] if correct else 0
                            if wrong and b=='main':stale.append({'id':v['id'],'model':v['model'],'batch':batch,'event':j,'method':method,'command':e['command'],'expected':r['sha'],'cached':h,'rc':r['rc']})
            by.append({'id':v['id'],'model':v['model'],'requests':task['requests'],**{k+'_'+s:task[k+'_'+s] for k in POLICIES for s in ['correct','stale']}})
        assert next(pred,None) is None
    res={'metrics':{m:{k:dict(sums[m,k]) for k in (b+'/'+p for b in BUDGETS for p in POLICIES)} for m in ['pooled','claude','codex','gemini']},
         'paired':{m:cluster_summary(by,m) for m in ['pooled','claude','codex','gemini']},'unscored':{str(k):v for k,v in errors.items()}}
    if check:
        assert res==read('results.json')
        assert stale==read('stale.json')
    else:
        js('results.json',res);js('stale.json',stale)
        with (ROOT/'per_task.csv').open('w',encoding='utf8',newline='') as f:
            w=csv.DictWriter(f,fieldnames=list(by[0]));w.writeheader();w.writerows(by)
    return res
if __name__=='__main__':
    arg=argparse.ArgumentParser();arg.add_argument('action',choices=['predict','score','verify']);a=arg.parse_args().action
    if a=='predict':predict()
    else:
        out=score(a=='verify')
        print(out['paired'])
        print({k:v for k,v in out['metrics']['pooled'].items() if k.startswith('main/')})

