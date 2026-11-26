"""Generate paired predictions first, then score after those predictions are sealed."""
from train_model import D,BASE,CONF,dump,read,sha
from pathlib import Path
import sys,importlib.util
import numpy as np
def predict():
    l=read(D/'learning-seal.json');assert sha(D/'probabilities.json.gz')==l['prob'] and sha(BASE/'manifest.json')==l['prior']
    co=read(CONF/'forecast-seal.json');assert sha(CONF/'predictions.json.gz')==co['pred']
    outside=read(BASE/'predictions.json.gz');dev=read(CONF/'predictions.json.gz');probs=read(D/'probabilities.json.gz');pan=read(BASE/'panels.json');out={}
    for q in pan['test']+pan['dev']:
        prev=outside[q];old=dev[q] if q in dev else prev
        order=old['rank']['qwen'];seen=prev['seen'];n=len(order);rel=np.zeros(n);rel[order]=1/np.sqrt(1+np.arange(n));a={};tail=[i for i in order if seen[i]]
        for name in ['qwen','full','document','match']:
            if name=='qwen':rr=order
            else:
                p=np.asarray(probs[q][name]);s=rel+.65*p/p.max();rr=sorted(order,key=lambda i:-s[i])
            a[name]=rr;a[name+'_mask']=[i for i in rr if not seen[i]]+tail
        for name,k in [('qwen','qwen'),('full','union' if q in dev else 'qwen_union')]:
            for suffix in ('','_mask'):assert a[name+suffix]==old['rank'][k+suffix]
        out[q]=dict(repo=prev['repo'],ids=prev['ids'],seen=seen,rank=a)
    dump('predictions.json.gz',out);dump('forecast-seal.json',dict(source=sha(D/'learning-seal.json'),confirm=sha(CONF/'forecast-seal.json'),rows=sha(D/'predictions.json.gz'),code=sha(Path(__file__))))
    print('Sealed',len(out),'complete forecast pools.')
def aggregate(qs,rows,pred):
    methods=sorted(next(iter(rows.values()))['arms']);arr=np.asarray([[rows[q]['arms'][k]['metric'] for k in methods] for q in qs]);names,idx=np.unique([rows[q]['repo'] for q in qs],return_inverse=True);freq=np.bincount(idx);n=len(names)
    g=np.zeros((n,len(methods),9));np.add.at(g,idx,arr);m=g/freq[:,None,None];gen=np.random.default_rng(471018);w=gen.multinomial(n,np.repeat(1/n,n),size=20000);den=w@freq
    a={k:dict(totals=arr[:,i,:].sum(0).tolist(),macro=m[:,i].mean(0).tolist(),tokens=np.mean([rows[q]['arms'][k]['tokens'] for q in qs],axis=0).tolist(),items=np.mean([rows[q]['arms'][k]['items'] for q in qs],axis=0).tolist()) for i,k in enumerate(methods)}
    c={}
    for suffix in ('','_mask'):
        for x,y in [('full','document'),('match','document'),('full','match'),('document','qwen'),('match','qwen'),('full','qwen')]:
            l,r=x+suffix,y+suffix;i,j=methods.index(l),methods.index(r);d=arr[:,i]-arr[:,j];dr=g[:,i]-g[:,j];dm=m[:,i]-m[:,j]
            c[l+' minus '+r]=dict(micro=d.mean(0).tolist(),macro=dm.mean(0).tolist(),ci=np.quantile((w@dr)/den[:,None],[.025,.975],axis=0).tolist(),
                 macroci=np.quantile((w@dm)/n,[.025,.975],axis=0).tolist(),wins=(d>1e-10).sum(0).tolist(),loss=(d< -1e-10).sum(0).tolist(),
                 set8=sum(set(pred[q]['rank'][l][:8])!=set(pred[q]['rank'][r][:8]) for q in qs))
    return dict(states=len(qs),repos=n,arms=a,contrasts=c)
def grade():
    s=read(D/'forecast-seal.json');assert sha(D/'predictions.json.gz')==s['rows'];pred=read(D/'predictions.json.gz')
    # Wait for the independent confirmation to be signed off before analyzing ablation outcomes.
    c=read(CONF/'manifest.json')['files'];assert sha(CONF/'results.json')==c['results.json']
    spec=importlib.util.spec_from_file_location('r47_confirmation_scoring',CONF/'evaluate.py');ev=importlib.util.module_from_spec(spec);spec.loader.exec_module(ev)
    ck=read(BASE/'manifest.json')['files'];assert sha(BASE/'ordinal-judgments.json.gz')==ck['ordinal-judgments.json.gz'];gold=read(BASE/'ordinal-judgments.json.gz');pan=read(BASE/'panels.json')
    out={q:dict(repo=z['repo'],arms=ev.state(z,gold[q])) for q,z in pred.items()};dump('outcomes.json.gz',out);dump('ordinal-judgments.json.gz',gold)
    panels={k:aggregate(pan[k],out,pred) for k in ('dev','outside','test','pilot')}
    dump('results.json',dict(panels=panels,metrics=ev.METRICS,forecast=sha(D/'forecast-seal.json'),outcomes=sha(D/'outcomes.json.gz'),gold=sha(D/'ordinal-judgments.json.gz'),
         primary_confirmation=sha(CONF/'manifest.json'),native_prefixes=len(out)*2*8))
    print('Scored',len(out),'states and',len(out)*16,'official depth checks.')
if __name__=='__main__':
    if len(sys.argv)!=2 or sys.argv[1] not in ('predict','grade'):raise SystemExit('expected predict or grade')
    (predict if sys.argv[1]=='predict' else grade)()

