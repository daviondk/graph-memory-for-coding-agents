"""Five mutually exclusive repository folds. Every held-out prediction scores before seeing its labels."""
import os
os.environ['OPENBLAS_NUM_THREADS']='1';os.environ['OMP_NUM_THREADS']='1'
import gzip, itertools, json, math, random
from collections import defaultdict
from features import State,ROOT,np,digest
from serbench.scoring import validate_predictions
from pathlib import Path

def read(split,kind):
    with gzip.open(ROOT/'upstream/data'/split/(kind+'.jsonl.gz'),'rt',encoding='utf-8') as f:
        for line in f:yield json.loads(line)
def project(s):
    return {'state_id':s.sid,'candidate_evidence':[{'evidence_id':v} for v in s.ids],'observed_evidence_ids':sorted(s.visible),'repo':s.repo,'instance_id':s.issue}
def lines(path,rows):
    with (gzip.open(path,'wt',encoding='utf-8',newline='\n') if path.name.endswith('.gz') else path.open('w',encoding='utf-8',newline='\n')) as f:
        for row in rows:f.write(json.dumps(row,separators=(',',':'),ensure_ascii=True)+'\n')
def label_sets(label):
    return [set(g['acceptable_evidence_ids']) for g in label['required_evidence_groups']]
def fit(X,y):
    X=np.array(X,float);y=np.array(y,float);mu=X.mean(axis=0);sd=np.maximum(X.std(axis=0),1e-4)
    Z=np.column_stack([np.ones(len(X)),np.clip((X-mu)/sd,-8,8)]);w=np.zeros(Z.shape[1])
    penalty=np.ones(len(w))*0.02;penalty[0]=0.00001
    for step in range(18):
        p=1/(1+np.exp(-np.clip(Z@w,-30,30)))
        H=Z.T@(Z*(p*(1-p))[:,None])/len(y)+np.diag(penalty)
        delta=np.linalg.solve(H,Z.T@(p-y)/len(y)+penalty*w)
        w-=delta
        if np.max(np.abs(delta))<1e-6:break
    return [mu.tolist(),sd.tolist(),w.tolist()]
def pred(model,X):
    mu,sd,w=map(np.asarray,model);return np.clip((X-mu)/sd,-8,8)@w[1:]+w[0]
def get_training(s,label):
    groups=label_sets(label);members=[{g for g,group in enumerate(groups) if k in group} for k in s.ids]
    y=np.array([int(bool(m)) for m in members]);pairs=[];all_eligible=sorted(s.eligible)
    pos=[i for i in all_eligible if members[i]]
    positive={(i,j) for i,j in itertools.combinations(pos,2) if any(a!=b for a in members[i] for b in members[j])}
    rng=random.Random('complement-pair-negatives|'+s.sid)
    neg=set()
    if len(all_eligible)>1:
        maxn=len(all_eligible)*(len(all_eligible)-1)//2-len(positive)
        while len(neg)<min(96,maxn):
            ij=tuple(sorted(rng.sample(all_eligible,2)))
            if ij not in positive:neg.add(ij)
    idx=sorted(positive|neg)
    return s.x[all_eligible],y[all_eligible],np.array([s.pair(i,j) for i,j in idx]),np.array([int(k in positive) for k in idx])
def train(parts):
    return [fit(np.concatenate([z[i] for z in parts]),np.concatenate([z[i+1] for z in parts])) for i in (0,2)]
def rank(s,models):
    unary=pred(models[0],s.x);eligible=np.array(s.eligible,int)
    simple=sorted(s.eligible,key=lambda i:-unary[i])[:8]
    res={'sdk_bm25':s.starter,'masked_bm25':sorted(s.eligible,key=lambda i:-s.x[i,0])[:8],'independent':simple}
    for kind in ['pair_completion','diversity']:
        selected=[];update=np.zeros(len(s.ids))
        for t in range(min(8,len(eligible))):
            val=unary+(.5*update/max(1,t) if kind=='pair_completion' else -.5*update)
            ix=max((int(i) for i in eligible if i not in selected),key=lambda i:val[i])
            selected.append(ix)
            feats=np.asarray([s.pair(i,ix) for i in eligible])
            if kind=='pair_completion':update[eligible]+=pred(models[1],feats)
            else:update[eligible]=np.maximum(update[eligible],feats[:,4])
        res[kind]=selected
    return {k:[s.ids[int(i)] for i in v] for k,v in res.items()}

def main():
    states=[State(row) for row in read('cal500','items')]
    labels={r['state_id']:r for r in read('cal500','labels')}
    repos=sorted({s.repo for s in states},key=lambda r:digest('serbench-s5-fold|'+r))
    folds={repo:i%5 for i,repo in enumerate(repos)}
    assert len(states)==500 and len(repos)==174
    parts=[get_training(s,labels[s.sid]) for s in states]
    outs=[];models={};meta=[]
    for f in range(5):
        train_parts=[p for s,p in zip(states,parts) if folds[s.repo]!=f]
        model=train(train_parts);models[str(f)]=model
        for s in states:
            if folds[s.repo]!=f:continue
            for k,v in rank(s,model).items():outs.append({'method':k,'state_id':s.sid,'ranked_evidence_ids':v})
            meta.append({'state_id':s.sid,'repo':s.repo,'issue':s.issue,'outer_fold':f})
        print('frozen fold',f,len(outs),flush=True)
    lines(ROOT/'cal_predictions.jsonl.gz',outs);lines(ROOT/'cal_candidates.jsonl.gz',map(project,states))
    lines(ROOT/'cal_folds.jsonl.gz',meta)
    final=train(parts);models['all']=final
    (ROOT/'model.json').write_text(json.dumps(models))
    preds=[];testproj=[]
    for row in read('test500','items'):
        s=State(row); assert s.repo not in folds
        preds.append({'method':'pair_completion','state_id':s.sid,'ranked_evidence_ids':rank(s,final)['pair_completion']})
        testproj.append(project(s))
    assert len(preds)==500
    validate_predictions(preds,testproj);lines(ROOT/'test500_predictions.jsonl',preds)
    lines(ROOT/'test_candidates.jsonl.gz',testproj)
    import hashlib
    files=['PROTOCOL.md','features.py','train.py','cal_predictions.jsonl.gz','cal_candidates.jsonl.gz','cal_folds.jsonl.gz','model.json','test500_predictions.jsonl','test_candidates.jsonl.gz']
    (ROOT/'decision_lock.json').write_text(json.dumps({name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in files},indent=2))
if __name__=='__main__':main()
