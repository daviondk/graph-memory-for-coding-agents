"""Private and resident Windows memory in a clean process serving one method."""
from reader import *
from machine import memory
def go(arm,iteration):
    core=pin();files=graphfiles(); con,_=of.connect(13);coder=of.fit.Lookup(con,"ft");snap={"after_import":memory()};p=get(HERE/"plan.json")
    panel=p["panel"][:8];by=defaultdict(list)
    for q,t in panel:by[t].append(q)
    cases=[]
    for t,qs in by.items():
        path,_=files[t];reqs,_=tree(path,t,qs);provider,_,_=common_vectors(reqs,coder)
        for r in reqs:cases.append((r,provider))
    gc.collect();snap["common_inputs"]=memory()
    model=net(arm) if arm in ARMS[2:] else None;params=get(HERE/"linear-model.json") if arm=="cost" else None
    gc.collect();snap["model_loaded"]=memory();warmed=[]
    with torch.inference_mode():
        for req,provider in cases:
            ids,cost,nodepos=fixed(req);sem=None;b=None;perm=None;static=None
            if model:
                b=batch(req,provider,model[1]);indices={x:j for j,x in enumerate(b.sample_node_ids)};perm=np.array([indices[k] for k in ids])
            else:
                sem=cos(provider.tasks[req.task_id].values.numpy(),nodepos);static=compile_struct(req,params) if params else None
            warmed.append((ids,cost,sem,static,b,perm))
        gc.collect();snap["requests_ready"]=memory();digests={}
        for _ in range(3):
            for (req,_pv),(ids,cost,sem,static,b,perm) in zip(cases,warmed):
                out=native(b,model[0],ids,cost,perm) if model else simple(sem,ids,cost,static)
                digests[req.task_id]=hashlib.sha256(json.dumps(out[0]).encode()).hexdigest()
        gc.collect();snap["served"]=memory()
    save(HERE/f"memory-{arm}-{iteration}.json",{"method":arm,"iteration":iteration,"core":core,"panel":panel,"snapshots":snap,
        "sha":digests,"protocol":sha(HERE/"MEMORY_PROTOCOL_RU.md")})
if __name__=="__main__":go(sys.argv[1],int(sys.argv[2]))
