"""Simultaneous trajectory-cluster intervals for both fixed readers on eight endpoints."""
from collections import defaultdict
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import numpy as np

D = Path(__file__).resolve().parent
SOURCE = D.parent.parent/"graph_memory_round20"/"factor_reader"
METRICS = ["coverage_512","coverage_1024","coverage_2048","full_support_2048","recall_5","mrr","coverage_auc","full_support_auc"]
ARMS = ["dense","rgcn","degree","factor"]
def load(p):
    b = p.read_bytes()
    return json.loads(gzip.decompress(b) if p.suffix==".gz" else b)
def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,obj):
    b = (json.dumps(obj, sort_keys=True, separators=(",",":"))+"\n").encode()
    p.write_bytes(gzip.compress(b,mtime=0) if p.suffix==".gz" else b)
def prepare():
    sources = [SOURCE/"metrics-test-rows.json.gz", SOURCE/"metrics-full-rows.json.gz"]
    data = load(sources[0]) | load(sources[1])
    ids = sorted(data["rgcn"])
    assert len(ids)==2000 and all(set(data[a])==set(ids) for a in ARMS)
    rows=[]
    for q in ids:
        t=data["rgcn"][q]["t"]
        assert all(data[a][q]["t"]==t for a in ARMS)
        rows.append([q,t,[[data[a][q][m] for m in METRICS] for a in ARMS]])
    packet=D/"by-query.json.gz"
    write(packet,{"arms":ARMS,"metrics":METRICS,"rows":rows})
    write(D/"source-lock.json",{"rows":sha(packet),"inputs":{p.name:sha(p) for p in sources},"protocol":sha(D/"PROTOCOL_RU.md")})
def calculate():
    packet=D/"by-query.json.gz"
    assert sha(packet)==load(D/"source-lock.json")["rows"]
    d=load(packet)
    assert d["arms"]==ARMS and d["metrics"]==METRICS
    rows=d["rows"]
    X=np.asarray([r[2] for r in rows],dtype=np.float64)
    groups,ids=np.unique([r[1] for r in rows],return_inverse=True)
    n=len(rows);g=len(groups)
    assert (n,g)==(2000,1207) and np.isfinite(X).all()
    diff=(X[:,2:,:]-X[:,1:2,:]).reshape(n,-1)
    effect=diff.mean(axis=0)
    residual=np.zeros((g,len(effect)))
    np.add.at(residual,ids,diff-effect)
    scale=np.sqrt((residual**2).sum(axis=0))
    assert np.all(scale>0) and np.max(np.abs(residual.sum(axis=0)))<1e-9
    se=scale*np.sqrt(g/(g-1))/n
    rng=np.random.default_rng(22601)
    B=40000
    maxima=[]
    for start in range(0,B,256):
        signs=2*rng.integers(0,2,size=(min(256,B-start),g),dtype=np.int8)-1
        z=signs.astype(float) @ (residual/scale)
        maxima.extend(np.max(np.abs(z),axis=1))
    maxT=np.asarray(maxima)
    critical=float(np.quantile(maxT,.95))
    tests={}
    for i,k in enumerate(a+"/"+m for a in ARMS[2:] for m in METRICS):
        tests[k]={"delta_pp":float(100*effect[i]),"se_pp":float(100*se[i]),
                  "simul95_pp":[float(100*(effect[i]-critical*se[i])),float(100*(effect[i]+critical*se[i]))],
                  "adjusted_p":float((1+(maxT>=abs(effect[i]/se[i])).sum())/(B+1))}
    summary={a:{m:float(X[:,i,j].mean()) for j,m in enumerate(METRICS)} for i,a in enumerate(ARMS)}
    write(D/"results.json",{"questions":n,"trajectories":g,"comparisons":len(tests),"draws":B,
                             "critical":critical,"family":tests,"means":summary,"source":sha(packet)})
    print("critical",critical,"simultaneous intervals excluding zero",
          {k:v for k,v in tests.items() if v["simul95_pp"][0]>0 or v["simul95_pp"][1]<0},flush=True)
if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--prepare",action="store_true")
    args=parser.parse_args()
    if args.prepare:prepare()
    calculate()

