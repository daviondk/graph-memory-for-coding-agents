"""Numerical rows for a frozen structural reader and four score corrections."""
from pathlib import Path
import sys,sqlite3
ROOT=Path(__file__).resolve().parent;REL=ROOT.parent/"relative_structure";sys.path.insert(0,str(REL))
from study import f,nm,save,sha,load,np,WORK,R19,R20,OLD,relative,design,defaultdict
from scipy.special import expit,logsumexp
from scipy.optimize import minimize
COHORT=R20/"residual_graph/cpu_fallback/cohorts.json"
OFF=WORK/"graph_memory_round22/native_multiseed/official580"
GRAPH=Path("D:/CodexResearch/x20-native-multiseed/official580/dev")
PRIVATE=Path("D:/CodexResearch/x20-r33-budget-loss");PRIVATE.mkdir(exist_ok=True)
PROJ=Path("D:/CodexResearch/x20-isetrace-trained/projection")
RANK=load(OLD/"hash64-weights.json")["rank"]
MODEL=load(REL/"weights.json")["models"]["global_role"]

def factors(t,pool,idx):
    ids,x=f.shape(pool,f.gmod.project(t,idx));r=relative(x,True)
    logit=f.lin(MODEL,np.column_stack((x,r)))
    return {k:[s,int(round(np.expm1(row[1]))),int(row[0])] for k,s,row in zip(ids,logit,x)}

def record(q,t,ids,pr,positive=None):
    assert len(set(ids))==len(pr) and set(ids)==set(pr)
    a=np.asarray([pr[k] for k in ids])
    cost=a[:,1].astype(int); role=a[:,2]
    assert min(cost)>=0
    x=np.column_stack((np.log1p(np.arange(1,len(cost)+1)),np.log1p(cost),role,role*np.log1p(cost)))
    rec={"q":q,"t":t,"x":x.tolist(),"c":cost.tolist(),"o":(a[:,0]+f.lin(RANK,f.rank_x(len(a)))).tolist()}
    if positive is not None:
        rec["y"]=[j for j,k in enumerate(ids) if k in positive];assert len(rec["y"])==len(positive)
    return rec

def train():
    c=load(COHORT);ts=sorted({t for v in c.values() for t in v["t"]});qset={q for v in c.values() for q in v["q"]}
    assert not set(ts).intersection(t for i in load(OLD/"prior.json")["inventory"] for t in i["t"])
    db=sqlite3.connect(Path("D:/CodexResearch/x20-isetrace-residual/vectors.sqlite3").as_uri()+"?mode=ro",uri=True)
    reader=f.DenseTaskRetriever(encoder=f.Lookup(db,"ft"),device="cpu");ix=f.gmod.graph_index();rows=[]
    previous=load(Path("D:/CodexResearch/x20-r33-conditional/train.json.gz"));old={r["q"]:r["y"] for r in previous}
    for t in ts:
        p=load(PROJ/"train"/(t+".json.gz"));pr=factors(t,p["pool"],ix)
        cs=tuple(f.TextCandidate.model_validate(v) for v in p["pool"])
        for v in p["qs"]:
            ids=[r.node_id for r in reader.rank(f.TextRankingRequest(task_id=v["q"],query_text=v["text"],candidates=cs))]
            rec=record(v["q"],t,ids,pr,set(v["positive"]));assert rec["y"]==old[v["q"]];rows.append(rec)
    db.close();assert {r["q"] for r in rows}==qset and len(rows)==196
    return rows

def sources(stage):
    if stage=="dev":return [f.app.rd.source("dev",0),R20/"untuned_holdout/dense-ranks-extra80.json.gz"]
    return [f.app.rd.source("dense",i) for i in range(8)]

def unseen(stage):
    ix=f.gmod.graph_index()
    if stage=="dev":
        for t,v in load(OFF/"dev-graphs.json").items():ix[t]=(GRAPH/(t+".json.gz"),v["graph_file"])
    rows=[];cert={}
    for i,path in enumerate(sources(stage)):
        if stage=="dev":
            checks=load(REL/("dev500-ranks.json.gz" if i==0 else "ranks-dev.json.gz"))
            cert=checks if i==0 else {r["q"]:r["orders"] for r in checks}
        else:cert={r["q"]:r["orders"] for r in load(REL/f"ranks-{i}.json.gz")}
        by=defaultdict(list)
        for r in load(path):by[r["t"]].append(r)
        for t,group in by.items():
            if stage=="dev":
                g=f.gmod.ProvenanceGraph.model_validate(load(GRAPH/(t+".json.gz"))["g"])
                pool=[v.model_dump(mode="json") for v in nm.pilot.native.provenance_unit_candidates(g)]
            else:pool=load(f.app.rd.stream.CACHE/f"{i}-{t}.json.gz")["pool"]
            pr=factors(t,pool,ix)
            for r in group:
                ids=[v["node_id"] for v in r["rr"]];row=record(r["q"],t,ids,pr)
                assert row["c"]==[k["token_count"] for k in r["rr"]]
                assert np.argsort(-np.asarray(row["o"]),kind="stable").tolist()==cert[r["q"]]["global_role"]
                rows.append(row)
    assert len(rows)==(580 if stage=="dev" else 2000);return rows

def main(stage):
    if stage=="test":assert (ROOT/"selection.json").is_file()
    rows=train() if stage=="train" else unseen(stage);path=PRIVATE/(stage+".json.gz");save(path,rows)
    save(ROOT/(stage+"-input.json"),{"n":len(rows),"t":len({r["t"] for r in rows}),"features":sha(path),"frozen_prior":sha(REL/"weights.json"),"cohort":sha(COHORT),"protocol":sha(ROOT/"PROTOCOL_RU.md"),"code":sha(Path(__file__))})
    print("features",stage,len(rows),flush=True)
if __name__=="__main__":main(sys.argv[1])
