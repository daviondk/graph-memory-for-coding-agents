"""Describe every CPU-versus-sealed ranking discrepancy on the fixed panel."""
from reader import *
def main():
    pin();checks=get(HERE/"replay.json.gz");need={q:r for q,r in checks.items() if any(not x["same_order"] for x in r["arms"].values())}
    raw,exp=references(set(need));by=defaultdict(list)
    for q,r in need.items():by[r["t"]].append(q)
    paths=graphfiles();con,_=of.connect(13);lookup=of.fit.Lookup(con,"ft");nets={m:net(m)[:2] for m in ARMS[2:]}
    out={};params=get(HERE/"linear-model.json")
    with torch.inference_mode():
        for t,qs in by.items():
            reqs,_=tree(paths[t][0],t,qs);pv,_,_=common_vectors(reqs,lookup);static=compile_struct(reqs[0],params);bias,rv,_=static
            for req in reqs:
                q=req.task_id;ids,cost,nodepos=fixed(req);indices={k:i for i,k in enumerate(ids)}
                sem=cos(pv.tasks[q].values.numpy(),nodepos);sd=np.argsort(-sem,kind="stable")
                v=np.empty(len(ids));v[sd]=bias[sd]+rv; sc={"dense":sem,"cost":v}
                for arm,(net1,cfg) in nets.items():
                    b=batch(req,pv,cfg);idx={k:i for i,k in enumerate(b.sample_node_ids)}
                    sc[arm]=net1(b).detach().numpy()[[idx[k] for k in ids]]
                out[q]={}
                for arm,s in sc.items():
                    order=sd[np.argsort(-s[sd],kind="stable")] if arm=="cost" else np.argsort(-s,kind="stable")
                    CPU=finish(order,ids,cost);target=exp[q][arm];reference=finish([indices[k] for k in target],ids,cost)
                    assert hashlib.sha256(json.dumps(CPU[0]).encode()).hexdigest()==checks[q]["arms"][arm]["order_sha"]
                    rev={k:i for i,k in enumerate(CPU[0])}
                    inversions=[abs(float(s[indices[a]]-s[indices[b]])) for i,a in enumerate(target) for b in target[i+1:] if rev[a]>rev[b]]
                    orig_dense=np.array([indices[k] for k in exp[q]["dense"]]); alt=orig_dense[np.argsort(-(bias[orig_dense]+rv),kind="stable")]; using_reference_dense=[ids[i] for i in alt]==exp[q]["cost"]
                    out[q][arm]={"with_reference_dense_reconstructs_cost":using_reference_dense,"inversions":len(inversions),"max_cpu_score_margin":max(inversions,default=0),"max_rank_displacement":max(abs(i-rev[k]) for i,k in enumerate(target)),
                        "prefix_same_set":set(CPU[1])==set(reference[1]),"prefix_symmetric_difference":len(set(CPU[1])^set(reference[1]))}
    save(HERE/"replay-differences.json",out);print("questions",len(out))
if __name__=="__main__":main()
