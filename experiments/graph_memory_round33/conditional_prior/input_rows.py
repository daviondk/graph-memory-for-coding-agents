"""CPU-only numerical inputs from stock ISETrace provenance candidates."""
import os
for k in ("OPENBLAS_NUM_THREADS","OMP_NUM_THREADS","MKL_NUM_THREADS","NUMEXPR_NUM_THREADS"):
    os.environ[k]="1"
os.environ["CUDA_VISIBLE_DEVICES"]="-1"
from pathlib import Path
import re, sys, sqlite3, hashlib, json, gzip
from collections import defaultdict
D=Path(__file__).resolve().parent
W=D.parents[1]
R19=W/"graph_memory_round19"
R20=W/"graph_memory_round20"
R21=W/"graph_memory_round21"
OFF=W/"graph_memory_round22/native_multiseed/official580"
PRIVATE=Path("D:/CodexResearch/x20-r33-conditional")
PRIVATE.mkdir(exist_ok=True)
sys.path.insert(0,str(R21/"five_seed"))
import study as hist
from study import f,pilot,load,sha,np
P=f.D/"prior.json"
M=f.D/"hash64-weights.json"
DATA=Path("D:/CodexResearch/x20-isetrace-trained/projection")
def write(path,obj):
    b=json.dumps(obj,ensure_ascii=False,sort_keys=True,separators=(",",":"),allow_nan=False).encode()
    tmp=path.with_suffix(path.suffix+".tmp")
    tmp.write_bytes(gzip.compress(b,mtime=0,compresslevel=3) if path.suffix==".gz" else b)
    tmp.replace(path)
def qfeatures(rr,text):
    s=np.asarray([row["score"] for row in rr],float)
    assert len(s) and np.all(np.diff(s)<=1e-6) and np.isfinite(s).all()
    a=s[:20];v=np.exp((a-a.max())/.03);v/=v.sum()
    words=re.findall(r"[a-z]+",text.lower());wordset=set(words)
    return [float(s[0]-s[min(1,len(s)-1)]),float(s[0]-s[min(4,len(s)-1)]),float(a.std()),float(-(v*np.log(v)).sum()/np.log(max(len(a),2))),
            float(np.log1p(len(words))),int(bool(wordset&{"before","after","first","last","previous","earlier","later","initial","final","initially","finally","when"})),
            int(bool(wordset&{"and","both","between","versus","compare","comparison","each"})),int(bool(wordset&{"why","how","reason","cause","explain"}))]
def prior(pool,graph):
    m=load(P)["models"]["prior"]
    keys,z=f.shape(pool,graph);return dict(zip(keys,f.lin(m,z[:,m["columns"]]).tolist(),strict=True))
def make(q,t,rr,qp,pr,pos=None):
    ids=[v["node_id"] for v in rr]
    assert set(ids)==set(pr) and len(pr)==len(ids)
    out={"q":q,"t":t,"x":qfeatures(rr,qp),"p":[pr[k] for k in ids]}
    if pos is not None:
        out["y"]=[j for j,k in enumerate(ids) if k in pos]
        assert len(out["y"])==len(pos)>0
    return out
def train():
    cohorts=load(R20/"residual_graph/cpu_fallback/cohorts.json")
    ts=sorted(set(cohorts["availability"]["t"])|set(cohorts["hash64"]["t"]))
    pt={t for v in load(P)["inventory"] for t in v["t"]};assert not pt.intersection(ts)
    con=hist.db_ro(Path("D:/CodexResearch/x20-isetrace-residual/vectors.sqlite3"))
    ret=f.DenseTaskRetriever(encoder=f.Lookup(con,"ft"),device="cpu")
    rows=[];ix=f.gmod.graph_index();qm=set()
    for t in ts:
        raw=load(DATA/"train"/(t+".json.gz"));pr=prior(raw["pool"],f.gmod.project(t,ix))
        cand=tuple(f.TextCandidate.model_validate(v) for v in raw["pool"])
        for r in raw["qs"]:
            q=r["q"];assert q not in qm;qm.add(q)
            req=f.TextRankingRequest(task_id=q,query_text=r["text"],candidates=cand)
            rr=[{"node_id":n.node_id,"score":n.score} for n in ret.rank(req)]
            rows.append(make(q,t,rr,r["text"],pr,set(r["positive"])))
    assert qm==set(cohorts["availability"]["q"])|set(cohorts["hash64"]["q"])
    out=PRIVATE/"train.json.gz";write(out,rows)
    write(D/"train-inputs.json",{"n":len(rows),"t":len(ts),"rows":sum(len(v["p"]) for v in rows),"features":sha(out),"code":sha(Path(__file__)),"prior":sha(P),"rankcal":sha(M),"cohorts":sha(R20/"residual_graph/cpu_fallback/cohorts.json")})
def devparents():
    return [R20/"residual_graph/dev500-pu-dense-ranks.json.gz",R20/"untuned_holdout/dense-ranks-extra80.json.gz"]
def testparents():
    return [R19/f"trained_rank/forecasts-main-{i}.json.gz" for i in range(8)]
def prepare(split):
    if split=="test":assert (D/"dev-selection.json").exists()
    paths=devparents() if split=="dev" else testparents()
    ids=load(OFF/"split.json.gz")[split];pairs={(z["q"],z["t"]) for z in ids}
    ix=f.gmod.graph_index();dev=Path("D:/CodexResearch/x20-native-multiseed/official580/dev")
    if split=="dev":
        for t,s in load(OFF/"dev-graphs.json").items():ix[t]=(dev/(t+".json.gz"),s["graph_file"])
    out=[]
    for i,src in enumerate(paths):
        by=defaultdict(list)
        for r in load(src):by[r["t"]].append(r)
        for t,group in by.items():
            if split=="dev":
                rec=load(dev/(t+".json.gz"));questions=dict(rec["q"])
                pool=[v.model_dump(mode="json") for v in pilot.native.provenance_unit_candidates(f.gmod.ProvenanceGraph.model_validate(rec["g"]))]
            else:
                rec=load(hist.CACHE/"projection"/f"{i}-{t}.json.gz");questions=dict(rec["q"]);pool=rec["pool"]
            pp=prior(pool,f.gmod.project(t,ix))
            for r in group:out.append(make(r["q"],t,r["rr"],questions[r["q"]],pp))
        print("prepared",split,i,len(out),flush=True)
    assert len(pairs)==len(out) and {(r["q"],r["t"]) for r in out}==pairs
    dst=PRIVATE/(split+".json.gz");write(dst,out)
    write(D/(split+"-inputs.json"),{"n":len(out),"t":len({v["t"] for v in out}),"rows":sum(len(v["p"]) for v in out),"file":sha(dst),"parents":{p.name:sha(p) for p in paths},"code":sha(Path(__file__))})
if __name__=="__main__":
    if sys.argv[1]=="train":train()
    else:prepare(sys.argv[1])