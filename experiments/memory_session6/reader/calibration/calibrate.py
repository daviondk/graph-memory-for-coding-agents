"""Fit budgeted cold-start gates without using test relations or test subjects."""
import hashlib
import json
import gzip
from pathlib import Path

import numpy as np

ROOT=Path(__file__).resolve().parent
READERS=['qwen2.5:14b','glm-4.6']
NSEED=32
FAMILIES=['fixed_disagree','fixed_agree','fixed_reader_sign','calibrated_sign','reader_ridge','shared_ridge']


def hash64(s):
    return int.from_bytes(hashlib.sha256(s.encode()).digest()[:8],'big')


def subject_folds(subjects):
    names,counts=np.unique(subjects,return_counts=True)
    bins=[0]*5
    assignment={}
    for name,n in sorted(zip(names,counts),key=lambda p:(-p[1],hash64('subject|'+p[0]))):
        f=min(range(5),key=lambda i:(bins[i],i))
        bins[f]+=n
        assignment[name]=str(f)
    return np.array([assignment[s] for s in subjects])


def quota(folds):
    groups,counts=np.unique(folds,return_counts=True)
    base={g:c//2 for g,c in zip(groups,counts)}
    extra=len(folds)//2-sum(base.values())
    odd=sorted((g for g,c in zip(groups,counts) if c%2),key=lambda g:hash64('quota|'+g))
    for g in odd[:extra]:base[g]+=1
    return base


def top(scores,tie,cap):
    order=np.lexsort((tie,-scores))
    a=np.zeros(len(order),dtype=bool)
    a[order[:cap]]=True
    return a


def ridge(x,d,xt):
    mu=x.mean(axis=0)
    std=x.std(axis=0)
    std[std<1e-10]=1.
    z=(x-mu)/std
    coef=np.linalg.solve(z.T@z+len(z)*np.eye(len(mu)),z.T@(d-d.mean(axis=0)))
    return d.mean(axis=0)+(xt-mu)/std@coef


def fit_actions(x,y,folds,subjects,ids,scheme):
    n=len(x)
    caps=quota(folds)
    tie=np.array([hash64('tie|'+i) for i in ids],dtype=np.uint64)
    dim=(NSEED,2,n)
    actions={m:np.zeros(dim,dtype=bool) for m in FAMILIES[:3]}
    for level in ['8','32','all']:
        actions.update({level+'/'+m:np.zeros(dim,dtype=bool) for m in FAMILIES[3:]})
    randp=np.zeros(n)
    delta=y[:,:,1]-y[:,:,0]
    for fold,cap in caps.items():
        te=np.flatnonzero(folds==fold)
        held=set(subjects[te])
        tr=[i for i in range(n) if folds[i]!=fold and subjects[i] not in held]
        sources={}
        for i in sorted(tr,key=lambda i:hash64('fact|'+ids[i])):
            sources.setdefault(subjects[i],i)
        assert not set(sources).intersection(held)
        if scheme=='relation': assert set(folds[i] for i in tr).isdisjoint({fold})
        randp[te]=cap/len(te)
        bit=x[te,0]
        for reader in range(2):
            pref=1. if reader==1 else -1.
            for k,sgn in [('fixed_disagree',1.),('fixed_agree',-1.),('fixed_reader_sign',pref)]:
                actions[k][:,reader,te]=top(sgn*bit,tie[te],cap)[None,:]
        for seed in range(NSEED):
            ranked=sorted(sources,key=lambda s:hash64(f'cal|{scheme}|{fold}|{seed}|{s}'))
            for level in ['8','32','all']:
                if level=='all' and seed>0:
                    for k in FAMILIES[3:]:
                        actions[level+'/'+k][seed,:,te]=actions[level+'/'+k][0,:,te]
                    continue
                idx=np.array([sources[s] for s in (ranked if level=='all' else ranked[:int(level)])])
                d=delta[idx,:]
                pred=ridge(x[idx],d,x[te])
                for reader in range(2):
                    arm=d[:,reader]
                    if np.unique(x[idx,0]).size>1:
                        diff=arm[x[idx,0]==1].mean()-arm[x[idx,0]==0].mean()
                    else:diff=0.
                    prior=1. if reader==1 else -1.
                    sg=np.sign(diff) if abs(diff)>1e-12 else prior
                    for k,scores in [('reader_ridge',pred[:,reader]),('shared_ridge',pred.mean(1)),('calibrated_sign',sg*bit)]:
                        actions[level+'/'+k][seed,reader,te]=top(scores,tie[te],cap)
    assert all(np.all(a.sum(2)==n//2) for a in actions.values())
    return actions,randp


def summarize(y,actions,randp,clusters,seed=20261118):
    off=y[:,:,0].T
    diff=(y[:,:,1]-y[:,:,0]).T
    expected=(off+diff*randp[None,:]).mean(1)
    out={}
    groups,inv=np.unique(clusters,return_inverse=True)
    draws=np.random.default_rng(seed).integers(0,len(groups),(10000,len(groups)))
    size=np.bincount(inv)[draws].sum(1)
    for k,act in actions.items():
        preds=off[None,:,:]+act*diff[None,:,:]
        scores=preds.mean(axis=2)
        out[k]={}
        for j,name in enumerate(READERS):
            entry={'mean_accuracy':float(scores[:,j].mean()),'mean_random':float(expected[j]),
                   'vs_random_pp':float(100*(scores[:,j].mean()-expected[j])),
                   'calibration_p10_p90':np.quantile(scores[:,j],[.1,.9]).tolist()}
            for cmp,other in [('signed',actions['fixed_reader_sign'])]+([('shared',actions[k.split('/')[0]+'/shared_ridge'])] if '/' in k else []):
                dd=(act[:,j,:].astype(float)-other[:,j,:])*diff[j]
                dm=dd.mean(axis=0)
                ci=np.quantile(np.bincount(inv,weights=dm)[draws].sum(1)/size,[.025,.975])
                entry[cmp+'_difference_pp']=100*float(dm.mean())
                entry[cmp+'_ci_pp']=(100*ci).tolist()
                entry[cmp+'_seed_p10_p90_pp']=(100*np.quantile(dd.mean(1),[.1,.9])).tolist()
            out[k][name]=entry
    return out


if __name__=='__main__':
    rows=[json.loads(l) for l in (ROOT/'inputs.jsonl').read_text().splitlines()]
    x=np.array([r['features'] for r in rows])
    y=np.array([[r['grades'][name] for name in READERS] for r in rows])
    ids=[r['id'] for r in rows]
    subjects=np.array([r['subject'] for r in rows])
    relation=np.array([r['relation'] for r in rows])
    summary={}
    per=[]
    for mode,folds in [('relation',relation),('subject',subject_folds(subjects))]:
        acts,p=fit_actions(x,y,folds,subjects,ids,mode)
        summary[mode]=summarize(y,acts,p,relation if mode=='relation' else subjects)
        for i,r in enumerate(rows):
            for j,name in enumerate(READERS):
                per.append({'query':r['id'],'reader':name,'split':mode,'fold':str(folds[i]),'subject':r['subject'],
                      'plain':int(y[i,j,0]),'dated':int(y[i,j,1]),'p_random':p[i],
                      'read_mask_hex':{k:np.packbits(a[:,j,i],bitorder='little').tobytes().hex() for k,a in acts.items()}})
    out={'seeds':NSEED,'n':len(rows),'budget':len(rows)//2,'bytes_per_reader':35*(len(rows)//2),
         'unique_subjects':len(set(subjects)),'relation_counts':dict(zip(*[a.tolist() for a in np.unique(relation,return_counts=True)])),
         'policies':summary}
    frozen={'results.json':json.dumps(out,indent=2).encode(),'actions.jsonl.gz':gzip.compress(
        ''.join(json.dumps(r,separators=(',',':'))+'\n' for r in per).encode(),mtime=0)}
    for name,content in frozen.items():
        dst=ROOT/name
        if dst.exists():assert dst.read_bytes()==content,name
        else:dst.write_bytes(content)
    for mode in ['relation','subject']:
        for k in ['fixed_reader_sign','8/reader_ridge','32/reader_ridge','32/shared_ridge','all/reader_ridge']:
            print(mode,k,*[(round(z['mean_accuracy'],4),round(z['signed_difference_pp'],3),round(z['vs_random_pp'],3)) for z in summary[mode][k].values()])
