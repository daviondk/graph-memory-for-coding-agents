"""Transfer frozen write policies to the complete author-defined ISETrace development partition."""
from concurrent.futures import ProcessPoolExecutor
from collections import Counter,defaultdict
import argparse
import gzip
import hashlib
import importlib.util
import json
import os
import sys
from pathlib import Path
from statistics import mean
import numpy as np

D=Path(__file__).resolve().parent;UP=D.parent/"online_write";TRAINED=D.parent/"trained_rank"
OFF=D.parents[1]/"graph_memory_round18/isetrace_official"
sys.path.insert(0,str(UP));import predict,graph_write
spec=importlib.util.spec_from_file_location("r19_storage_metrics",UP/"score.py");measure=importlib.util.module_from_spec(spec);spec.loader.exec_module(measure)
sys.path.insert(0,str(OFF));from discover import N,pilot,RAW,sample_split
from graph_memory.datasets.isetrace.adapter import parse_isetrace_record,adapt_isetrace_record
RUNTIME=pilot.CACHE.parent/"write-dev-private";PROJECTION=RUNTIME/"projection";SCRATCH=RUNTIME/"forecasts"
def stable(obj):return json.dumps(obj,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()
def put(path,obj):
    if isinstance(path,str):path=D/path
    raw=stable(obj)+b"\n"
    if path.suffix==".gz":raw=gzip.compress(raw,mtime=0)
    if path.exists():assert path.read_bytes()==raw,path
    else:path.write_bytes(raw)
def load(path):
    if isinstance(path,str):path=D/path
    b=path.read_bytes();return json.loads(gzip.decompress(b) if path.suffix==".gz" else b)
def lock():
    digest=pilot.sha
    linked={str(p.relative_to(D.parents[1])).replace("\\","/"):digest(p) for p in (
        UP/"predict.py",UP/"graph_write.py",UP/"score.py",UP/"PROTOCOL_RU.md",UP/"GRAPH_PROTOCOL_RU.md",TRAINED/"split.json.gz",OFF/"cohort.json",OFF/"split-verification.json",OFF/"source-lock.json")}
    put("design-lock.json",{"sources":linked,"implementation":digest(D/"transfer.py"),"protocol":digest(D/"PROTOCOL_RU.md"),"tokenizer":digest(predict.TOKENIZER)})
def check():
    s=load("design-lock.json")
    for f,h in s["sources"].items():assert pilot.sha(D.parents[1]/f)==h
    assert s["implementation"]==pilot.sha(D/"transfer.py") and s["protocol"]==pilot.sha(D/"PROTOCOL_RU.md") and s["tokenizer"]==pilot.sha(predict.TOKENIZER)
def split():
    check();drops=set(load(OFF/"split-verification.json")["dropped_queries"])
    meta={v["query_id"]:v["trajectory_id"] for _,v in pilot.stream(pilot.META)}
    ids=[v["id"] for _,v in pilot.stream(pilot.Q) if v["id"] not in drops]
    group=N.allocate_trajectory_splits([meta[q] for q in ids],split_counts={"train":2410,"dev":352,"test":1207},split_seed=13)
    allq={label:sample_split([q for q in ids if meta[q] in g],count=None,seed=13,offset=0) for label,g in group.items()}
    full_profile=sample_split([q for q in ids if meta[q] in group["dev"]],count=500,seed=13,offset=0)
    x=load(TRAINED/"split.json.gz")
    for label in ("train","dev","test"):
        ref=[{"q":q,"t":meta[q]} for q in (full_profile if label=="dev" else allq[label])]
        assert x[label]==ref
    assert {q for q in allq["test"]}=={r["query_id"] for r in load(OFF/"cohort.json")}
    sizes={}
    for l in allq:
        for m in allq:
            if l!=m:assert set(allq[l]).isdisjoint(allq[m]) and group[l].isdisjoint(group[m])
        sizes[l]={"q":len(allq[l]),"t":len(group[l])}
    assert sizes=={"train":{"q":3894,"t":2410},"dev":{"q":580,"t":352},"test":{"q":2000,"t":1207}}
    rows=[{"q":q,"t":meta[q],"publication_dev500":q in full_profile} for q in allq["dev"]];put("cohort.json",rows)
    report={"sizes":sizes,"overlap_query_count":0,"overlap_trajectory_count":0,"full_profile_exact_match":True,"test_id_set_match":True,
            "dev500_t":len({meta[q] for q in full_profile}),"other80_t":len({u["t"] for u in rows if not u["publication_dev500"]})}
    put("split-audit.json",report);print(report,flush=True)
def data_shard(task):
    stage,i=task
    cohort=load("cohort.json");groups=defaultdict(set)
    for r in cohort:groups[r["t"]].add(r["q"])
    wanted={x["q"] for x in cohort}
    if stage=="prepare":
        text={q["id"]:q["query"] for _,q in pilot.stream(pilot.Q) if q["id"] in wanted}
        tokenizer=pilot.offsets(pilot.Tokenizer.from_file(str(predict.TOKENIZER)))
    else:
        lockmap=load("forecast-lock.json")
        for f,digest in lockmap["forecasts"].items():assert pilot.sha(D/f)==digest
        examples={q.id:q for q in N._read_queries(pilot.Q,strict=False,summary=N.ISETraceBenchmarkSummary()) if q.id in wanted}
    f=RAW/f"trajectories-{i:05d}.jsonl"
    source={r["path"]:r["sha256"] for r in load(OFF/"source-lock.json")}
    assert pilot.sha(f)==source["trajectories/"+f.name]
    summary={};truth={}
    for raw,row in pilot.stream(f):
        t=row["session_id"]
        if t not in groups:continue
        tr=adapt_isetrace_record(parse_isetrace_record(row),source_revision=pilot.RAW[1])
        if stage=="prepare":
            graph=pilot.native.build_provenance_graph(tr,content_chunker=lambda s:pilot.token_chunks(s,tokenizer=tokenizer,max_tokens=504,overlap_tokens=64))
            pool=pilot.native.provenance_unit_candidates(graph)
            fields={**{a.event_id:a.raw_arguments for a in tr.tool_calls},**{a.event_id:a.content for a in tr.tool_outputs}}
            publication=[{"metadata":dict(c.metadata),"source_spans":[s.model_dump() for s in c.source_spans]} for c in pool]
            name=f"{i}-{t}.json.gz";put(PROJECTION/name,{"t":t,"pool":publication,"fields":fields,"q":[[q,text[q]] for q in sorted(groups[t])]})
            summary[t]={"shard":i,"record_sha256":hashlib.sha256(raw).hexdigest(),"projection_sha256":pilot.sha(PROJECTION/name),"n":len(groups[t])}
        else:
            info=load("projection-lock.json")["trajectories"][t];assert info["record_sha256"]==hashlib.sha256(raw).hexdigest()
            for q in groups[t]:
                ex=examples[q];mapping=N._match_task_text(ex,tr);assert mapping is not None
                truth[q]=[s.model_dump() for s in N._resolve_gold_spans(ex,mapping)];assert truth[q]
    return summary if stage=="prepare" else truth
def projection():
    check();PROJECTION.mkdir(exist_ok=True,parents=True);SCRATCH.mkdir(exist_ok=True,parents=True)
    with ProcessPoolExecutor(4) as p:pieces=list(p.map(data_shard,[("prepare",i) for i in range(8)]))
    obs={k:v for piece in pieces for k,v in piece.items()}
    assert len(obs)==352 and sum(x["n"] for x in obs.values())==580
    put("projection-lock.json",{"design":pilot.sha(D/"design-lock.json"),"cohort":pilot.sha(D/"cohort.json"),"trajectories":obs})
    print("projected",len(obs),flush=True)
def predictions(i):
    plan=load("projection-lock.json")
    for t,item in plan["trajectories"].items():
        if item["shard"]==i:assert pilot.sha(PROJECTION/f"{i}-{t}.json.gz")==item["projection_sha256"]
    predict.HERE=SCRATCH;predict.CACHE=PROJECTION;predict.CAPS=(8192,)
    graph_write.HERE=SCRATCH;graph_write.CACHE=PROJECTION
    n=predict.worker(i);graph_write.worker(i)
    dest=D/f"predictions-{i}.jsonl.gz"
    tmp=dest.with_suffix(".part")
    with gzip.open(SCRATCH/f"forecast-{i}.jsonl.gz","rb") as a,gzip.open(SCRATCH/f"graph-{i}.jsonl.gz","rb") as b,tmp.open("wb") as file,gzip.GzipFile(filename="",mode="wb",fileobj=file,mtime=0,compresslevel=6) as fout:
        for l,m in zip(a,b,strict=True):
            rec,extra=json.loads(l),json.loads(m);assert rec["t"]==extra["t"]
            rec["arms"].update(extra["arms"]);rec["stats"]=extra["stats"]
            fout.write(stable(rec)+b"\n")
    if dest.exists():assert pilot.sha(dest)==pilot.sha(tmp);tmp.unlink()
    else:tmp.replace(dest)
    return n
def forecast():
    check()
    with ProcessPoolExecutor(4) as pool:counts=list(pool.map(predictions,range(8)))
    assert sum(counts)==352;put("forecast-lock.json",{"projections":pilot.sha(D/"projection-lock.json"),"forecasts":{f.name:pilot.sha(f) for f in sorted(D.glob("predictions-*.jsonl.gz"))}})
    print("frozen",counts,flush=True)
def score():
    check()
    with ProcessPoolExecutor(4) as pool:pieces=list(pool.map(data_shard,[("score",i) for i in range(8)]))
    truth={k:v for piece in pieces for k,v in piece.items()}
    assert len(truth)==580
    put("gold-spans.json.gz",truth);gold={q:tuple(pilot.SourceSpan.model_validate(s) for s in ss) for q,ss in truth.items()}
    rows={};costs={};rowsby={};declared={r["q"]:r for r in load("cohort.json")};counts=Counter()
    for f,digest in load("forecast-lock.json")["forecasts"].items():
        assert pilot.sha(D/f)==digest
        with gzip.open(D/f,"rb") as src:
            for line in src:
                r=json.loads(line);t=r["t"];nodes=[]
                for j,(e,a,b,c,nb) in enumerate(r["blocks"]):
                    eid,ptr=r["addresses"][e];span=pilot.SourceSpan(event_id=eid,json_pointer=ptr,char_start=a,char_end=b)
                    nodes.append(pilot.RankedNodeRecord(node_id=str(j),score=0,token_count=c,source_spans=(span,)))
                counts.update(r["stats"]);costs[t]={}
                for name,(keep,qs) in r["arms"].items():
                    keep=list(range(len(nodes))) if keep is None else keep
                    assert len(set(keep))==len(keep)
                    stored=[nodes[j] for j in keep];tk=sum(a.token_count for a in stored)
                    assert name=="all" or tk<=8192
                    costs[t][name]={"write_tokens":tk,"bytes":sum(r["blocks"][j][4] for j in keep),"blocks":len(keep)}
                    for q,chosen in qs.items():
                        assert declared[q]["t"]==t and len(set(chosen))==len(chosen) and set(chosen)<=set(keep)
                        read=[nodes[j] for j in chosen];rt=sum(a.token_count for a in read);assert rt<=2048
                        # The original evaluator additionally compares its native metrics to its independent span calculation.
                        w=measure.take(stored,gold[q],True);v=measure.take(read,gold[q],True)
                        assert v[0]<=w[0] and v[1]<w[1]+1e-12
                        row=rows.setdefault(q,{"q":q,"t":t,"a":{}})
                        row["a"][name]=list(w)+list(v)+[rt]
    arms=sorted(next(iter(rows.values()))["a"])
    assert len(rows)==580 and all(set(row["a"])==set(arms) for row in rows.values())
    put("outcomes.json.gz",list(rows.values()));put("storage.json.gz",costs)
    subsets={"all580":list(rows.values()),"profile500":[x for q,x in rows.items() if declared[q]["publication_dev500"]],"other80":[x for q,x in rows.items() if not declared[q]["publication_dev500"]]}
    out={}
    for label,part in subsets.items():
        armscores={h:{"mean":np.mean([r["a"][h] for r in part],axis=0).tolist(),"write_full_count":int(sum(r["a"][h][0] for r in part)),"read_full_count":int(sum(r["a"][h][3] for r in part))} for h in arms}
        tt={r["t"] for r in part}
        store={h:{k:mean(costs[t][h][k] for t in tt) for k in ("write_tokens","bytes","blocks")} for h in arms}
        effects={}
        for left,right in (("head/8192","fifo/8192"),("output_head/8192","head/8192"),("shared","shifted"),("shared","head/8192")):
            for j,stage in ((0,"write"),(3,"read")):
                entry=measure.ci(part,(left,right),j)
                effects[f"{left}:{right}:{stage}"]=entry
        out[label]={"n":len(part),"trajectories":len(tt),"metrics":armscores,"storage_per_trajectory":store,"effects":effects}
    out["graph_events"]=dict(counts);put("results.json",out);print({k:(v["write_full_count"],v["read_full_count"]) for k,v in out["all580"]["metrics"].items()},flush=True)
if __name__=="__main__":
    {"lock":lock,"split":split,"project":projection,"forecast":forecast,"score":score}[sys.argv[1]]()
