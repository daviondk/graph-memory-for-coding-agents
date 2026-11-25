"""Read out-of-fit questions. Fill a private CPU FP32 embedding cache, then seal picks."""
from pathlib import Path
import sys,sqlite3,hashlib,time,os
for k in ("OPENBLAS_NUM_THREADS","MKL_NUM_THREADS","OMP_NUM_THREADS","RAYON_NUM_THREADS"):os.environ[k]="1"
D=Path(__file__).resolve().parent
import importlib.util
spec=importlib.util.spec_from_file_location("holdout_inventory",D/"inventory.py");inv=importlib.util.module_from_spec(spec);spec.loader.exec_module(inv)
sys.path.insert(0,str(D.parent/"fine_train"));import apply as app
from apply import rd,save,load,sha,pilot,Lookup,DenseTaskRetriever,TextCandidate,TextRankingRequest,np
from graph_memory.graphs.provenance.builder import _argument_chunk_node_id,_output_chunk_node_id
LOCAL=inv.PS/"extra-dev-vectors.sqlite";WD=Path("D:/CodexResearch/x20-isetrace-trained")
def database():
    c=sqlite3.connect(LOCAL.as_uri(),uri=True,timeout=120);c.execute("create table if not exists local(k blob primary key,v blob) without rowid")
    c.execute("attach database ? as gpu",(inv.DB.as_uri()+"?mode=ro",))
    c.execute("create temp view vectors as select k,prec,v from gpu.vectors where prec='ft' union all select k,'ft' as prec,v from main.local")
    return c
def encode():
    import torch
    from graph_memory.embeddings import load_sentence_transformer
    torch.set_num_threads(2);torch.set_num_interop_threads(1)
    model=load_sentence_transformer(str(WD/"model"),device="cpu").eval();c=database()
    files,texts,groups=inv.group();have={k for k, in c.execute("select k from vectors")}
    todo=sorted(((k,s) for k,s in texts.items() if k not in have),key=lambda z:(len(z[1]),z[0]));st=time.perf_counter();tokens=0
    with torch.inference_mode():
        for i in range(0,len(todo),32):
            batch=todo[i:i+32];ss=[s for k,s in batch];vs=model.encode(ss,batch_size=8,normalize_embeddings=True,show_progress_bar=False)
            assert vs.shape==(len(ss),768) and vs.dtype==np.float32 and np.isfinite(vs).all()
            c.executemany("insert into local values(?,?)",[(k,v.astype("<f4",copy=False).tobytes()) for (k,_),v in zip(batch,vs,strict=True)]);c.commit()
            tokens+=sum(model.tokenizer(ss,truncation=True,max_length=model.max_seq_length,return_length=True)["length"])
            if i%256==0:print(i,len(todo),round(time.perf_counter()-st,1),flush=True)
    assert set(texts)<={k for k, in c.execute("select k from vectors")}
    save(D/"encoder-check.json",{"new_this_run":len(todo),"private_inputs":c.execute("select count(*) from local").fetchone()[0],"tokens_this_run":tokens,"elapsed":time.perf_counter()-st,"checkpoint":sha(WD/"model/model.safetensors"),"queries":len(groups),"seen_source":sum(groups.values()),"protocol":sha(D/"PROTOCOL_RU.md")});c.close()
def forecast():
    c=database();ranker=DenseTaskRetriever(encoder=Lookup(c,"ft"),device="cpu");files,texts,groups=inv.group();wanted={f.stem.split("-",1)[1].removesuffix(".json"):f for f in files}
    learned={n:load(D.parent/n/"model.json") for n in ("fine_read","fine_lextrain")};out=[];audit=0
    rank_rows=[]
    for i in range(8):
        import gzip,json
        with gzip.open(rd.blocks_path("dev",i),"rb") as sf:
            for line in sf:
                base=json.loads(line);t=base["t"]
                if t not in wanted:continue
                raw=load(wanted[t]);assert raw["t"]==t
                pool=[]
                for item in raw["pool"]:
                    md=item["metadata"];sp=item["source_spans"][0];k=(_argument_chunk_node_id if md["node_kind"]=="content.tool_argument" else _output_chunk_node_id)(md["call_id"],md["chunk_index"])
                    pool.append(TextCandidate(item_id=k,text=raw["fields"][sp["event_id"]][sp["char_start"]:sp["char_end"]],source_spans=item["source_spans"],metadata=md))
                check=WD/"projection/dev"/(t+".json.gz")
                if check.exists():
                    previous=load(check)["pool"];assert len(previous)==len(pool)
                    assert all(p.model_dump(mode="json")==v for p,v in zip(pool,previous,strict=True));audit+=1
                used={};picks={};geom=None
                for q,s in raw["q"]:
                    if q not in groups:continue
                    req=TextRankingRequest(task_id=q,query_text=s,candidates=tuple(pool));rank=ranker.rank(req)
                    packed=pilot.assemble_ranked_result(request=req,method="dense",ranked_nodes=rank,top_k=len(pool),latency_ms=0,retrieved_edges=[],native_trace=None).ranked_nodes;rr=[v.model_dump() for v in packed]
                    rank_rows.append({"q":q,"t":t,"rr":rr})
                    if geom is None:geom=rd.geometry(base,raw,rr)
                    bl=base["blocks"];x,rp,rl=rd.features(s,rr,bl,geom);part={}
                    for n,m in learned.items():
                        arms=rd.choose({"q":q,"rr":rr},bl,geom,x,rp,rl,m)
                        for a,ids in arms.items():
                            if a in ("prefix","skip","ratio","prob","unprotected"):
                                part[n+"/"+a]=ids
                                for k in ids:used[k]=bl[int(k[6:])][:4] if k.startswith("micro/") else geom[0][k]
                    picks[q]=part
                out.append({"t":t,"addresses":base["addresses"],"used":used,"picks":picks})
    assert sum(len(r["picks"]) for r in out)==80 and len(out)==74
    save(D/"dense-ranks-extra80.json.gz",rank_rows)
    save(D/"predictions.json.gz",out);save(D/"forecast-seal.json",{"forecast":sha(D/"predictions.json.gz"),"encoder":sha(D/"encoder-check.json"),"code":sha(D/"holdout.py"),"ranks":sha(D/"dense-ranks-extra80.json.gz"),"checked_source_trajectories":audit,"models":{n:sha(D.parent/n/"model.json") for n in learned}})
def evaluate():
    from collections import defaultdict
    from statistics import mean
    sys.path.insert(0,str(app.OLD/"tail_read"))
    from tail import independent,compare
    seal=load(D/"forecast-seal.json");assert sha(D/"predictions.json.gz")==seal["forecast"]
    gold=load(app.OLD/"write_transfer/gold-spans.json.gz");_,_,groups=inv.group();by=defaultdict(dict)
    for a in load(D/"predictions.json.gz"):
        for q,arms in a["picks"].items():
            for arm,ids in arms.items():
                sub=[]
                for k in ids:
                    e,l,h,n=a["used"][k];ed,ptr=a["addresses"][e];sp=pilot.SourceSpan(event_id=ed,json_pointer=ptr,char_start=l,char_end=h)
                    sub.append(pilot.RankedNodeRecord(node_id=k,score=0,token_count=n,source_spans=(sp,)))
                cost=sum(v.token_count for v in sub);assert cost<=2048
                m=pilot.span_metrics_under_token_budget(sub,tuple(pilot.SourceSpan.model_validate(s) for s in gold[q]),2048)
                audit=independent(gold[q],[n.model_dump() for n in sub]);assert all(abs(getattr(m,k)-v)<1e-12 for k,v in zip(("coverage","density","full_support"),audit,strict=True))
                by[arm][q]={"t":a["t"],"tokens":cost,**{f:getattr(m,f) for f in ("coverage","full_support","f1","density")}}
    assert all(set(vals)==set(groups) for vals in by.values())
    result={}
    for which in ("all","new_source","seen_source"):
        sel={q for q,y in groups.items() if which=="all" or y==(which=="seen_source")}
        cells={a:{q:v for q,v in bv.items() if q in sel} for a,bv in by.items()};stats={a:{"hits":sum(v["full_support"] for v in vals.values()),"coverage":mean(v["coverage"] for v in vals.values())} for a,vals in cells.items()}
        pairs={a:compare(vals,cells[a.split("/")[0]+"/skip"]) for a,vals in cells.items() if a.endswith(("/ratio","/prob","/unprotected"))}
        result[which]={"n":len(sel),"stats":stats,"pairs":pairs}
    save(D/"outcomes.json.gz",by);save(D/"results.json",result);print(result["all"]["stats"],flush=True)
if __name__=="__main__":{"encode":encode,"predict":forecast,"score":evaluate}[sys.argv[1]]()
