"""Freeze native flat and provenance-unit BM25 rankings plus four budget policies, one atomic receipt per trajectory."""
from pathlib import Path
from collections import defaultdict
import gzip
import hashlib
import json
import os
import subprocess
import sys
import time
from discover import ROOT,BASE,RAW,load,write,pilot
from graph_memory.datasets.isetrace.adapter import parse_isetrace_record,adapt_isetrace_record
from graph_memory.datasets.isetrace import retrieval_views
from graph_memory.retrieval.results import RankedNodeRecord

RUNTIME=pilot.CACHE.parent/"full-checkpoints"
B=2048
def encode_json(data):
    return json.dumps(data,ensure_ascii=False,sort_keys=True,separators=(",",":")).encode()+b"\n"
def ranking_lock():
    expected={name:pilot.sha(ROOT/name) for name in ("PROTOCOL_RU.md","fetch_all.py","discover.py","rank.py","source-lock.json","cohort.json","split-verification.json")}
    expected["r17_pilot_sha256"]=pilot.sha(BASE/"pilot.py")
    expected["official_code_version"]=pilot.CODE
    write("ranking-plan.json",expected)
def state_file(tid):
    assert tid.isascii() and tid.startswith("traj_") and tid.replace("_","").isalnum()
    return RUNTIME/(tid+".json.gz")
def checked(file,plan_hash):
    if not file.exists():return False
    seal=file.with_suffix(file.suffix+".sha256")
    if not seal.exists():return False
    assert pilot.sha(file)==seal.read_text("ascii").strip(),file
    assert json.loads(gzip.decompress(file.read_bytes()))["plan"]==plan_hash,file
    return True
def persist(tid,rec,plan_hash):
    path=state_file(tid);seal=path.with_suffix(path.suffix+".sha256")
    buf=gzip.compress(encode_json(dict(rec,plan=plan_hash)),compresslevel=4,mtime=0)
    temp=path.with_suffix(".tmp");temp.write_bytes(buf);temp.replace(path)
    tag=seal.with_suffix(".tmp.sha");tag.write_text(hashlib.sha256(buf).hexdigest(),encoding="ascii");tag.replace(seal)
def char_offsets(tokenizer,text):
    return [(a,b) for a,b in tokenizer.encode(text,add_special_tokens=False).offsets if b>a]
def clipped(rr,src,selected,view,cache):
    prefix_len=len(selected);remaining=B-sum(n.token_count for n in selected)
    if remaining<=0 or prefix_len==len(rr):return None
    node=rr[prefix_len];meta=src[node.node_id].metadata
    assert 0<remaining<node.token_count
    pos=meta["chunk_index"]*440
    if view=="flat":
        document,fragments,offset=cache["flat"]
        source=document
    else:
        span=node.source_spans[0];ev=span.event_id
        assert len(node.source_spans)==1
        source=cache["fields"][ev]
        if ev not in cache["offset_by_event"]:cache["offset_by_event"][ev]=char_offsets(cache["tokenizer"],source)
        offset=cache["offset_by_event"][ev]
    total=min(504,len(offset)-pos)
    start=offset[pos][0] if pos else 0
    end=len(source) if pos+total==len(offset) else offset[pos+total][0]
    assert total==node.token_count
    boundary=offset[pos+remaining][0]
    assert start<boundary<=end
    if view=="flat":
        assert start==meta["document_char_start"] and end==meta["document_char_end"]
        sp=retrieval_views._chunk_source_spans(chunk_start=start,chunk_end=boundary,fragments=fragments)
    else:
        assert start==span.char_start and end==span.char_end
        sp=(span.model_copy(update={"char_end":boundary}),)
    return RankedNodeRecord(node_id=node.node_id+"#clip",score=node.score,source_spans=sp,token_count=remaining)
def run_one(tr,queries,tokenizer,plan_hash,raw_digest,shard):
    offsets=pilot.offsets(tokenizer)
    flat=pilot.native.flat_trajectory_candidates(tr,tokenizer=offsets,max_tokens=504,overlap_tokens=64)
    graph=pilot.native.build_provenance_graph(tr,content_chunker=lambda s:pilot.token_chunks(s,tokenizer=offsets,max_tokens=504,overlap_tokens=64))
    pu=pilot.native.provenance_unit_candidates(graph)
    doc,fr=retrieval_views._render_trajectory(tr)
    cache={"flat":(doc,fr,char_offsets(tokenizer,doc)),"tokenizer":tokenizer,"offset_by_event":{},
           "fields":{**{a.event_id:a.raw_arguments for a in tr.tool_calls},**{a.event_id:a.content for a in tr.tool_outputs}}}
    allq={}
    for q in queries:
        views={}
        for view,pool in (("flat",flat),("provenance",pu)):
            req=pilot.TextRankingRequest(task_id=q["id"],query_text=q["query"],candidates=pool)
            ranks=pilot.assemble_ranked_result(request=req,method="bm25",ranked_nodes=pilot.BM25TaskRetriever().rank(req),top_k=len(pool),
                                            latency_ms=0,retrieved_edges=[],native_trace=None).ranked_nodes
            assert all(n.token_count>0 for n in ranks)
            src={n.item_id:n for n in pool};meta={k:x.metadata for k,x in src.items()}
            arms={}
            for policy in ["prefix","skip","value"]+(["related"] if view=="provenance" else []):
                arms[policy]=[n.node_id for n in pilot.pack(ranks,meta,B,policy)]
            prefix=pilot.pack(ranks,meta,B,"prefix")
            extra=clipped(ranks,src,prefix,view,cache)
            arms["clip"]=arms["prefix"]+([extra.node_id] if extra is not None else [])
            # Full order is retained for exact verification; no raw source text is exported.
            views[view]={"ranked":[r.model_dump() for r in ranks],"partial":None if extra is None else extra.model_dump(),"arms":arms}
        allq[q["id"]]=views
    persist(tr.trajectory_id,{"trajectory_id":tr.trajectory_id,"shard":shard,"source_record_sha256":raw_digest,"queries":allq},plan_hash)
def rank_shard(i):
    RUNTIME.mkdir(exist_ok=True)
    plan_hash=pilot.sha(ROOT/"ranking-plan.json")
    locks=load("ranking-plan.json")
    for n,h in locks.items():
        if n.endswith((".py",".json",".md")):assert pilot.sha(ROOT/n)==h,n
    assert pilot.sha(BASE/"pilot.py")==locks["r17_pilot_sha256"] and pilot.CODE==locks["official_code_version"]
    records=load("cohort.json");ids={v["query_id"]:v["trajectory_id"] for v in records}
    by=defaultdict(list)
    for _,q in pilot.stream(pilot.Q):
        if q["id"] in ids:by[ids[q["id"]]].append({"id":q["id"],"query":q["query"]})
    source=RAW/f"trajectories-{i:05d}.jsonl"
    sourcelock=load("source-lock.json");digests={x["path"]:x["sha256"] for x in sourcelock}
    assert pilot.sha(source)==digests["trajectories/"+source.name]
    tokenizer=pilot.Tokenizer.from_file(str(pilot.CACHE/"tokenizer.json"))
    start=time.monotonic();done=0
    for raw,row in pilot.stream(source):
        tid=row["session_id"]
        if tid not in by:continue
        if not checked(state_file(tid),plan_hash):
            tr=adapt_isetrace_record(parse_isetrace_record(row),source_revision=pilot.RAW[1])
            run_one(tr,by[tid],tokenizer,plan_hash,hashlib.sha256(raw).hexdigest(),i)
        done+=1
        if done%20==0:print("shard",i,"completed",done,"seconds",round(time.monotonic()-start,1),flush=True)
    print("finished shard",i,done,round(time.monotonic()-start,1),flush=True)
if __name__=="__main__":
    if sys.argv[1]=="lock":ranking_lock()
    else:rank_shard(int(sys.argv[1]))
