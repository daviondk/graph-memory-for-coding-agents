from reader import ARMS,D,W,read,save,sha,np
from intervals import summarize,SEEDS

def run():
    observations={};qids=None;ts=None;meta={};native_n=0;packet_n=0
    for s in SEEDS:
        prefix=f"test-{s}";stat=read(D/(prefix+"-scores.json"));out=read(D/(prefix+"-outcomes.json.gz"));pred=read(D/(prefix+"-pred.json.gz"))
        assert stat["outcomes"]==sha(D/(prefix+"-outcomes.json.gz"))
        qs=sorted(out);tr=[out[q][0] for q in qs];native_n+=stat["unique_native_checks"];packet_n+=stat["packets"]
        if qids is None:qids=qs;ts=tr
        assert qids==qs and tr==ts
        canonical=W/f"graph_memory_round37/native_five_seeds/canonical-{s}.json.gz"
        legacy=read(canonical)
        for rd,j in [("R35",1),("full_rgcn",3),("wo_chunk_adjacency",4)]:
            for a in ARMS:
                rows=np.array([out[q][1][rd][a] for q in qs])
                if a=="strict":
                    assert np.allclose(rows[:,:2],[[legacy[q][j][0],legacy[q][j][3]] for q in qs],rtol=0,atol=1e-12)
                observations.setdefault(rd+"/"+a,[]).append(rows)
            physical=[pred[q][1][rd] for q in qs]
            meta[f"{s}/{rd}"]=dict(mean_pool=np.mean([v["n"] for v in physical]),mean_eligible=np.mean([v["eligible"] for v in physical]),
                mean_tail_considered=np.mean([v["n"]-len(v["head"]) for v in physical]),strict_inspections=np.mean([min(v["n"],1+len(v["head"])) for v in physical]),
                same_output_firstfit=sum(set(v["extra"]["firstfit"])==set(v["extra"]["reachdp"]) for v in physical))
    mats={k:np.array(v) for k,v in observations.items()};primary="R35/reachdp"
    pairs=[(primary,"R35/"+a) for a in ARMS if a!="reachdp"]
    for rd in ("full_rgcn","wo_chunk_adjacency"):
        pairs.extend([(rd+"/reachdp",rd+"/firstfit"),(primary,rd+"/reachdp"),(primary,rd+"/firstfit"),(primary,rd+"/strict")])
    r=summarize(mats,ts,pairs);r.update(metadata=meta,native_unique=native_n,packets=packet_n,strict_native_crosschecks=30000,code=sha(D/"summary.py"))
    save(D/"results.json",r)
    print([(k,round(v[0]*100,2)) for k,v in r["means"].items()],flush=True)
if __name__=="__main__":run()

