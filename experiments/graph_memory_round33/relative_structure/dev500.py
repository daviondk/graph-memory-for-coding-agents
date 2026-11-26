"""Fixed policies for the 500 development questions outside the R33 selection panel."""
from study import *
ARM=("global","global_role","global_trajectory")
def main():
    src=f.app.rd.source("dev",0);assert sha(src)==load(R20/"residual_graph/dev500-pu-dense-lock.json")["ranks"]
    base=load(src);extra=load(ROOT/"outcomes-dev.json.gz");assert len(base)==500 and not ({r["q"] for r in base}&set(extra))
    index=f.gmod.graph_index();by=defaultdict(list)
    for r in base:by[r["t"]].append(r)
    weights=load(ROOT/"weights.json")["models"];rank=load(OLD/"hash64-weights.json")["rank"];ranks={}
    for t,qs in by.items():
        pool=load(Path("D:/CodexResearch/x20-isetrace-trained/projection/dev")/(t+".json.gz"))["pool"];ids,x=f.shape(pool,f.gmod.project(t,index));at={k:j for j,k in enumerate(ids)}
        tr=relative(x,False);role=relative(x,True);p={m:f.lin(weights[m],design(x,m,tr,role)) for m in ARM}
        for r in qs:
            inds=[at[n["node_id"]] for n in r["rr"]];sig=f.lin(rank,f.rank_x(len(inds)))
            ranks[r["q"]]={m:np.argsort(-(sig+v[inds]),kind="stable").tolist() for m,v in p.items()}
    save(ROOT/"dev500-ranks.json.gz",ranks);save(ROOT/"dev500-seal.json",{"code":sha(Path(__file__)),"protocol":sha(ROOT/"DEV500_RU.md"),"source":sha(src),"weights":sha(ROOT/"weights.json"),"ranks":sha(ROOT/"dev500-ranks.json.gz")})
    refs=load(R19/"write_transfer/gold-spans.json.gz");out={}
    for r in base:
        q=r["q"];nodes=[nm.pilot.RankedNodeRecord.model_validate(v) for v in r["rr"]];gold=tuple(nm.pilot.SourceSpan.model_validate(v) for v in refs[q])
        values={}
        for m,ix in {"dense":range(len(nodes)),**ranks[q]}.items():
            ranked=tuple(nodes[j] for j in ix);metrics=nm.points(ranked,gold);values[m]=[metrics[k] for k in ("full_support_2048","coverage_512","coverage_1024","coverage_2048","recall_5","mrr")]
        out[q]={"t":r["t"],"arms":values}
    save(ROOT/"dev500-outcomes.json.gz",out);result={"n":len(out),"t":len(by),"means":{m:np.mean([r["arms"][m] for r in out.values()],axis=0).tolist() for m in ("dense",*ARM)},
        "vs_global":{m:paired(out,m) for m in ARM[1:]},"seal":sha(ROOT/"dev500-seal.json"),"outcomes":sha(ROOT/"dev500-outcomes.json.gz")}
    save(ROOT/"dev500-results.json",result);print(result["means"],flush=True)
if __name__=="__main__":main()
