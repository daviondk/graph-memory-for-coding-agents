from compare import D,W,N,T,S,ARMS,SEEDS,load,put,sha,np
def main():
    fn=D/"outcomes.json.gz";r=load(fn);st=load(D/"results.json");assert sha(fn)==st["rows"]
    cache=W/"graph_memory_round34/interval_witness";atoms=load(cache/"test-atoms.json.gz");assert sha(cache/"test-atoms.json.gz")==load(cache/"test-geometry.json")["atoms"]
    from pathlib import Path
    cf=Path("D:/CodexResearch/x20-r33-budget-loss/test.json.gz");assert sha(cf)==load(W/"graph_memory_round33/budget_loss/test-input.json")["features"]
    costs={c["q"]:np.asarray(c["c"]) for c in load(cf)};new13=load(S/"test-orders.json.gz");checked=0;sw={str(s):{a:[0,0] for a in ARMS} for s in SEEDS}
    for shard in range(8):
        new17=load(T/f"orders-{shard}.json.gz");ords={}
        for seed in SEEDS:
            for method in ARMS:
                base=N/f"seed-{seed}"/method;receipt=load(base/"forecast-seal.json")["receipts"][shard];file=base/receipt["file"]
                assert sha(file)==receipt["sha"];ords[str(seed),method]={v["q"]:v["graph"] for v in load(file)}
        for q in new17:
            gold=atoms[q];lng=np.array([b-a for _,a,b,_ in gold]);c=costs[q]
            for seed in SEEDS:
                s=str(seed);pred=r[q]["seeds"][s]
                for arm in ("oof_3894",*ARMS):
                    ix=np.asarray((new13[q]["oof_3894"] if seed==13 else new17[q]["17"]["oof_3894"]) if arm=="oof_3894" else ords[s,arm][q]);rank=np.argsort(ix);spent=c[ix].cumsum()
                    covered=np.array([min(spent[rank[i]] for i in group)<=2048 for *_,group in gold])
                    assert np.allclose(pred[arm],[covered.all(),lng[covered].sum()/lng.sum()],rtol=0,atol=1e-12);checked+=1
                for a in ARMS:
                    z=sw[s][a];z[0]+=pred["oof_3894"][0]>pred[a][0];z[1]+=pred["oof_3894"][0]<pred[a][0]
    assert checked==12000
    for s,arms in sw.items():
        for a,v in arms.items():
            z=st["groups"][s]["comparisons"][a];assert v==[z["win_query_seed"][0],z["loss_query_seed"][0]]
    put(D/"audit.json",dict(orders_checked=checked,metrics_checked=checked*2,independent_span_sweep="atoms with cumsum of original token costs",switches=sw,results=sha(D/"results.json")));print("verified",checked)
if __name__=="__main__":main()