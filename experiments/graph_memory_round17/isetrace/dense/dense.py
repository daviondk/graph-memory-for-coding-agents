"""Locked CPU replication of the packed evidence experiment with the original frozen encoder."""
import collections
import gzip
import hashlib
import json
import os
from pathlib import Path
import sys
import time

import numpy as np
import torch
import sentence_transformers
import transformers

ROOT=Path(__file__).resolve().parent
PANELS=[ROOT.parent,ROOT.parent/"replication"]
sys.path.insert(0,str(ROOT.parent))
import pilot
from graph_memory.datasets.isetrace.adapter import parse_isetrace_record, adapt_isetrace_record
from graph_memory.retrieval.methods.flat.dense import DenseTaskRetriever
from graph_memory.embeddings import load_sentence_transformer

def load(path):
    data=path.read_bytes()
    return json.loads(gzip.decompress(data) if path.suffix==".gz" else data)
def put(name,obj):
    data=json.dumps(obj,ensure_ascii=False,sort_keys=True,separators=(",",":")).encode("utf8")+b"\n"
    if name.endswith(".gz"):data=gzip.compress(data,mtime=0)
    p=ROOT/name
    if p.exists():assert p.read_bytes()==data,name
    else:p.write_bytes(data)
def alloc():
    params={}
    for idx,p in enumerate(PANELS):
        cases=load(p/"cohort.json")["selected"]
        ids=set(load(p/"projection.json")["nodes"])
        top=sorted(ids,key=lambda t:hashlib.sha256(("r17-e5/"+t).encode()).digest())[:8]
        dropped=set(load(p/"projection.json")["rejections"])
        params[str(idx)]={t:[q for q in cases[t]["queries"] if q not in dropped] for t in top}
    put("selection.json",params)
    put("plan-seal.json",{n:pilot.sha(ROOT/n) for n in ("selection.json","PROTOCOL_RU.md","dense.py","weights-lock.json")})
def prepare():
    assigned=load(ROOT/"selection.json")
    allq={q:row for _,row in pilot.stream(pilot.Q) if (q:=row["id"]) in {q for pairs in assigned.values() for ids in pairs.values() for q in ids}}
    paths=sorted(pilot.SHARD.parent.glob("trajectories-*.jsonl"))
    records=[];statuses={}
    tok=pilot.offsets(pilot.Tokenizer.from_file(str(pilot.CACHE/"tokenizer.json")))
    for i,p in enumerate(PANELS):
        selected=assigned[str(i)]
        bmrows={(row["q"],row["v"]):row["ranking"] for row in load(p/"native-ranks.json.gz") if row["q"] in {q for ids in selected.values() for q in ids} and row['v']=='provenance'}
        checks=load(p/"cohort.json")["selected"]; n=0
        for raw,data in pilot.stream(paths[i]):
            tid=data["session_id"]
            if tid not in selected:continue
            assert hashlib.sha256(raw).hexdigest()==checks[tid]["record_sha"]
            tr=adapt_isetrace_record(parse_isetrace_record(data),source_revision=pilot.RAW[1])
            graph=pilot.native.build_provenance_graph(tr,content_chunker=lambda s:pilot.token_chunks(s,tokenizer=tok,max_tokens=504,overlap_tokens=64))
            candidates=pilot.native.provenance_unit_candidates(graph)
            for q in selected[tid]:
                req=pilot.TextRankingRequest(task_id=q,query_text=allq[q]["query"],candidates=candidates)
                original={v["node_id"]:v for v in bmrows[q,"provenance"]}
                ranks=pilot.assemble_ranked_result(request=req,method="bm25",ranked_nodes=pilot.BM25TaskRetriever().rank(req),top_k=len(candidates),latency_ms=0,retrieved_edges=[],native_trace=None)
                assert [r.model_dump(mode="json") for r in ranks.ranked_nodes]==bmrows[q,"provenance"],q
                records.append((i,tid,req));n+=1
        statuses[str(i)]=n
    assert len(records)==len(allq)
    return records,statuses
class Cached:
    def __init__(self,model):
        self.model=model;self.cache={}
    def encode(self,texts,**kwargs):
        assert kwargs=={"batch_size":64,"normalize_embeddings":True,"show_progress_bar":False}
        missing=list(dict.fromkeys(t for t in texts if t not in self.cache))
        if missing:
            vectors=self.model.encode(missing,**kwargs)
            self.cache.update(zip(missing,vectors,strict=True))
        return np.stack([self.cache[t] for t in texts])
def rank():
    for n,h in load(ROOT/"plan-seal.json").items():assert pilot.sha(ROOT/n)==h
    weights=pilot.CACHE.parent/"e5-base-v2"
    for item in load(ROOT/"weights-lock.json"):assert pilot.sha(weights/item["path"])==item["sha256"]
    records,status=prepare()
    torch.set_num_threads(6)
    torch.set_num_interop_threads(1)
    model=load_sentence_transformer(str(weights),device="cpu")
    cached=Cached(model)
    retriever=DenseTaskRetriever(model_name=str(weights),device="cpu",encoder=cached)
    native_rows=[];selection=[]
    stamp=time.perf_counter()
    for j,(i,tid,req) in enumerate(records):
        res=pilot.assemble_ranked_result(request=req,method="dense",ranked_nodes=retriever.rank(req),top_k=len(req.candidates),
                latency_ms=0,retrieved_edges=[],native_trace=None)
        ranking=res.ranked_nodes
        meta={c.item_id:c.metadata for c in req.candidates}
        sets={str(b):{h:[n.node_id for n in pilot.pack(ranking,meta,b,h)] for h in ("prefix","skip","value","related")} for b in pilot.BUDGETS}
        native_rows.append({"shard":i,"trajectory":tid,"query":req.task_id,"ranking":[r.model_dump() for r in ranking]})
        selection.append({"q":req.task_id,"sets":sets})
        print(j+1,"/",len(records),len(cached.cache),"encoded unique strings",round(time.perf_counter()-stamp),"s",flush=True)
    put("ranked.json.gz",native_rows);put("sets.json.gz",selection)
    put("dense-predictions-seal.json",{n:pilot.sha(ROOT/n) for n in ("plan-seal.json","ranked.json.gz","sets.json.gz")})
    put("runtime.json",{"device":"cpu","threads":6,"dtype":str(next(model.parameters()).dtype),"torch":torch.__version__,"transformers":transformers.__version__,
                     "sentence_transformers":sentence_transformers.__version__,"queries_per_panel":status,"encoded_unique_strings":len(cached.cache),"seconds":time.perf_counter()-stamp})
def score():
    import dataclasses
    for n,h in load(ROOT/"dense-predictions-seal.json").items():assert pilot.sha(ROOT/n)==h
    ranks={r["query"]:r for r in load(ROOT/"ranked.json.gz")}
    gold={q:tuple(pilot.SourceSpan.model_validate(s) for s in span) for p in PANELS for q,span in load(p/"gold-spans.json.gz").items() if q in ranks}
    rows=[]
    for card in load(ROOT/"sets.json.gz"):
        q=card["q"];src=ranks[q];allnodes={v["node_id"]:pilot.RankedNodeRecord.model_validate(v) for v in src["ranking"]}
        for b,policy in card["sets"].items():
            for h,ids in policy.items():
                sub=tuple(allnodes[k] for k in ids);used=sum(s.token_count for s in sub)
                assert used<=int(b)
                metrics=pilot.span_metrics_under_token_budget(sub,gold[q],int(b))
                if h=="prefix":assert metrics==pilot.span_metrics_under_token_budget(tuple(allnodes.values()),gold[q],int(b))
                rows.append(dict(query=q,trajectory=src["trajectory"],shard=src["shard"],budget=int(b),ranker="dense",policy=h,tokens=used,**dataclasses.asdict(metrics)))
    for i,p in enumerate(PANELS):
        for row in load(p/"outcomes.json.gz"):
            if row["query"] in ranks and row["view"]=="provenance":rows.append(dict(row,shard=i,ranker="bm25"))
    put("outcomes.json.gz",rows)
    print("scored",len(rows),"tasks",len(gold),flush=True)
if __name__=="__main__":{"allocate":alloc,"rank":rank,"score":score}[sys.argv[1]]()
