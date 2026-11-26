"""Call each real reader from a compressed graph and read-only local embedding store."""
from reader import *
def main():
    core=pin(); p=get(HERE/"plan.json")["panel"][:24]; common=graphfiles();con,_=of.connect(13);lookup=of.fit.Lookup(con,"ft")
    models={m:net(m)[:2] for m in ARMS[2:]};params=get(HERE/"linear-model.json");reference=get(HERE/"replay.json.gz")
    rng=random.Random(3424);times=[]
    with torch.inference_mode():
        for q,t in p:
            path,_=common[t]
            for rep in range(3):
                sequence=list(ARMS);rng.shuffle(sequence)
                for pos,m in enumerate(sequence):
                    st=tick()
                    reqs,_=tree(path,t,[q]);pv,_,_=common_vectors(reqs,lookup);req=reqs[0];ids,cost,nodepos=fixed(req)
                    if m in ARMS[2:]:
                        mod,cfg=models[m];b=batch(req,pv,cfg);keys={k:i for i,k in enumerate(b.sample_node_ids)}
                        out=native(b,mod,ids,cost,np.array([keys[k] for k in ids]))
                    else:
                        static=compile_struct(req,params) if m=="cost" else None
                        out=simple(cos(pv.tasks[q].values.numpy(),nodepos),ids,cost,static)
                    elapsed=tick()-st
                    assert hashlib.sha256(json.dumps(out[0]).encode()).hexdigest()==reference[q]["arms"][m]["order_sha"]
                    times.append([t,q,rep,pos,m,elapsed])
    save(HERE/"file-times.json.gz",times);print(len(times))
if __name__=="__main__":main()
