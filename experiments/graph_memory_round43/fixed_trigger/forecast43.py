"""Run frozen readers on the observed eight-group prefix, before any gold is opened."""
import os
for k in ("OPENBLAS_NUM_THREADS","OMP_NUM_THREADS","MKL_NUM_THREADS","RAYON_NUM_THREADS"):os.environ[k]="1"
os.environ["CUDA_VISIBLE_DEVICES"]="-1"
from collections import defaultdict,Counter
from time import monotonic
import sys
from io43 import D,W,R41,R42,OFF,SEEDS,ARMS,read,save,sha,signed
from trigger43 import cut,record
sys.path.insert(0,str(R42))
import features42 as f
import models42 as mdl
from core42 import firstfit
from graph_memory.graphs.provenance import build_provenance_graph
import numpy as np
api=f.api


def get_models():
    frozen=signed(R42/"models.json")["models"]
    graph_weights=read(W/"graph_memory_round33/relative_structure/weights.json")["models"]["global_role"]
    budget_weights=read(W/"graph_memory_round35/calibration_scale/models.json")["models"]["oof_3894"]
    ranks={s:(read(W/"graph_memory_round20/factor_reader/hash64-weights.json")["rank"] if s==13 else
        read(W/f"graph_memory_round21/five_seed/seed-{s}/calibration.json")["rank"]) for s in SEEDS}
    models={}
    for s in SEEDS:
        db,lookup,nets=f.native.native_inputs(s)
        models[s]=(db,lookup,*nets["wo_chunk_adjacency"])
    return frozen,graph_weights,budget_weights,ranks,models


def embeddings_and_native(graph,qs,names,models):
    pool=tuple(api.pilot.native.provenance_unit_candidates(graph))
    requests=[api.ExecutionProvenanceRankingRequest(task_id=q,query_text=txt,candidates=pool,graph=graph) for q,txt in qs.items()]
    n=len(graph.nodes);slots={node.node_id:i for i,node in enumerate(graph.nodes)}
    extract=np.array([slots[k] for k in names]);local={name:i for i,name in enumerate(names)}
    rng={q:{} for q in qs};h={q:{} for q in qs}
    for seed,(_,lookup,cfg,net) in models.items():
        storage=np.empty((len(qs)*(n+1),768),dtype=np.float32)
        provider,used=api.fit.features(requests,lookup,storage,0)
        assert used==len(storage)
        score=storage[n::n+1]@storage[extract].T
        for j,q in enumerate(qs):
            sim=score[j].astype(float)
            order=np.argsort(-sim,kind="stable")
            rank=np.empty(len(names));rank[order]=np.arange(1,len(names)+1)
            rng[q][seed]=np.column_stack([np.log1p(rank),1/rank,(len(names)-rank)/max(1,len(names)-1),sim])
        tasks=[api.fit.tensorize_provenance_ranking_task(req,model_config=cfg,text_embedding_provider=provider,seed_signal_provider=provider) for req in requests]
        with api.torch.inference_mode():
            for batch in api.inf.build_evidence_dataloader(tasks,per_device_graph_batch_size=128,shuffle=False,random_seed=seed):
                assert batch.sample_node_features.device.type=="cpu"
                logits=net(batch)
                assert api.torch.isfinite(logits).all()
                for q,ranked in api.old.orders(batch,logits).items():
                    h[q][seed]=[local[k] for k in ranked]
                    assert sorted(h[q][seed])==list(range(len(names)))
    return rng,h


def run(shards):
    api.torch.set_num_threads(2);api.torch.set_num_interop_threads(1);assert not api.torch.cuda.is_available()
    registration=read(D/"registration.json");assert sha(D/"PROTOCOL_RU.md")==registration["protocol"]
    frozen,gmodel,bmodel,rmodels,nets=get_models()
    by=defaultdict(list)
    for r in read(OFF/"split.json.gz")["test"]:by[r["t"]].append(r["q"])
    wanted={q for qs in by.values() for q in qs}
    sdk=api.pilot
    qt={r["id"]:r["query"] for _,r in sdk.stream(sdk.Q) if r["id"] in wanted}
    tok=sdk.offsets(sdk.Tokenizer.from_file(str(sdk.CACHE/"tokenizer.json")))
    def chunk(src):return sdk.token_chunks(src,tokenizer=tok,max_tokens=504,overlap_tokens=64)
    for sh in shards:
        start=monotonic()
        seal=D/f"forecast-{sh}-seal.json";packets=D/f"packets-{sh}.json.gz";traces=D/f"traces-{sh}.json.gz"
        if seal.exists():
            assert read(seal)["packets"]==sha(packets) and read(seal)["traces"]==sha(traces)
            continue
        rawpath=api.RAW/f"trajectories-{sh:05d}.jsonl"
        assert sha(rawpath)==read(R41/f"forecast-{sh}-seal.json")["source"]
        records=[];trace=[];missing=[];acc=defaultdict(list)
        for _,origin in sdk.stream(rawpath):
            t=origin["session_id"]
            if t not in by:continue
            prefix,n_groups,calls=cut(iter(origin["messages"]))
            if prefix is None:
                missing.extend((q,t) for q in by[t]);trace.append([t,False,n_groups,calls,None,None,None,None]);continue
            tr=f.native.adapt_isetrace_record(f.native.parse_isetrace_record(record(t,prefix,calls)),source_revision=sdk.RAW[1])
            tr=tr.model_copy(update={"source_metadata":None})
            assert len(tr.tool_calls)==calls and tr.events[-1].event_type=="tool_output"
            graph=build_provenance_graph(tr,content_chunker=chunk)
            allowed={e.event_id for e in tr.events}
            assert all(sp.event_id in allowed for v in (*graph.nodes,*graph.edges) for sp in v.source_spans)
            names,_,meta,edge,sham=f.auxiliary(graph,tr,len(tr.events)-1,t)
            qs={q:qt[q] for q in by[t]}
            sem,native=embeddings_and_native(graph,qs,names,nets)
            trace.append([t,True,n_groups,calls,len(prefix),len(tr.events),len(names),graph.fingerprint()])
            for q in qs:
                records.append((q,t,names,native[q]))
                for k,x in (("meta",meta),("edge",edge),("sham",sham)):acc[k].append(x)
                for seed in SEEDS:acc[seed].append(sem[q][seed])
            if len(trace)%50==0:print("progress",sh,len(trace),round(monotonic()-start,1),flush=True)
        # Names are translated into the common external index only after every native forward.
        source=api.TR/f"forecasts-main-{sh}.json.gz"
        assert sha(source)==read(api.TR/"forecast-seal.json")["forecasts"][source.name]
        index={r["q"]:{u["node_id"]:i for i,u in enumerate(r["rr"])} for r in read(source)}
        responses={q:[t,False,[],{}] for q,t in missing}
        if records:
            m,e,sham=(np.vstack(acc[k]) for k in ("meta","edge","sham"))
            c=np.rint(np.expm1(m[:,1])).astype(int)
            gscore=np.column_stack([m[:,:7],e])@gmodel["coef"]+gmodel["intercept"]
            for s in SEEDS:
                sem=np.vstack(acc[s])
                rank=np.rint(np.expm1(sem[:,0])).astype(int)
                scores={name:mdl.portable(frozen[name]["hgb"],mdl.inputs(sem,m,e,sham,name)) for name in ("full","rich","cross","local","sham")}
                z=np.column_stack([sem[:,0],m[:,1],m[:,0],m[:,0]*m[:,1]])
                prior=np.column_stack([-np.log(rank),sem[:,1],sem[:,2]])@rmodels[s]["coef"]+rmodels[s]["intercept"]
                scores["R35"]=gscore+prior+(z-bmodel["center"])/bmodel["scale"]@bmodel["weights"]
                pos=0
                for q,t,names,native in records:
                    n=len(names);sl=slice(pos,pos+n);pos+=n
                    ids=np.asarray([index[q][name] for name in names],dtype=int)
                    orders={name:np.lexsort((rank[sl],-values[sl])) for name,values in scores.items()}
                    orders.update(dense=np.argsort(rank[sl]),native_wo=native[s])
                    output={name:ids[firstfit(order,c[sl])].tolist() for name,order in orders.items()}
                    assert set(output)==set(ARMS)
                    responses.setdefault(q,[t,True,ids.tolist(),{}])[3][str(s)]=output
                assert pos==len(c)
        assert set(index)==set(responses)
        save(packets,responses);save(traces,trace)
        save(seal,dict(packets=sha(packets),traces=sha(traces),source=sha(rawpath),program=sha(D/"forecast43.py"),
            registered=sha(D/"registration.json"),questions=len(responses),fired_questions=len(records),seconds=monotonic()-start))
        print("sealed",sh,len(responses),len(records),round(monotonic()-start,1),flush=True)
    for db,*_ in nets.values():db.close()


if __name__=="__main__":run([int(a) for a in sys.argv[1:]] or range(8))
