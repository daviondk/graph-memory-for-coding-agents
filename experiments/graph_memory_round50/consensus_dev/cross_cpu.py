"""Run the second checkpoint on CPU a second time, saving every differing order for packet sensitivity."""
from native_cpu import *
def main():
    torch.set_num_threads(2);torch.set_num_interop_threads(1)
    key=load(W/"graph_memory_round34/interval_witness/dev-geometry.json")["source"]["candidate_sources"]
    by={}
    for f,sign in key.items():
        path=Path(f);assert sha(path)==sign
        for r in load(path):by[r["q"]]={v["node_id"]:i for i,v in enumerate(r["rr"])}
    glist=load(R22/"dev-graphs.json")
    seq=[r["q"] for r in load(R22/"split.json.gz")["dev"]]
    for seed in map(int,sys.argv[1:] or [13,17,29,37,41]):
        base=W.parents[1]/f"x20-r34-dev-metric/seed-{seed}"/ARM;pick=load(base/"dev-selection.json")
        epoch=pick["selected"]["epoch"];folder=base/pick["attempt"];f=folder/f"epoch-{epoch}.pt";ref=folder/f"ranks-{epoch}.json.gz"
        assert sha(f)==pick["selected"]["weight"] and sha(ref)==pick["selected"]["ranks"]
        arch=load(ref);cp,_,_=n.selection(seed);cfg=n.old.model(seed,ARM,cp)
        model=n.fit.build_model_from_config(cfg);model.load_state_dict(torch.load(f,map_location="cpu",weights_only=True));model.eval()
        con,_=n.connect(seed);lookup=n.fit.Lookup(con,"ft");size=load(R22/"input-inventory.json")["mmap_bytes"]//3072
        mem=np.empty((size,768),np.float32);offset=0;ts={}
        for t in sorted(glist):
            path=n.DEV/(t+".json.gz");assert sha(path)==glist[t]["graph_file"]
            row=load(path);g=n.ProvenanceGraph.model_validate(row["g"]);pool=tuple(n.pilot.native.provenance_unit_candidates(g))
            rr=[n.ExecutionProvenanceRankingRequest(task_id=q,query_text=s,candidates=pool,graph=g) for q,s in row["q"]]
            provider,offset=n.fit.features(rr,lookup,mem,offset)
            for req in rr:ts[req.task_id]=n.fit.tensorize_provenance_ranking_task(req,model_config=cfg,text_embedding_provider=provider,seed_signal_provider=provider)
        con.close();assert offset==size
        delta={}
        with torch.inference_mode():
            for batch in build_evidence_dataloader([ts[q] for q in seq],per_device_graph_batch_size=128,shuffle=False,random_seed=seed):
                rr=n.old.orders(batch,model(batch))
                for q,ids in rr.items():
                    if list(ids)!=arch[q]:
                        delta[q]=[by[q][k] for k in ids]
        store(f"cross-cpu-{seed}.json.gz",delta)
        print("Second checkpoint, CPU rank differences",seed,len(delta),flush=True)
        del ts,mem,model
if __name__=="__main__":main()

