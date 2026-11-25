"""Refit within each storage semantics. No test/span outcomes read by fit, predict, or seal."""
import os
for v in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS'): os.environ[v]='1'
import sys
import hashlib
from collections import defaultdict
from pathlib import Path
D=Path(__file__).resolve().parent
INCR=D.parent/'incremental_binding'
sys.path.insert(0,str(INCR))
import predict_readout as inc
from operators import packed_stats,features_in_rank_order,rank_strength
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
import numpy as np
ref=inc.ref
R20=inc.R20
PRIVATE=Path('D:/CodexResearch/x20-field-refit')
PRIVATE.mkdir(exist_ok=True)
ARMS=('dense','exact/exact','exact/append','append/exact','append/append','dual/both','dual/zero','r20/exact','r20/append')


def sha(p): return ref.sha(p)
def read(p): return ref.read(p)
def save(p,x): return ref.put(p,x)


def src_plan():
    paths=[D/'PROTOCOL_RU.md',Path(__file__),INCR/'stream.py',INCR/'predict_readout.py',D.parent/'factorized_provenance/operators.py',D.parent/'factorized_provenance/study.py',R20/'typed_reader/study.py',R20/'typed_reader/weights.json',ref.RES/'dev500-pu-dense-ranks.json.gz',ref.TR/'split.json.gz',INCR/'plan.json',R20/'typed_reader/holdout80/source-plan.json',ref.TR/'forecast-seal.json']
    return {str(p.name if p.parent==D else p.relative_to(D.parents[1])).replace('\\','/'):sha(p) for p in paths}


def geometry(i):
    targets=read(ref.TR/'split.json.gz')
    extras=read(R20/'typed_reader/holdout80/source-plan.json')
    keep=set(r['t'] for k in ('dev','test') for r in targets[k]) | set(extras['novel_trajectories'])
    graphs=ref.graph_index()
    for t,x in extras['records'].items():
        if not x['native']: graphs[t]=(Path('D:/CodexResearch/x20-typed-reader-private')/(t+'.json.gz'),x['sha'])
    fname=f'trajectories-{i:05d}.jsonl';raw=inc.env.RAW/fname
    h=next(z['sha256'] for z in read(inc.env.R18/'isetrace_official/source-lock.json') if z['path']=='trajectories/'+fname)
    assert sha(raw)==h
    out={}
    for line,record in inc.env.pilot.stream(raw):
        t=record['session_id']
        if t not in keep: continue
        tr=inc.adapt_isetrace_record(inc.parse_isetrace_record(record),source_revision=inc.env.pilot.RAW[1])
        path,wanted=graphs[t];assert sha(path)==wanted
        graph=read(path)
        assert graph['raw_source']==hashlib.sha256(line).hexdigest()
        ids,geom=inc.geometry(graph)
        append,_,diag=inc.structure(tr,graph['g'],ids,geom)
        exact=set(map(tuple,geom.links.tolist()))
        extra=sorted(set(map(tuple,append.links.tolist()))-exact)
        assert len(extra)==diag['extra'] and all(row[2]==2 for row in extra)
        out[t]=[list(ids),geom.membership.tolist(),geom.adjacent.tolist(),geom.links.tolist(),extra]
    dest=PRIVATE/f'geometry-{i}.json.gz'
    save(dest,out)
    save(D/f'geometry-{i}-lock.json',dict(source=h,geometries=sha(dest),records=len(out),stale_edges=sum(len(x[4]) for x in out.values())))
    print('geometry',i,len(out),flush=True)


def load_graphs(shards=range(8)):
    result={}
    for k in shards:
        p=PRIVATE/f'geometry-{k}.json.gz'
        assert sha(p)==read(D/f'geometry-{k}-lock.json')['geometries']
        result.update(read(p))
    return result


def design(g,rr):
    names,m,adj,links,extra=g
    ids={v:i for i,v in enumerate(names)}
    order=np.array([ids[x['node_id']] for x in rr],dtype=int)
    assert len(set(order))==len(order)==len(ids)
    strength=rank_strength(order)
    base=inc.Packed(np.asarray(m),inc.table(adj,2),inc.table(links,3))
    exact=features_in_rank_order(order,packed_stats(base,strength))
    append=exact
    if extra:
        top=inc.Packed(base.membership,base.adjacent,inc.table(links+extra,3))
        append=features_in_rank_order(order,packed_stats(top,strength))
    # Features 15..20 inclusive correspond to directed outgoing/incoming data.feeds.
    assert np.array_equal(exact[:,:15],append[:,:15]) and np.array_equal(exact[:,21:],append[:,21:])
    dual=np.column_stack((exact,append[:,15:21]-exact[:,15:21]))
    return dict(exact=exact,append=append,dual=dual)


def fit():
    plan=src_plan()
    save(D/'plan.json',plan)
    rows=read(ref.RES/'dev500-pu-dense-ranks.json.gz')
    by=defaultdict(list)
    for r in rows:by[r['t']].append(r)
    graphs=load_graphs()
    calibrator=read(ref.TR/'split.json.gz')
    assert {r['q'] for r in rows}=={r['q'] for r in calibrator['dev']}
    assert not set(by)&{r['t'] for r in calibrator['test']}
    ys=[];weights=[];storage=defaultdict(list)
    for t,rs in sorted(by.items()):
        truth={r['q']:set(r['positive']) for r in read(ref.PROJ/'projection/dev'/(t+'.json.gz'))['qs']}
        for r in rs:
            rr=r['rr']; y=np.array([n['node_id'] in truth[r['q']] for n in rr],dtype=int)
            p=y.sum();neg=len(y)-p
            if not p or not neg: continue
            ys.append(y);weights.append(np.where(y,.5/p,.5/neg))
            for k,v in design(graphs[t],rr).items():storage[k].append(v)
    y=np.concatenate(ys);w=np.concatenate(weights);w*=len(w)/w.sum()
    models={}
    for k,allx in storage.items():
        x=np.concatenate(allx)
        sc=StandardScaler().fit(x,sample_weight=w)
        z=LogisticRegression(C=1,solver='lbfgs',max_iter=1000,random_state=13)
        z.fit(sc.transform(x),y,sample_weight=w)
        coef=z.coef_[0]/sc.scale_;bias=z.intercept_[0]-np.dot(coef,sc.mean_)
        assert max(z.n_iter_)<1000 and np.allclose(x@coef+bias,z.decision_function(sc.transform(x)),atol=1e-10,rtol=1e-10)
        models[k]=dict(w=coef.tolist(),bias=float(bias),n_iter=int(z.n_iter_[0]))
    old=read(R20/'typed_reader/weights.json')['typed']
    save(D/'weights.json',models)
    save(D/'fit-lock.json',dict(plan=sha(D/'plan.json'),weights=sha(D/'weights.json'),q=len(rows),t=len(by),fs_used=len(ys),nodes=len(y),positive=int(y.sum()),max_abs_delta_exact_old=float(np.max(abs(np.array(old['w'])-models['exact']['w'])))))
    print('fit',len(y),int(y.sum()),flush=True)


def verify_fit():
    lock=read(D/'fit-lock.json')
    assert read(D/'plan.json')==src_plan() and sha(D/'weights.json')==lock['weights'] and sha(D/'plan.json')==lock['plan']


def predict(part):
    verify_fit()
    if part=='extra':
        pp=R20/'untuned_holdout/dense-ranks-extra80.json.gz';seal=read(R20/'untuned_holdout/forecast-seal.json')
        assert sha(pp)==seal['ranks']
        rows=read(pp);rows=rows['rows'] if isinstance(rows,dict) else rows
        novel=set(read(R20/'typed_reader/holdout80/source-plan.json')['novel_trajectories'])
        rows=[r for r in rows if r['t'] in novel]
        assert len(rows)==27
        graphs=load_graphs()
    else:
        i=int(part);fname=f'forecasts-main-{i}.json.gz';pp=ref.TR/fname
        assert sha(pp)==read(ref.TR/'forecast-seal.json')['forecasts'][fname]
        rows=read(pp);graphs=load_graphs([i])
    models=read(D/'weights.json');models['r20']=read(R20/'typed_reader/weights.json')['typed']
    pilot=set(read(INCR/'plan.json')['trajectories'])
    old={r['q']:r for r in read(INCR/f'readout-{part}.json.gz')} if part!='extra' else {}
    pred=[]
    for r in rows:
        t=r['t'];q=r['q'];rr=r['rr'];x=design(graphs[t],rr)
        x['both']=x['dual']
        x['zero']=x['dual'].copy();x['zero'][:,27:]=0
        cost=[n['token_count'] for n in rr];picks={}
        for a in ARMS:
            if a=='dense':order=np.arange(len(rr))
            else:
                train,readout=a.split('/');m=models[train]
                order=np.argsort(-(x[readout]@m['w']+m['bias']),kind='stable')
            picks[a]=ref.pack(order,cost,False)
        if old:
            assert picks['r20/exact']==old[q]['picks']['exact'] and picks['r20/append']==old[q]['picks']['append']
        pred.append(dict(q=q,t=t,pilot=t in pilot,picks=picks))
    p=D/f'forecast-{part}.json.gz';save(p,pred)
    save(D/f'forecast-{part}-lock.json',dict(input=sha(pp),weights=sha(D/'weights.json'),forecast=sha(p),q=len(pred),t=len({r['t'] for r in pred})))
    print('forecast',part,len(pred),flush=True)


def seal():
    rows=[];locks={}
    for i in range(8):
        p=D/f'forecast-{i}.json.gz';lock=read(D/f'forecast-{i}-lock.json')
        assert sha(p)==lock['forecast'] and lock['weights']==sha(D/'weights.json')
        rows.extend(read(p));locks[p.name]=sha(p)
    assert len(rows)==2000 and len({r['q'] for r in rows})==2000
    assert {r['q'] for r in rows}=={r['q'] for r in read(ref.TR/'split.json.gz')['test']}
    save(D/'forecast-seal.json',dict(shards=locks,rows=len(rows),fit=sha(D/'fit-lock.json')))


if __name__=='__main__':
    mode=sys.argv[1]
    if mode=='geo':
        for i in map(int,sys.argv[2:]):geometry(i)
    elif mode=='fit':fit()
    elif mode=='predict':
        for p in sys.argv[2:]:predict(p)
    elif mode=='seal':seal()

