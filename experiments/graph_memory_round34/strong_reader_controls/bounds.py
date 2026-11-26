"""Identify sharp event-overlap bounds and construct feasible per-query tables from marginals."""
from collections import defaultdict
from itertools import permutations
from math import ceil,floor,isqrt
from pathlib import Path
import gzip,hashlib,json
import numpy as np

HERE=Path(__file__).resolve().parent
WORK=HERE.parents[1]
DATA=WORK/"graph_memory_round33/budget_frontier"
NATIVE=WORK/"graph_memory_round34/native_comparison/outcomes-13.json.gz"
META=Path("D:/CodexResearch/x20-isetrace-runtime/inputs/query-authoring/isetrace-v7-raw.jsonl.metadata.jsonl")
SEEDS=["13","17","29","37","41"]
MODES=["direct_recall","linked_recall","multi_fact_recall"]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):
    return json.loads(gzip.decompress(p.read_bytes()) if p.suffix==".gz" else p.read_bytes())
def save(p,v):
    data=(json.dumps(v,separators=(",",":"),sort_keys=True)+"\n").encode()
    p.write_bytes(gzip.compress(data,mtime=0) if p.suffix==".gz" else data)
def possibilities(n,mean,sd):
    # Every binary seed-mean is k/n. Two rounded percentages constrain sum(k) and sum(k^2).
    totals=[s for s in range(5*n+1) if abs(100*s/(5*n)-mean)<.00500000001]
    assert len(totals)==1
    s=totals[0];lo=(sd-.005)*n/100;hi=(sd+.005)*n/100;mu=s/5
    options=set()
    for ss in range(ceil(s*s/5+4*lo**2-1e-7),floor(s*s/5+4*hi**2+1e-7)+1):
        # |k_i-mu| <= sqrt(4*4/5)*sd in count units; slightly looser bound is harmless.
        lower=max(0,floor(mu-2*hi)-1);upper=min(n,ceil(mu+2*hi)+1)
        for a in range(lower,upper+1):
            for b in range(a,upper+1):
                for c in range(b,upper+1):
                    tail=s-a-b-c
                    d2=2*(ss-a*a-b*b-c*c)-tail*tail
                    if d2<0:continue
                    d=isqrt(d2)
                    if d*d!=d2 or (tail-d)%2:continue
                    e=(tail-d)//2; f=tail-e
                    if c<=e<=f<=upper:options.add((a,b,c,e,f))
    assert options
    for o in options:
        assert abs(100*np.mean(o)/n-mean)<.00500001 and abs(100*np.std(o,ddof=1)/n-sd)<.00500001
    return sorted(options)

def possibilities_to_extrema(n,counts,options):
    sort_order=np.argsort(counts,kind="stable")
    sf=counts[sort_order]
    best=min(options,key=lambda v:(sum(abs(x-y) for x,y in zip(sf,v)),v))
    lo=np.empty(5,dtype=int);lo[sort_order]=best
    # When all success-count sums exceed n, upper disagreement = 2*n - a - b independently of pairing.
    if min(counts)+min(min(x) for x in options)>=n:hi=np.asarray(options[0])
    else:
        perms=(p for x in options for p in permutations(x))
        hi=np.asarray(max(perms,key=lambda b:sum(min(x+y,2*n-x-y) for x,y in zip(counts,b))))
    return lo,hi

def assign(A,counts,max_diff,priority):
    m=len(A);Y=np.zeros_like(A)
    for j,c in enumerate(counts):
        # Sort successes last for maximal disagreement, first for minimal disagreement.
        pre=np.argsort(np.where(A[priority,j],1 if max_diff else -1,0),kind="stable")
        Y[priority[pre[:c]],j]=1
    return Y

def actual(a,b,clusters):
    arr=a-b
    mean=arr.mean(axis=1);t=sorted(set(clusters));idx={x:i for i,x in enumerate(t)}
    slots=np.array([idx[x] for x in clusters]); size=np.bincount(slots)
    sums=np.bincount(slots,weights=mean)
    rng=np.random.default_rng(13); samples=[]
    for _ in range(100):
        take=rng.integers(len(t),size=(100,len(t)));samples.extend(sums[take].sum(1)/size[take].sum(1))
    return {"a_pct":100*float(a.mean()),"b_pct":100*float(b.mean()),"delta_pp":100*float(mean.mean()),
        "ci95_pp":(100*np.quantile(samples,[.025,.975])).tolist(),"wins":int(np.sum(arr==1)),"losses":int(np.sum(arr==-1)),
        "agreement":int(np.sum(arr==0)),"questions_any_disagreement":int(np.sum(np.any(arr!=0,axis=1)))}

def audit_native(rows,ids,A,types,ts):
    assert sorted(rows)==ids
    out={}
    for j,name in ((2,"full_rgcn"),(3,"wo_chunk_adjacency")):
        n=len(A);y=np.array([rows[q][j][0] for q in ids],dtype=int)[:,None]
        assert np.array_equal(A[:,0],[rows[q][1][0] for q in ids]) and all(ts[i]==rows[q][0] for i,q in enumerate(ids))
        bounds={}
        for kind in ("low","high"):
            yhat=np.zeros_like(y)
            for m in MODES:
                take=np.flatnonzero(types==m); yhat[take]=assign(A[take,:1],y[take].sum(axis=0),kind=="high",np.arange(len(take)))
            bounds[kind]=actual(A[:,:1],yhat,ts)
        real=actual(A[:,:1],y,ts); assert bounds["low"]["wins"]<=real["wins"]<=bounds["high"]["wins"]
        out[name]={"actual":real,"extremes_if_margins_only":bounds}
    return out

def main():
    x={}; hashes={}
    for i in range(8):
        p=DATA/f"repeat-outcomes-{i}.json.gz";hashes[p.name]=sha(p)
        part=read(p);assert not (x.keys()&part.keys());x.update(part)
    meta={v["query_id"]:v for v in map(json.loads,META.open(encoding="utf8"))}
    q=sorted(x);ts=[x[k]["t"] for k in q];types=np.array([meta[k]["memory_mode"] for k in q])
    assert len(q)==2000 and len(set(ts))==1207 and all(a==meta[k]["trajectory_id"] for a,k in zip(ts,q))
    A=np.array([[x[k]["seeds"][s]["cost"][6] for s in SEEDS] for k in q],dtype=int)
    assert A.sum()==8046
    ref=read(HERE/"discovery.json")["paper"]["tables"]["S7.T3"];row=next(v for v in ref if "chunk adjacency" in v[0])
    pct=[tuple(map(float,t.split(" ± "))) for t in row[1:]]
    synthetic={y:np.zeros_like(A) for y in ("low","high")}; strata={}
    for m,(mean,sd) in zip(MODES,pct):
        take=np.flatnonzero(types==m);n=len(take);local=A[take];counts=local.sum(axis=0)
        options=possibilities(n,mean,sd);low,high=possibilities_to_extrema(n,counts,options)
        order=sorted(range(n),key=lambda k:hashlib.sha256(("counterexample/"+ts[take[k]]+"/"+q[take[k]]).encode()).digest())
        for label,ranks in (("low",low),("high",high)):
            trial=assign(local,ranks,label=="high",np.asarray(order));assert np.array_equal(trial.sum(0),ranks)
            synthetic[label][take]=trial
        strata[m]={"n":n,"local":counts.tolist(),"total_published":sum(options[0]),"locally_feasible_published_count":len(options),
                   "mean":mean,"sample_sd":sd,"example_low":low.tolist(),"example_high":high.tolist()}
    counter={k:actual(A,v,ts) for k,v in synthetic.items()}
    witness={k:[ts[i],str(types[i]),A[i].tolist(),*[synthetic[s][i].tolist() for s in ("low","high")]] for i,k in enumerate(q)}
    save(HERE/"witnesses.json.gz",witness)
    out={"strata":strata,"feasible_examples":counter,"empirical":audit_native(read(NATIVE),q,A,types,ts),
         "source_hashes":hashes,"native":sha(NATIVE),"metadata":sha(META),"witnesses":sha(HERE/"witnesses.json.gz"),"script":sha(Path(__file__)),"protocol":sha(HERE/"PROTOCOL_RU.md")}
    save(HERE/"bounds.json",out)
    print(counter)
if __name__=="__main__":main()
