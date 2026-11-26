"""Compare same candidate IDs and annotated span budgets against local R-GCN scores."""
from study import *
from seeds import METRICS
UP=WORK/"graph_memory_round22/native_multiseed";ARMS=("full_rgcn","wo_chunk_adjacency")
def contrast(rows,baseline):
    paired_rows={q:{"t":r["t"],"arms":{"global":r["arms"][baseline],"global_role":r["arms"]["global_role"]}} for q,r in rows.items()}
    return paired(paired_rows,"global_role")

def report(rows):
    arms=next(iter(rows.values()))["arms"]
    return {"n":len(rows),"means":{m:np.mean([r["arms"][m] for r in rows.values()],axis=0).tolist() for m in arms},
            "vs_graph":{m:contrast(rows,m) for m in arms if "rgcn" in m or "adjacency" in m}}

def test():
    rows={};refs={}
    for i in range(8):
        rows.update(load(ROOT/f"outcomes-{i}.json.gz"));refs.update({r["q"]:r for r in load(f.app.rd.source("dense",i))})
    checks={}
    for which,where in (("dev580",UP/"official580"),("dev500",UP)):
        for a in ARMS:
            p=where/"seed-13"/a;lock=load(p/"results.json");assert lock["metrics"]==sha(p/"metrics.json.gz") and lock["forecast"]==sha(p/"forecast-seal.json")
            seal=load(p/"forecast-seal.json");checks[which+"/"+a]=lock["forecast"]
            stats=load(p/"metrics.json.gz")["graph"];assert set(rows)==set(stats)
            n=0
            for h in seal["receipts"]:
                file=p/h["file"];assert sha(file)==h["sha"]
                for r in load(file):
                    q=r["q"];assert r["t"]==rows[q]["t"]==refs[q]["t"] and sorted(r["graph"])==list(range(len(refs[q]["rr"])))
                    v=stats[q];rows[q]["arms"][which+"/"+a]=[v[k] for k in METRICS];n+=1
            assert n==len(rows)
    save(ROOT/"rgcn-test-results.json",{"comparison":report(rows),"sources":checks})
def dev():
    seal=load(ROOT/"rgcn-dev-seal.json");rows=load(ROOT/"dev500-outcomes.json.gz");by={r["q"]:r for r in load(f.app.rd.source("dev",0))};refs=load(R19/"write_transfer/gold-spans.json.gz")
    for a in ARMS:
        p=ROOT/(a+"-dev500-ranks.json.gz");assert sha(p)==seal["ranks"][a];order=load(p);assert rows.keys()==order.keys()
        for q,ix in order.items():
            r=by[q];nodes=[nm.pilot.RankedNodeRecord.model_validate(v) for v in r["rr"]];gold=tuple(nm.pilot.SourceSpan.model_validate(v) for v in refs[q])
            assert sorted(ix)==list(range(len(nodes)))
            v=nm.points(tuple(nodes[j] for j in ix),gold)
            rows[q]["arms"][a]=[v[k] for k in METRICS]
    save(ROOT/"rgcn-dev500-outcomes.json.gz",{q:{"t":r["t"],"arms":{a:r["arms"][a] for a in ARMS}} for q,r in rows.items()})
    save(ROOT/"rgcn-dev500-results.json",{"comparison":report(rows),"seal":sha(ROOT/"rgcn-dev-seal.json")})
if __name__=="__main__":{"test":test,"dev":dev}[sys.argv[1]]()
