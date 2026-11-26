"""Confirm fixed structural models on four additional seed-specific Dense-FT rankings."""
from study import ROOT,WORK,R19,f,nm,sha,load,save,relative,design,paired,np,ProcessPoolExecutor,defaultdict
SRC=WORK/"graph_memory_round21/five_seed"
SEEDS=(17,29,37,41)
ARMS=("global","global_role","global_trajectory")
METRICS=("full_support_2048","coverage_512","coverage_1024","coverage_2048","recall_5","mrr")
def make(i):
    upstream=f.app.rd.source("dense",i);base=load(upstream);group=defaultdict(list);index=f.gmod.graph_index()
    prev={};cal={};models=load(ROOT/"weights.json")["models"]
    for s in SEEDS:
        src=SRC/f"seed-{s}";file=src/f"picks-{i}.json.gz";lock=load(src/"forecast-seal.json");h=next(r for r in lock["receipts"] if r["file"]==file.name)
        assert sha(file)==h["sha"] and h["source"]==sha(upstream) and lock["rank_weights"]==sha(src/"calibration.json")
        prev[s]={r["q"]:r for r in load(file)};cal[s]=load(src/"calibration.json")["rank"]
    for q in base:group[q["t"]].append(q)
    out=[]
    for t,qs in group.items():
        raw=load(f.app.rd.stream.CACHE/f"{i}-{t}.json.gz");ids,x=f.shape(raw["pool"],f.gmod.project(t,index))
        tr=relative(x,False);role=relative(x,True);at={k:j for j,k in enumerate(ids)}
        pri={m:f.lin(models[m],design(x,m,tr,role)) for m in ARMS}
        for q in qs:
            name=q["q"];node=np.array([at[k["node_id"]] for k in q["rr"]]);record={}
            for s in SEEDS:
                old=prev[s][name];dx=np.array(old["dense"]);assert old["t"]==t and sorted(dx.tolist())==list(range(len(dx)))
                signal=f.lin(cal[s],f.rank_x(len(dx)));z=node[dx];scores={m:dx[np.argsort(-(signal+p[z]),kind="stable")].tolist() for m,p in pri.items()}
                assert scores["global"]==old["factor"]
                record[str(s)]={m:scores[m] for m in ARMS if m!="global"}
            out.append({"q":name,"t":t,"orders":record})
    path=ROOT/f"rep-ranks-{i}.json.gz";save(path,out);return path.name,sha(path)

def measure(i):
    parents={r["q"]:r for r in load(f.app.rd.source("dense",i))};gold=load(nm.OFF/"gold-spans.json.gz");out={}
    for r in load(ROOT/f"rep-ranks-{i}.json.gz"):
        q=r["q"];nodes=[nm.pilot.RankedNodeRecord.model_validate(v) for v in parents[q]["rr"]]
        refs=tuple(nm.pilot.SourceSpan.model_validate(v) for v in gold[q]);record={}
        for s,arms in r["orders"].items():
            record[s]={}
            for a,order in arms.items():
                ranked=tuple(nodes[j] for j in order)
                vals=[nm.pilot.span_metrics_under_token_budget(ranked,refs,b) for b in (512,1024,2048)]
                record[s][a]=[vals[2].full_support,*[v.coverage for v in vals],nm.span_metrics_at(ranked,refs,5).coverage,nm.span_mrr(ranked,refs)]
        out[q]={"t":r["t"],"seeds":record}
    path=ROOT/f"rep-outcomes-{i}.json.gz";save(path,out);return path.name,sha(path)

def main():
    with ProcessPoolExecutor(2) as p:hashes=dict(p.map(make,range(8)))
    save(ROOT/"rep-seal.json",{"protocol":sha(ROOT/"SEEDS_RU.md"),"code":sha(ROOT/"seeds.py"),"ranks":hashes,"weights":sha(ROOT/"weights.json")})
    print("four additional seed ranks sealed",flush=True)
    with ProcessPoolExecutor(2) as p:outcomes=dict(p.map(measure,range(8)))
    rows={}
    for path,h in outcomes.items():assert sha(ROOT/path)==h;rows.update(load(ROOT/path))
    assert len(rows)==2000
    for s in SEEDS:
        src=SRC/f"seed-{s}";path=src/"metrics.json.gz";assert sha(path)==load(src/"results.json")["q_sha"];ref=load(path)
        for q,r in rows.items():
            for target,name in (("factor","global"),("dense","dense")):
                original=ref[target][q];assert original["t"]==r["t"];r["seeds"][str(s)][name]=[original[k] for k in METRICS]
    for i in range(8):
        for q,v in load(ROOT/f"outcomes-{i}.json.gz").items():rows[q]["seeds"]["13"]={m:v["arms"][m] for m in ("dense",*ARMS)}
    result={}
    for label,seeds in [(str(s),[s]) for s in (13,*SEEDS)]+[("extra4",SEEDS),("all5",(13,*SEEDS))]:
        av={q:{"t":r["t"],"arms":{m:np.mean([r["seeds"][str(s)][m] for s in seeds],axis=0).tolist() for m in ("dense",*ARMS)}} for q,r in rows.items()}
        result[label]={"mean":{m:np.mean([r["arms"][m] for r in av.values()],axis=0).tolist() for m in ("dense",*ARMS)},
                       "vs_global":{m:paired(av,m) for m in ARMS if m!="global"}}
    save(ROOT/"rep-results.json",{"outcomes":outcomes,"aggregate":result,"nq":len(rows),"seeds":[13,*SEEDS],"seal":sha(ROOT/"rep-seal.json")})
if __name__=="__main__":main()
