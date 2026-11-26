"""Post-hoc factorial check at identical penalties and matched R-GCN checkpoints."""
from losses import *
from study import paired
NAMES=("full_support_2048","coverage_512","coverage_1024","coverage_2048","recall_5","mrr")
def compare(rows,first,second):
    return paired({q:{"t":r["t"],"arms":{"global":r["arms"][second],"candidate":r["arms"][first]}} for q,r in rows.items()},"candidate")
def main():
    records=load(PRIVATE/"test.json.gz");models=load(ROOT/"models.json")["models"];ranks={}
    for r in records:
        x=np.array(r["x"]);o=np.array(r["o"]);m={}
        for k,v in models.items():
            s=o+((x-v["center"])/v["scale"])@v["weights"];m[k]=np.argsort(-s,kind="stable").tolist()
        ranks[r["q"]]=m
    save(ROOT/"diagnostic-ranks.json.gz",ranks);save(ROOT/"diagnostic-seal.json",{"source":sha(PRIVATE/"test.json.gz"),"protocol":sha(ROOT/"DIAGNOSTICS_RU.md"),"model":sha(ROOT/"models.json"),"ranks":sha(ROOT/"diagnostic-ranks.json.gz"),"code":sha(Path(__file__))})
    gold=load(nm.OFF/"gold-spans.json.gz");out={}
    for path in sources("test"):
        for r in load(path):
            q=r["q"];nodes=[nm.pilot.RankedNodeRecord.model_validate(v) for v in r["rr"]];refs=tuple(nm.pilot.SourceSpan.model_validate(v) for v in gold[q]);v={}
            for k,ix in ranks[q].items():
                ns=tuple(nodes[j] for j in ix);val=nm.pilot.span_metrics_under_token_budget(ns,refs,2048)
                v[k]=[val.full_support,val.coverage]
            out[q]={"t":r["t"],"arms":v}
    save(ROOT/"diagnostic-outcomes.json.gz",out);tests={}
    for l2 in K:
        for k in FAM[:-1]:
            a=f"cost_worst_{l2}";b=f"{k}_{l2}";tests[a+" vs "+b]=compare(out,a,b)
    means={k:np.mean([r["arms"][k] for r in out.values()],axis=0).tolist() for k in models}
    extra={};which=load(ROOT/"selection.json")["policy"];native=load(ROOT/"test-outcomes.json.gz")
    for config,db in (("dev500",OFF.parent),("dev580",OFF)):
        for a in ("full_rgcn","wo_chunk_adjacency"):
            path=db/"seed-13"/a/"metrics.json.gz";assert load(path.parent/"results.json")["metrics"]==sha(path)
            history=load(path)["graph"];assert set(history)==set(native)
            cells={q:{"t":r["t"],"arms":{"global":[history[q][k] for k in NAMES],"candidate":r["arms"][which]}} for q,r in native.items() if r["t"]==history[q]["t"]}
            assert len(cells)==2000
            extra[config+"/"+a]=paired(cells,"candidate")
    save(ROOT/"diagnostics.json",{"means_fs_cov":means,"matched_penalties":tests,"graph_comparison":extra,"seal":sha(ROOT/"diagnostic-seal.json")})
if __name__=="__main__":main()
