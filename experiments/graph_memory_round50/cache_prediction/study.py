"""Repo-disjoint training, archived next-state labels for training, and blind-to-future admission at inference."""
from collections import defaultdict,Counter
from time import perf_counter_ns
import hashlib
import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from build_inputs import D,W,OLD,sha,read,put
from predict import LOCAL,GRAPH,N_LOCAL,select,candidates,retention
from experiment import Cache,Keys
PROTO='993e33ce4c6ba26c5326b2683d7e4f113ae12558c3dad7e54f86c670734d83bb'


def fold(repo):
    return int(hashlib.sha256(repo.encode()).hexdigest(),16)%5


def teach(rows):
    """Training distribution uses the fixed baseline for all history before the decision."""
    train=[]
    for q,z in rows.items():
        if z['panel']!='R48' or not z['prev']:continue
        history=z['prev'];teacher=Cache('proposed',31,Keys());resident={}
        for stage,p in enumerate(history):
            par=rows[p]
            keys,features,record=candidates(resident,par,stage,True)
            if p==history[-1]:
                # Only here the offline label of the supervised transition is read.
                labels=np.array([k in z['docs'] for k in keys],dtype=np.int8)
                train.append((z['repo'],q,features,labels))
                break
            teacher.operate({k:par['docs'][k][0] for k in par['order']})
            resident={k:record[k] for k in teacher.entries()}
    return train


def fit(samples,which):
    cut=N_LOCAL if which=='local' else N_LOCAL+len(GRAPH)
    X=np.concatenate([v[2][:,:cut] for v in samples]);y=np.concatenate([v[3] for v in samples])
    w=np.concatenate([np.full(len(v[3]),1/len(v[3])) for v in samples]);w*=len(w)/w.sum()
    scaler=StandardScaler().fit(X,sample_weight=w)
    clf=LogisticRegression(C=1.0,solver='liblinear',max_iter=500,random_state=501271).fit(scaler.transform(X),y,sample_weight=w)
    beta=clf.coef_[0]/scaler.scale_;intercept=float(clf.intercept_[0]-beta@scaler.mean_)
    assert np.allclose(X@beta+intercept,clf.decision_function(scaler.transform(X)),rtol=1e-9,atol=1e-9)
    return dict(coef=beta.tolist(),intercept=intercept,features=(LOCAL+GRAPH)[:cut],scaler_mean=scaler.mean_.tolist(),scaler_scale=scaler.scale_.tolist(),
        train_states=sorted(v[1] for v in samples),train_repos=sorted({v[0] for v in samples}),n_examples=len(y),n_positive=int(y.sum()))


def run():
    assert sha(D/'PROTOCOL_RU.md')==PROTO and sha(D/'NUMERICS_RU.md')=='919316430b6df8306e9130d741bfa7cddd16f993a168dae49e665d0fe39758dc'
    rows=read(D/'inputs.json.gz');examples=teach(rows);banks={}
    for tag in ['transfer','0','1','2','3','4']:
        samples=examples if tag=='transfer' else [v for v in examples if str(fold(v[0]))!=tag]
        banks[tag]={a:fit(samples,a) for a in ('local','graph')}
    put('models.json',banks);obs={}
    cache={p:read(OLD/(p+'-outcomes.json.gz')) for p in ['R48','R49']}
    for q,z in rows.items():
        tag='transfer' if z['panel']=='R49' else str(fold(z['repo']))
        unit=dict(repo=z['repo'],panel=z['panel'],fold=tag,total=z['total'],within=z['within'],arms={},ns={})
        for mode in ('local','graph'):
            m=banks[tag][mode];assert z['repo'] not in m['train_repos']
            resident={}
            for stage,p in enumerate(z['prev']+[q]):
                current=rows[p]
                if p==q:
                    unit['arms'][mode]=retention(resident,current)
                    unit[mode+'_retained']=sorted(resident)
                t=perf_counter_ns();resident=select(resident,current,stage,m,mode=='graph');elapsed=perf_counter_ns()-t
                if p==q:unit['ns'][mode]=elapsed
        for mode in ['proposed','lru_costhot','gdsf','cost']:unit['arms'][mode]=cache[z['panel']][q]['batch'][mode]
        obs[q]=unit
    put('outcomes.json.gz',obs)
    return obs


def summarize(obs):
    repos=sorted({z['repo'] for z in obs});grp=[[z for z in obs if z['repo']==r] for r in repos]
    ns=len(repos);bs=np.random.default_rng(501271).multinomial(ns,np.full(ns,1/ns),size=20000)
    den=np.array([sum(z['total'] for z in g) for g in grp]);num={a:np.array([sum(z['arms'][a][1] for z in g) for g in grp]) for a in obs[0]['arms']}
    base=num['graph'];out={};dups=sum(z['within'] for z in obs)
    for m,v in num.items():
        diff=base-v;out[m]=dict(hits=sum(z['arms'][m][0] for z in obs),saved=int(v.sum()),net=int(den.sum()-dups-v.sum()),
            rate=v.sum()/den.sum(),macro=float(np.mean(v/den)),delta=diff.sum()/den.sum(),tokens=int(diff.sum()),
            ci=np.quantile((bs@diff)/(bs@den),[.025,.975]).tolist(),macro_delta=np.mean(diff/den))
    return dict(states=len(obs),repos=ns,total=int(den.sum()),within=dups,arms=out,write_ms={
        a:dict(median=np.median([z['ns'][a] for z in obs])/1e6,p95=np.percentile([z['ns'][a] for z in obs],95)/1e6) for a in ('local','graph')})


def main():
    obs=run();s={p:summarize([z for z in obs.values() if z['panel']==p]) for p in ['R48','R49']}
    for f in range(5):s['fold'+str(f)]=summarize([z for z in obs.values() if z['fold']==str(f)])
    put('results.json',dict(panels=s,protocol=PROTO,inputs=sha(D/'inputs.json.gz'),models=sha(D/'models.json'),outcomes=sha(D/'outcomes.json.gz')))
    print({p:{k:[round(v['delta']*100,3),[round(x*100,3) for x in v['ci']]] for k,v in s[p]['arms'].items()} for p in ['R48','R49']})


if __name__=='__main__':main()

