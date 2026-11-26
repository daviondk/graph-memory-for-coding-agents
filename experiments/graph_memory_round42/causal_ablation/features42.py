"""Physically rebuild native prefix graphs for train and test. No test label loader."""
import os
for key in ("OMP_NUM_THREADS","OPENBLAS_NUM_THREADS","MKL_NUM_THREADS","RAYON_NUM_THREADS"):os.environ[key]="1"
os.environ["CUDA_VISIBLE_DEVICES"]="-1"
import sys,importlib.util,hashlib
from collections import Counter,defaultdict
from time import monotonic
from core42 import D,W,R41,CAUSAL,OFF,SEEDS,read,save,signed,sha
sys.path.insert(0,str(R41))
import native
api=native.api
sys.path.insert(0,str(W/"graph_memory_round21/factorized_provenance"))
from operators import packed_stats
spec=importlib.util.spec_from_file_location("r42_geometry",W/"graph_memory_round21/factorized_provenance/study.py")
packed=importlib.util.module_from_spec(spec);spec.loader.exec_module(packed)
from scipy.stats import rankdata
import numpy as np


def auxiliary(graph,tr,step,t):
    ids,g=packed.geometry({"g":graph})
    names=list(ids)
    src={n.node_id:n for n in graph.nodes if n.node_id in ids}
    calls=[e for e in tr.events[:step+1] if e.event_type=="tool_call"]
    sequence={e.call_id:i for i,e in enumerate(calls)}
    freq=Counter(e.tool_name for e in calls)
    counts=Counter((int(n.kind=="content.tool_output"),n.attributes["call_id"]) for n in src.values())
    meta=[]
    for name in names:
        n=src[name]; m=n.attributes
        role=int(n.kind=="content.tool_output");call=m["call_id"];size=counts[role,call];k=m["chunk_index"]
        pos=sequence[call]
        meta.append([role,np.log1p(m["token_count"]),np.log1p(k),k/max(1,size-1),int(k==0),int(k==size-1),np.log1p(size),
            pos/max(1,len(calls)-1),np.log1p(pos),np.log1p(len(calls)-1-pos),np.log1p(counts[0,call]),
            np.log1p(counts[1,call]),np.log1p(freq[m["tool_name"]]),np.log1p(len(calls)),np.log1p(len(names))])
    meta=np.array(meta)
    deg=np.log1p(packed_stats(g,np.zeros(len(names)))[:,:,0])
    rel=np.empty(deg.shape)
    ix=np.arange(len(names))
    perm=ix.copy()
    for role in [0,1]:
        gix=ix[meta[:,0]==role]
        if not len(gix):continue
        rel[gix]=(rankdata(deg[gix],axis=0,method="average")-.5)/len(gix)-.5
        shuffled=sorted(gix,key=lambda i:hashlib.sha256(("ablation42|"+t+"|"+names[i]).encode()).digest())
        perm[shuffled]=np.roll(shuffled,max(1,len(gix)//2))
    graphf=np.column_stack([deg,rel])
    assert sorted(perm)==list(ix)
    return names,src,meta,graphf,graphf[perm]


def run(shards):
    registration=read(D/"registration.json")
    assert sha(D/"PROTOCOL_RU.md")==registration["protocol"]
    nd=api.pilot
    api.torch.set_num_threads(1);api.torch.set_num_interop_threads(1)
    assert not api.torch.cuda.is_available()
    split=read(OFF/"split.json.gz");by=defaultdict(list);stage={}
    for st in ("train","test"):
        for r in split[st]:
            by[r["t"]].append(r["q"])
            assert stage.setdefault(r["t"],st)==st
    wanted={q for qs in by.values() for q in qs}
    queries={r["id"]:r["query"] for _,r in nd.stream(nd.Q) if r["id"] in wanted}
    token=nd.offsets(nd.Tokenizer.from_file(str(nd.CACHE/"tokenizer.json")))
    def chunk(text):
        return nd.token_chunks(text,tokenizer=token,max_tokens=504,overlap_tokens=64)
    lookup={}
    for seed in SEEDS:
        c,_=api.connect(seed)
        for _,name,_ in c.execute("pragma database_list").fetchall():
            if name!="temp" and name.isidentifier():c.execute(f"pragma {name}.mmap_size=3000000000")
        lookup[seed]=native.RepeatedLookup(api.fit.Lookup(c,"ft"))
    opts=dict(batch_size=64,normalize_embeddings=True,show_progress_bar=False)
    graph_coef=read(W/"graph_memory_round33/relative_structure/weights.json")["models"]["global_role"]
    for sh in shards:
        start=monotonic()
        seal_file=D/f"features-{sh}-seal.json"
        if seal_file.exists():
            assert read(seal_file)["code"]==sha(D/"features42.py")
            continue
        signed_graphs={t:dig for t,cut,step,nn,ne,dig in read(R41/f"forecast-{sh}-seal.json")["traces"] if cut==50}
        prior={q:(avail,np.array(logits)) for q,t,cut,step,avail,logits,p in read(CAUSAL/f"state-{sh}.json.gz") if cut==50}
        saved=read(api.TR/f"forecasts-main-{sh}.json.gz")
        index={r["q"]:{v["node_id"]:j for j,v in enumerate(r["rr"])} for r in saved}
        ranks={s:{r["q"]:r["dense"] for r in read(W/f"graph_memory_round21/five_seed/seed-{s}/picks-{sh}.json.gz")} for s in SEEDS if s!=13}
        rows={"train":[],"test":[]};arrays={"train":defaultdict(list),"test":defaultdict(list)};counts=Counter()
        path=api.RAW/f"trajectories-{sh:05d}.jsonl"
        assert sha(path)==read(R41/f"forecast-{sh}-seal.json")["source"]
        for _,obj in nd.stream(path):
            t=obj["session_id"]
            if t not in stage:continue
            st=stage[t];tr=native.adapt_isetrace_record(native.parse_isetrace_record(obj),source_revision=nd.RAW[1]);step,_=native.midstep(tr)
            graph=native.prefix_graph(tr,step,chunk)
            if st=="test":
                assert graph.fingerprint()==signed_graphs[t]
            names,src,meta,edge,sham=auxiliary(graph,tr,step,t)
            if st=="train":
                public=read(api.TRAINED/"projection/train"/(t+".json.gz"))
                labels={z["q"]:set(z["positive"]) for z in public["qs"]}
            qs=by[t]; sims={}
            for s in (SEEDS if st=="test" else (13,)):
                passage=lookup[s].encode(["passage: "+src[n].text for n in names],**opts)
                query=lookup[s].encode(["query: "+queries[q] for q in qs],**opts)
                sims[s]=(query@passage.T).astype(float)
            for qi,q in enumerate(qs):
                n=len(names); local=np.arange(n)
                a=arrays[st]
                for k,v in [("meta",meta),("edge",edge),("sham",sham)]:a[k].append(v)
                if st=="train":
                    assert q in labels
                    y=np.asarray([k in labels[q] for k in names],dtype=np.uint8)
                    a["labels"].append(y)
                    ext=local
                else:
                    ext=np.asarray([index[q][k] for k in names],dtype=int)
                    avail,logit=prior[q]
                    assert set(ext)==set(avail)
                    aligned={v:i for i,v in enumerate(ext)}
                    gx=np.column_stack([meta[:,:7],edge])
                    pred=gx@graph_coef["coef"]+graph_coef["intercept"]
                    assert np.max(np.abs(pred[[aligned[v] for v in avail]]-logit))<1e-10
                for s in (SEEDS if st=="test" else (13,)):
                    sim=sims[s][qi];sim_order=np.argsort(-sim,kind="stable")
                    if st=="test":
                        expected_order=(sorted(ext) if s==13 else [v for v in ranks[s][q] if v in aligned])
                        order=np.asarray([aligned[v] for v in expected_order],dtype=int)
                        counts["semantic_orders"]+=1
                        counts["semantic_top1_same"]+=int(sim_order[0]==order[0])
                        counts["semantic_order_same"]+=int(np.array_equal(order,sim_order))
                    else:order=sim_order
                    rank=np.empty(n);rank[order]=np.arange(1,n+1)
                    a[f"sem{s}"].append(np.column_stack([np.log1p(rank),1/rank,(n-rank)/max(1,n-1),sim]))
                rows[st].append([q,t,n,ext.tolist() if st=="test" else None])
                counts[st+"_questions"]+=1
            counts[st+"_trajectories"]+=1
        hashes={}
        for st in rows:
            rp=D/f"{st}-{sh}.json.gz";save(rp,rows[st])
            table=D/f"{st}-{sh}.npz";np.savez_compressed(table,**{k:np.concatenate(v) for k,v in arrays[st].items()})
            hashes[st]=[sha(rp),sha(table)]
        save(seal_file,dict(code=sha(D/"features42.py"),registration=sha(D/"registration.json"),counts=counts,rows=hashes,seconds=monotonic()-start))
        print("projected",sh,dict(counts),round(monotonic()-start,1),flush=True)


if __name__=="__main__":
    run([int(s) for s in sys.argv[1:]] or range(8))
