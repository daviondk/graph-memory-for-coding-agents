"""Alternate true CPU readers on an outcome-blind panel; retain each physical timing."""
from reader import *
from machine import memory
def go():
    core=pin();p=get(HERE/"plan.json");assert p["protocol"]==sha(HERE/"PROTOCOL_RU.md")
    by=defaultdict(list)
    for q,t in p["panel"]:by[t].append(q)
    panel={q for q,t in p["panel"]};raw,expected=references(panel)
    gold=get(WORK/"graph_memory_round18/isetrace_official/gold-spans.json.gz")
    files=graphfiles();con,_=of.connect(13);coder=of.fit.Lookup(con,"ft")
    weights={m:net(m) for m in ARMS[2:]};clock=tick();params=get(HERE/"linear-model.json");linear_loading=tick()-clock
    rng=random.Random(3407);rows=[];checks={};setups={};per_t={}
    with torch.inference_mode():
        for t,qs in by.items():
            path,gsha=files[t];assert sha(path)==gsha
            reqs,decode=tree(path,t,qs);provider,lookup,vbytes=common_vectors(reqs,coder)
            st=tick();static=compile_struct(reqs[0],params);comp=tick()-st
            st=tick();ids,cost,nodepos=fixed(reqs[0]);fixed_ns=tick()-st
            per_t[t]={"common_gzip_json_graph_and_requests_ns":decode,"shared_sqlite_and_copy_ns":lookup,"copied_embedding_bytes":vbytes,"graph_gzip_bytes":path.stat().st_size,
                "static_linear_build_ns":comp,"common_id_and_embedding_mapping_ns":fixed_ns,"n":len(ids),"typed_edges":static[2],
                "cached_linear_float_bytes":static[0].nbytes+static[1].nbytes,"budget_count_vector_bytes":cost.nbytes}
            for req in reqs:
                q=req.task_id;mat=provider.tasks[q].values.numpy();tt=tick();sem=cos(mat,nodepos);sem_ns=tick()-tt
                bs={};setup={}
                for m in ARMS[2:]:
                    tt=tick();b=batch(req,provider,weights[m][1]);bn=tick()-tt
                    lookup_ix={k:i for i,k in enumerate(b.sample_node_ids)};perm=np.array([lookup_ix[k] for k in ids])
                    nsem=b.sample_node_features[:,0].detach().numpy()[perm]
                    assert np.allclose(nsem,sem,atol=1e-6,rtol=0)
                    bs[m]=(b,perm);setup[m]={"batch_ns":bn,"tensor_storage_bytes":used_tensor_bytes(b),"semantic_max_abs_diff":float(np.max(np.abs(nsem-sem)))}
                setups[q]={"cosine_ns":sem_ns,"native":setup,"t":t}
                def evaluate(m,mode):
                    if m in ("dense","cost"):
                        scores=sem if mode=="warm" else cos(mat,nodepos)
                        return simple(scores,ids,cost,static if m=="cost" else None)
                    b,perm=bs[m]; neural,cfg,_=weights[m]
                    if mode=="embeddings":b=batch(req,provider,cfg)
                    return native(b,neural,ids,cost,perm)
                verified={};refs=tuple(of.pilot.SourceSpan.model_validate(a) for a in gold[q]);chs={}
                for m in ARMS:
                    out=evaluate(m,"warm");assert out==evaluate(m,"embeddings");verified[m]=out
                    er=expected[q][m];i0={k:i for i,k in enumerate(ids)}
                    ex=finish([i0[k] for k in er],ids,cost)
                    def fs(order):return float(of.pilot.span_metrics_under_token_budget(tuple(raw[q][k] for k in order),refs,2048).full_support)
                    fs1,fs2=fs(out[0]),fs(er)
                    chs[m]={"same_order":out[0]==er,"same_prefix":out[1]==ex[1],"n_diff_ranks":sum(a!=b for a,b in zip(out[0],er)),
                        "fs":fs1,"reference_fs":fs2,"prefix_length":len(out[1]),"order_sha":hashlib.sha256(json.dumps(out[0]).encode()).hexdigest(),"ref_sha":hashlib.sha256(json.dumps(er).encode()).hexdigest()}
                checks[q]={"t":t,"arms":chs}
                for mode,reps in (("warm",8),("embeddings",2)):
                    for rep in range(reps):
                        seq=list(ARMS);rng.shuffle(seq)
                        for pos,m in enumerate(seq):
                            st=tick();out=evaluate(m,mode);ns=tick()-st
                            assert out==verified[m]; rows.append([t,q,mode,rep,pos,m,ns])
    results={"core":core,"cpu":platform.processor(),"python":platform.python_version(),"platform":platform.platform(),"torch":torch.__version__,"numpy":np.__version__,"threads":torch.get_num_threads(),"interop":torch.get_num_interop_threads(),
        "cuda_visible":os.environ["CUDA_VISIBLE_DEVICES"],"linear_load_ns":linear_loading,"linear_bytes":(HERE/"linear-model.json").stat().st_size,"checkpoints":{m:w[2] for m,w in weights.items()},
        "panel":sha(HERE/"plan.json"),"host_process_at_end":memory()}
    save(HERE/"times.json.gz",rows);save(HERE/"replay.json.gz",checks);save(HERE/"setup.json.gz",{"histories":per_t,"queries":setups});save(HERE/"runtime.json",results)
    print(len(rows),{m:sum(r["arms"][m]["same_order"] for r in checks.values()) for m in ARMS},flush=True)
if __name__=="__main__":go()
