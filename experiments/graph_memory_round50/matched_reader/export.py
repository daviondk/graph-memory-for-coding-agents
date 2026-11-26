"""Build minimal numerical input projections with no gold labels. Store source digests and forecasts."""
import sys
import os
from common import D,W,SEEDS,sha,read,put
R40=W/"graph_memory_round40/cost_quality"
R43=W/"graph_memory_round43/metric_matched"
R39=W/"graph_memory_round39/hybrid_controls"
sys.path.insert(0,str(R40))
import inputs
import shutil

def main():
    assert sha(D/"PROTOCOL_RU.md")=="8127a24dc5fe7119490ef3d6831d41fd62de88e5c2a2dacfa5be559d28105a11"
    raw=inputs.pool_source()
    # Keep paths, numeric features, costs and offsets only. No annotated study outcomes.
    put(D/"pool.json.gz",{q:{k:r[k] for k in ("t","x","o","c")} for q,r in raw.items()})
    mapping={}
    maps={}
    for sh in range(8):
        p=W/f"graph_memory_round19/trained_rank/forecasts-main-{sh}.json.gz"
        maps[p.name]=sha(p)
        for r in read(p):mapping[r["q"]]={u["node_id"]:i for i,u in enumerate(r["rr"])}
    assert set(raw)==set(mapping) and len(raw)==2000
    sources={"mapping":maps,"pool":sha(inputs.FEATURES),"model":sha(R40/"model.json.gz"),"seeds":{}}
    private=Path(os.environ.get("R50_CHECKPOINT_RANKS",str(W.parents[1]/"x20-r34-dev-metric")))
    for seed in SEEDS:
        metrics=read(R43/f"forecast-{seed}.json")
        private_rank=private/f"seed-{seed}/wo_chunk_adjacency/test-ranks.json.gz"
        assert sha(private_rank)==metrics["checkpoints"]["wo_chunk_adjacency"]["ranks"]
        devr=read(private_rank)
        native={}
        for q,t,p in inputs.cases(seed,raw):
            other=[mapping[q][x] for x in devr[q]];assert sorted(other)==list(range(len(p["costs"])))
            native[q]=[p["dense"],p["order"],other]
        put(D/f"ranks-{seed}.json.gz",native)
        r39=read(R39/f"test-{seed}-seal.json");d39=R39/f"test-{seed}-packets.json.gz"
        d43=R43/f"packets-{seed}.json.gz"
        assert sha(d39)==r39["packets"] and sha(d43)==metrics["data"]
        assert r39["orders"][1]=="wo_chunk_adjacency" and r39["budgets"][3]==2048
        orig,dev=read(d39),read(d43);arch={}
        for q in native:
            a=orig[q][1][1][3];b=dev[q][1];assert orig[q][0]==dev[q][0]==raw[q]["t"]
            arch[q]=[[a[r39["rules"].index(k)] for k in ("graph_dp","firstfit","graph_value")],
                     [b["wo_chunk_adjacency/"+k] for k in ("dp","firstfit","value")]]
        put(D/f"archive-{seed}.json.gz",arch)
        sources["seeds"][seed]={"recall_forecast":sha(d39),"dev_forecast":sha(d43),"dev_rank":sha(private_rank),"selected_checkpoint":metrics["checkpoints"]["wo_chunk_adjacency"]}
        print("export",seed,flush=True)
    put(D/"input_sources.json",sources)
if __name__=="__main__":
    from pathlib import Path
    main()

