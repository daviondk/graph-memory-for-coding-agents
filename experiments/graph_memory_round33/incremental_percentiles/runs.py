"""Numeric fixture replay, dynamic vs deferred baselines, and independent reference."""
from index import DegreeIndex,NCH,score_rows,shape,signal,np
from pathlib import Path
import sys,hashlib,json,gzip,time,tracemalloc,gc
from collections import Counter,defaultdict
from scipy.stats import rankdata
D=Path(__file__).resolve().parent;W=D.parents[1]
MODES=("incremental","deferred_hist","deferred_edges")
def load(p):
    b=p.read_bytes();return json.loads(gzip.decompress(b) if p.suffix==".gz" else b)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def save(p,x):
    b=json.dumps(x,sort_keys=True,separators=(",",":"),allow_nan=False).encode()
    p.write_bytes(gzip.compress(b,mtime=0,compresslevel=3) if p.suffix==".gz" else b)
def inputs():
    lock=load(D/"fixture-lock.json");rows=[]
    for k,h in lock["files"].items():
        assert sha(D/k)==h
        rows.extend(load(D/k))
    p=W/"graph_memory_round33/relative_structure/weights.json";a=W/"graph_memory_round20/factor_reader/hash64-weights.json"
    assert sha(p)==lock["weights"] and sha(a)==lock["rank_model"]
    m=load(p)["models"]["global_role"];return rows,np.array(m["coef"]),m["intercept"],load(a)["rank"]
def ref(attrs,edges):
    ids=sorted(attrs);where={k:j for j,k in enumerate(ids)}
    meta=np.asarray([attrs[k] for k in ids],int).reshape(-1,4);deg=np.zeros((len(ids),8),int)
    for a,b,k in edges:deg[where[a],k*2]+=1;deg[where[b],2*k+1]+=1
    re=np.empty(deg.shape)
    for role in (0,1):
        ix=np.flatnonzero(meta[:,0]==role)
        if len(ix):re[ix]=(rankdata(np.log1p(deg[ix]),axis=0,method="average")-.5)/len(ix)-.5
    return np.asarray(ids,dtype=int),meta,deg,re
def inverse(state,attrs):
    back={"minus":state["plus"],"plus":state["minus"],"rm":[],"up":[]}
    for a,*v in state["up"]:
        if a not in attrs:back["rm"].append(a)
        else:back["up"].append([a,*attrs[a]])
    for a in state["rm"]:back["up"].append([a,*attrs[a]])
    return back
def replay():
    rows,coef,bias,rank=inputs();allstats=[];n_queries=0;endmatches=0;reverse=0;maxerr=0.
    qmap={}
    for i in range(8):
        can=load(W/f"graph_memory_round19/trained_rank/forecasts-main-{i}.json.gz")
        fcasts={v["q"]:v["orders"]["global_role"] for v in load(W/f"graph_memory_round33/relative_structure/ranks-{i}.json.gz")}
        for v in can:qmap.setdefault(v["t"],[]).append(fcasts[v["q"]])
    for tr in rows:
        t=tr["t"];attrs={};edges=set();prev={};back=[];states=[];stores=[DegreeIndex(m) for m in MODES]
        for it,s in enumerate(tr["steps"]):
            back.append(inverse(s,attrs))
            minus=set(map(tuple,s["minus"]));plus=set(map(tuple,s["plus"]))
            assert minus<=edges and not edges.intersection(plus);edges.difference_update(minus);edges.update(plus)
            for a in s["rm"]:del attrs[a]
            for a,*v in s["up"]:attrs[a]=v
            digest=hashlib.sha256(json.dumps([sorted(attrs.items()),sorted(edges)],separators=(",",":")).encode()).hexdigest()
            assert digest==s["snapshot"];ids,meta,deg,rel=ref(attrs,edges);lookup=dict(zip(ids,range(len(ids))))
            feats=np.column_stack((shape(meta),np.log1p(deg),rel));scores=feats@coef+bias
            for store in stores:
                store.update(s);a,b,c=store.rows(ids);ff=np.column_stack((shape(a),np.log1p(b),c))
                assert np.array_equal(ff,feats);est=store.read(ids,coef,bias)
                maxerr=max(maxerr,float(np.max(np.abs(est-scores),initial=0)))
                assert np.allclose(est,scores,rtol=0,atol=1e-12)
                for qq,order in enumerate(s["dense"]):
                    perm=np.array([lookup[a] for a in order],int);n=len(perm);off=signal(n,n,rank)
                    ans=np.argsort(-(off+scores[perm]),kind="stable");got=np.argsort(-(off+est[perm]),kind="stable")
                    assert np.array_equal(ans,got)
                    if store is stores[0] and it==len(tr["steps"])-1:
                        assert ans.tolist()==qmap[t][qq];endmatches+=1
            oldrows=0;changed=relative=untouched_relative=0
            for j,a in enumerate(ids):
                if a in prev:
                    oldrows+=1;dc=not np.array_equal(prev[a][0],deg[j]);rc=not np.array_equal(prev[a][1],rel[j])
                    changed+=dc;relative+=rc;untouched_relative+=rc and not dc
            prev={a:(d.copy(),r.copy()) for a,d,r in zip(ids,deg,rel)}
            n_queries+=len(s["dense"])
            st={"t":t,"step":it,"q":len(s["dense"]),"V":len(ids),"E":len(edges),"new_or_updated":len(s["up"]),"deleted":len(s["rm"]),
                "edges_added":len(plus),"edges_revoked":len(minus),"old":oldrows,"old_degree_changed":changed,
                "old_percentile_changed":relative,"old_percentile_changed_without_degree":untouched_relative,
                "degree_rows_written":changed+len(ids)-oldrows,"maxdegree":int(deg.max(initial=0))}
            allstats.append(st);states.append((ids,feats))
        store=stores[0]
        for j,change in enumerate(reversed(back)):
            store.update(change)
            if j==len(back)-1:
                assert not store.alive.any() and store.hist.sum()==0
            else:
                ids,target=states[-j-2];a,b,c=store.rows(ids);assert np.array_equal(np.column_stack((shape(a),np.log1p(b),c)),target)
            reverse+=1
    save(D/"by-state.json.gz",allstats)
    sums={k:sum(v[k] for v in allstats) for k in ("V","E","new_or_updated","deleted","edges_added","edges_revoked","old","old_degree_changed","old_percentile_changed","old_percentile_changed_without_degree","degree_rows_written")}
    save(D/"equivalence.json",{"trajectories":len(rows),"states":len(allstats),"question_states":n_queries,"terminal_orders_match_published":endmatches,
         "max_score_error":maxerr,"max_degree":max(v["maxdegree"] for v in allstats),"retraction_states":sum(v["edges_revoked"]>0 for v in allstats),
         "by_state":sha(D/"by-state.json.gz"),"sums":sums,"reverse_checks":reverse,"protocol":sha(D/"PROTOCOL_RU.md"),"code":sha(D/"runs.py"),"index":sha(D/"index.py")})
def workload(steps,how,subset):
    ops=[]
    for j,s in enumerate(steps):
        read=how=="each" or j==len(steps)-1 or how=="fourth" and (j+1)%4==0
        if not read:ops.append((s,None));continue
        orders=[np.array(v if subset=="all" else v[:8],int) for v in s["dense"]]
        unique=np.unique(np.concatenate(orders))
        # Global IDs are persistent but may be sparse. Materialize scores once per state.
        compact=[np.searchsorted(unique,p) for p in orders]
        ops.append((s,(unique,compact,len(s["dense"][0]))))
    return ops
def play(mode,ops,c,b,r,measure_memory=False):
    if measure_memory:gc.collect();tracemalloc.start()
    start=time.perf_counter_ns();idx=DegreeIndex(mode);digest=0
    for step,read in ops:
        idx.update(step)
        if read is not None:
            ids,orders,n=read;prior=idx.read(ids,c,b)
            for perm in orders:
                ranked=np.argsort(-(prior[perm]+signal(n,len(perm),r)),kind="stable");digest+=int(ranked[0])
    dt=time.perf_counter_ns()-start
    if measure_memory:
        cur,peak=tracemalloc.get_traced_memory();tracemalloc.stop();return [cur,peak]
    return dt,digest
def bench():
    rows,c,b,r=inputs();times=[];mem=[]
    for j,tr in enumerate(rows):
        for freq in ("each","fourth","last"):
            for scope in ("all","eight"):
                ops=workload(tr["steps"],freq,scope);record={m:[] for m in MODES};checks=set()
                for rep in range(6):
                    offset=(rep+j)%len(MODES)
                    for m in MODES[offset:]+MODES[:offset]:
                        tm,cs=play(m,ops,c,b,r);checks.add(cs)
                        if rep>0:record[m].append(tm)
                assert len(checks)==1
                times.append({"t":tr["t"],"freq":freq,"scope":scope,"nstate":len(ops),"nread":sum(o[1] is not None for o in ops),"ns":record})
        ops=workload(tr["steps"],"each","all")
        mem.append({"t":tr["t"],"bytes":{m:play(m,ops,c,b,r,True) for m in MODES}})
    save(D/"paired-times.json.gz",times);save(D/"allocated.json.gz",mem)
    result={}
    def ci(rat):
        logs=np.log(rat);rng=np.random.default_rng(13);bs=rng.integers(len(logs),size=(10000,len(logs)))
        return [float(np.exp(logs.mean())),*np.exp(np.quantile(logs[bs].mean(axis=1),[.025,.975])).tolist()]
    for freq in ("each","fourth","last"):
        for scope in ("all","eight"):
            group=[v for v in times if (v["freq"],v["scope"])==(freq,scope)];med={m:np.array([np.median(v["ns"][m]) for v in group]) for m in MODES}
            result[f"{freq}/{scope}"]={"reads":sum(z["nread"] for z in group),"ms_for_48":{m:float(a.sum()/1e6) for m,a in med.items()},
                "geometric_ratio_95":{m:ci(med["incremental"]/med[m]) for m in MODES[1:]}}
    save(D/"bench.json",{"summary":result,"median_per_trajectory_peak_python_numpy_bytes":{m:float(np.median([z["bytes"][m][1] for z in mem])) for m in MODES},
                         "median_per_trajectory_retained_bytes":{m:float(np.median([z["bytes"][m][0] for z in mem])) for m in MODES},
                         "fixture_load_and_peak_workload_arrays_excluded":True,"timing_source":sha(D/"paired-times.json.gz"),"mem_source":sha(D/"allocated.json.gz")})
if __name__=="__main__":{"verify":replay,"bench":bench}[sys.argv[1]]()