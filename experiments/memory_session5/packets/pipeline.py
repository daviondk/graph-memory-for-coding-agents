"""Three separate commands fit on training repos, predict on unseen prefixes, and reveal outcomes."""
from pathlib import Path
import collections,gzip,hashlib,json,math,os,sys,time
from concurrent.futures import ProcessPoolExecutor
from common import ROOT,rows,advance,newmeta,pages,digest,emit,rel,success
from policy import *
from collections import Counter,defaultdict
def write(n,obj): (ROOT/n).write_text(json.dumps(obj,ensure_ascii=True,indent=1))
def data(split,k):return rows(ROOT/'source'/split/f'{k}.jsonl.gz')
def future(events,t):
    for n,a,feedback in events[t:t+4]:
        if a.get('command')=='str_replace' and rel(a.get('path')) and isinstance(a.get('old_str'),str) and a['old_str']:
            return rel(a['path']),a['old_str'],success('str_replace',a['path'],feedback)
    return None
def snapshots(row):
    states={'drop':{},'rebase':{}};meta=newmeta()
    for t,event in enumerate(row['events'],1):
        advance(states,meta,event,t)
        if not t%4 and t<len(row['events']):yield t,states,meta
def fit():
    import numpy as np
    samples=[];ys=[];ws=[];widths=Counter();counts=Counter()
    for k in range(8):
        for obj in data('train',k):
            counts['train_tasks']+=1
            for t,state,meta in snapshots(obj):
                target=future(obj['events'],t)
                if not target or not target[2]:continue
                counts['accepted']+=1;rs=pages(state['rebase']);ids=order(rs,meta)[:CAP]
                span=unique_span(rs,target[0],target[1]);first=span[0] if span else None
                if span and first in ids:widths[min(len(span),3)]+=1
                # All positive and fixed uniform 1/4 of negatives, with inverse probability weights.
                take=[i for i in ids if i==first or (i+obj['row']+t)%4==0]
                fs=features(rs,meta,t,obj['issue'],take)
                for i,f in fs.items():
                    samples.append(f);ys.append(i==first);ws.append(1 if i==first else 4)
        print('fit shard',k,len(samples),flush=True)
    f=np.array(samples,dtype=np.int16);y=np.array(ys,dtype=float);w=np.array(ws,dtype=float)
    cols=np.cumsum([0]+DIMS[:-1]);keys=f+cols
    coef=np.zeros(sum(DIMS));b0=math.log((w*y).sum()/((1-y)*w).sum());inter=b0;hist=[]
    # Small fixed L2 prior, fixed 120 iterations full-batch, no held-out tuning.
    for it in range(120):
        z=np.clip(inter+coef[keys].sum(axis=1),-25,25);pred=1/(1+np.exp(-z));err=(pred-y)*w/w.sum()
        grad=np.bincount(keys.ravel(),weights=np.repeat(err,len(DIMS)),minlength=len(coef))
        coef-=4*(grad+0.0005*coef);inter-=4*sum(err)
        if it%20==0:hist.append(float((w*(-y*np.log(pred)-(1-y)*np.log(1-pred))).sum()/w.sum()))
    model={'weights':[coef[l:l+d].tolist() for l,d in zip(cols,DIMS)],'intercept':float(inter),'width_fractions':[(widths[k]+1)/(sum(widths.values())+3) for k in (1,2,3)],'training':dict(counts),'sampled_training_rows':len(samples),'width_counts':dict(widths),'fit_loss':hist}
    write('model.json',model)
    files=['PROTOCOL.md','policy.py','pipeline.py','common.py','extract5.py','selection.json','model.json','qwen_tokenizer.json']
    files+=sorted(str(p.relative_to(ROOT)).replace('\\','/') for p in (ROOT/'source').rglob('*.gz'))
    write('fit_lock.json',{n:digest(ROOT/n) for n in files})
def predict(k):
    model=json.loads((ROOT/'model.json').read_bytes());res=ROOT/'sealed'/f'{k}.jsonl.gz';ct=0
    with gzip.open(res,'wt',encoding='utf8',compresslevel=2) as fp:
        for obj in data('test',k):
            for t,state,meta in snapshots(obj):
                preds=policy(state,meta,t,obj['issue'],model)
                fp.write(emit([obj['instance'],t,preds])+'\n');ct+=1
    print('predict',k,ct,flush=True);return ct
def score(k):
    pool=iter(rows(ROOT/'sealed'/f'{k}.jsonl.gz'));counts=Counter();rr=[]
    for obj in data('test',k):
        counts['tasks']+=1
        for t,states,meta in snapshots(obj):
            name,cut,pred=next(pool);assert (name,cut)==(obj['instance'],t)
            counts['cuts']+=1;tar=future(obj['events'],t)
            if not tar:continue
            path,old,ok=tar;counts['intents']+=1
            if ok:counts['accepted']+=1
            row={'id':name,'repo':name.split('.')[0],'format':obj['format'],'cut':t,'accepted':ok,'old_sha':hashlib.sha256(old.encode()).hexdigest(),'metrics':{}}
            candidate={k:pages(mem) for k,mem in states.items()}
            for b,arms in pred.items():
                row['metrics'][b]={}
                for a,(idx,tok) in arms.items():
                    rs=candidate['drop' if a=='reset_tail' else 'rebase']
                    # Sort physical indices for matching independently of the serialized order.
                    hit=bool(unique_span([rs[i] for i in sorted(idx)],path,old))
                    row['metrics'][b][a]=[int(hit),tok]
            rr.append(row)
    assert next(pool,None) is None
    with gzip.open(ROOT/'metrics'/f'{k}.jsonl.gz','wt',encoding='utf8') as fp:
        for r in rr:fp.write(emit(r)+'\n')
    return dict(counts)
def main():
    mode=sys.argv[1];start=time.monotonic()
    if mode=='fit':fit()
    if mode=='predict':
        lock=json.loads((ROOT/'fit_lock.json').read_bytes());assert all(digest(ROOT/n)==x for n,x in lock.items());(ROOT/'sealed').mkdir(exist_ok=True)
        with ProcessPoolExecutor(3) as ex:n=sum(ex.map(predict,range(8)))
        write('prediction_lock.json',{'boundaries':n,'files':{str(p.relative_to(ROOT)).replace('\\','/'):digest(p) for p in [ROOT/'fit_lock.json',*sorted((ROOT/'sealed').glob('*.gz'))]}})
    if mode=='score':
        lock=json.loads((ROOT/'prediction_lock.json').read_bytes());assert all(digest(ROOT/n)==x for n,x in lock['files'].items());(ROOT/'metrics').mkdir(exist_ok=True)
        with ProcessPoolExecutor(3) as ex:counts=list(ex.map(score,range(8)))
        write('coverage.json',dict(sum((Counter(c) for c in counts),Counter())))
    write(mode+'_timing.json',{'wall_seconds':time.monotonic()-start})
if __name__=='__main__':main()
