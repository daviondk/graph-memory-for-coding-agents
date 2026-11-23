"""Compare immutable author rankings under alternate token packing policies."""
import argparse
import collections
import dataclasses
import gzip
import hashlib
import json
import math
from pathlib import Path
import re
import subprocess
import sys
import types

import numpy as np
from tokenizers import Tokenizer
from provision import ROOT, CACHE, RAW

RUNTIME = CACHE.parent
UPSTREAM = RUNTIME/"upstream"
CODE = "df29287116fa1565b3fd6b485022cd6090dc0b27"
assert subprocess.check_output(["git","-C",str(UPSTREAM),"rev-parse","HEAD"]).decode().strip()==CODE
assert not subprocess.check_output(["git","-C",str(UPSTREAM),"diff","--","graph_memory"])
sys.path.insert(0,str(UPSTREAM))
# The package initializer imports optional torch training classes. Load the exact
# unmodified retrieval, adapter and scoring leaf modules in the lightweight CPU env.
key="graph_memory.datasets.isetrace"
package=types.ModuleType(key)
package.__path__=[str(UPSTREAM/"graph_memory/datasets/isetrace")]
sys.modules[key]=package
from graph_memory.datasets.isetrace import benchmark_adapter as native
from graph_memory.evaluation.span_metrics import span_metrics_under_token_budget
from graph_memory.retrieval.execution.results import assemble_ranked_result
from graph_memory.retrieval.methods.flat.bm25 import BM25TaskRetriever
from graph_memory.retrieval.requests import TextRankingRequest
from graph_memory.retrieval.results import RankedNodeRecord
from graph_memory.text.chunking import token_chunks
from graph_memory.trajectories import SourceSpan

Q=CACHE/"query-authoring/isetrace-v7-raw.jsonl"
META=Q.with_suffix(".jsonl.metadata.jsonl")
SHARD=CACHE/"trajectories/trajectories-00000.jsonl"
BUDGETS=(512,1024,2048)
EXCLUDE = re.compile(r"\b(?:exploit\w*|vulnerab\w*|malware|phishing|ransomware|intrusion|credential\w*|cyberattack\w*|cybersecurity|security|bypass\w*|hack(?:er|ing)?|pentest\w*|payload\w*|reverse shell|botnet|firearm\w*|weapon\w*|missile\w*|military|combat|militia|defense|warfare|munition\w*|terroris\w*|explosiv\w*|gunpowder|pathogen\w*|viral|viruses|vaccine\w*|synthesi[sz]\w*|toxin\w*|bioweapon\w*|bacteria\w*|genome\w*|genetic\w*|virolog\w*|sequencing|antibody|drug synthesis|medical diagnosis)\b", re.I)

def stream(path):
    with path.open("rb") as f:
        for raw in f:
            if raw.strip():yield raw,json.loads(raw)
def sha(path):
    with path.open("rb") as f:return hashlib.file_digest(f,"sha256").hexdigest()
def dump(name,obj):
    data=json.dumps(obj,ensure_ascii=False,sort_keys=True,separators=(",",":")).encode("utf8")+b"\n"
    path=ROOT/name
    if name.endswith(".gz"):data=gzip.compress(data,mtime=0)
    if path.exists():assert path.read_bytes()==data, name
    else:path.write_bytes(data)
def load(name):
    p=ROOT/name;b=p.read_bytes()
    return json.loads(gzip.decompress(b) if name.endswith(".gz") else b)
def verify_sources():
    for x in load("source-lock.json"):assert sha(CACHE/x["path"])==x["sha256"]
def cohort():
    verify_sources()
    meta={m["query_id"]:m for _,m in stream(META)}
    order={}; allowed={}; query_meta={}
    for idx,(_,q) in enumerate(stream(Q)):
        m=meta[q["id"]]; tid=m["trajectory_id"]
        if tid not in order and len(order)==1200:break
        order.setdefault(tid,len(order)+1)
        query_meta[q["id"]]=m
        if EXCLUDE.search(q["query"]):continue
        allowed.setdefault(tid,[]).append(q["id"])
    seen={}; rejects=0; in_shard=0
    for raw,obj in stream(SHARD):
        tid=obj["session_id"]
        if tid not in allowed:continue
        in_shard+=1
        intents="\n".join(i["natural_language_intent"] for i in obj["source_intents"])
        if EXCLUDE.search(intents):
            rejects+=1;continue
        assert tid not in seen
        seen[tid]=hashlib.sha256(raw).hexdigest()
    selected=sorted(seen,key=lambda t:hashlib.sha256(("r17-fit/"+t).encode()).digest())[:64]
    assert len(selected)>=10
    rows={t:{"ordinal":order[t],"record_sha":seen[t],"queries":allowed[t]} for t in selected}
    dump("cohort.json",{"selected":rows,"in_shard":in_shard,"excluded_by_intent":rejects,"eligible":len(seen),
                        "prefix_trajectories":len(order),"prefix_queries":len(query_meta),"upstream":CODE})
    dump("assignment.json",{n:sha(ROOT/n) for n in ("pilot.py","PROTOCOL_RU.md","cohort.json","source-lock.json","provision.py")})
    print("cohort",len(selected),"queries",sum(len(allowed[t]) for t in selected),"in shard",in_shard,"allow",len(seen),flush=True)

def offsets(tok):
    def get(text,*,add_special_tokens,return_offsets_mapping,truncation):
        assert not add_special_tokens and return_offsets_mapping and not truncation
        return {"offset_mapping":tok.encode(text,add_special_tokens=False).offsets}
    return get
def pack(ranks,meta,budget,policy):
    selected=[];used=0
    for pos,node in enumerate(ranks):
        if used+node.token_count>budget:break
        selected.append(node);used+=node.token_count
    else:return selected
    tail=ranks[pos:]
    if policy=="prefix":return selected
    if policy=="value":tail=sorted(tail,key=lambda n:(-n.score/math.sqrt(n.token_count),n.node_id))
    if policy=="related":
        keep={(meta[n.node_id]["call_id"],meta[n.node_id]["node_kind"]) for n in selected if meta[n.node_id].get("call_id")}
        def adjacent(n):
            m=meta[n.node_id]
            other={"content.tool_output":"content.tool_argument","content.tool_argument":"content.tool_output"}.get(m.get("node_kind"))
            return bool(other and (m.get("call_id"),other) in keep)
        tail=sorted(tail,key=lambda n:not adjacent(n))
    for node in tail:
        if used+node.token_count<=budget:
            selected.append(node);used+=node.token_count
    return selected
def ranking():
    for n,h in load("assignment.json").items():assert sha(ROOT/n)==h
    selected=load("cohort.json")["selected"]
    identifiers={k:t for t,v in selected.items() for k in v["queries"]}
    examples=[native._QUERY_ADAPTER.validate_python(q) for _,q in stream(Q) if q["id"] in identifiers]
    assert len(examples)==len(identifiers)
    # Match the exact authoring sources against the full shard, including non-selected trajectories.
    summary=native.ISETraceBenchmarkSummary()
    matched=native._match_query_contexts(SHARD,examples=examples,source_revision=RAW[1],strict=False,summary=summary)
    assert all(identifiers[q]==v[0].trajectory_id for q,v in matched.items())
    rejected=sorted(set(identifiers)-set(matched))
    tok=offsets(Tokenizer.from_file(str(CACHE/"tokenizer.json")))
    def chunk(s):return token_chunks(s,tokenizer=tok,max_tokens=504,overlap_tokens=64)
    examples=[e for e in examples if e.id in matched]
    print("canonical",len(examples),"excluded",len(rejected),flush=True)
    trajectories,graphs,contexts=native._build_selected_contexts(examples,matched_contexts=matched,content_chunker=chunk)
    pool={}
    for t,g in graphs.items():
        pool[t]={"flat":native.flat_trajectory_candidates(trajectories[t],tokenizer=tok,max_tokens=504,overlap_tokens=64),
                 "provenance":native.provenance_unit_candidates(g)}
    by_task={};cards=[]
    retriever=BM25TaskRetriever()
    for example in examples:
        tid=identifiers[example.id]
        arms={}
        for view, candidates in pool[tid].items():
            req=TextRankingRequest(task_id=example.id,query_text=example.query,candidates=candidates)
            result=assemble_ranked_result(request=req,method="bm25",ranked_nodes=retriever.rank(req),top_k=len(candidates),
                    latency_ms=0,retrieved_edges=[],native_trace=None)
            ranks=result.ranked_nodes
            assert all(n.token_count>0 for n in ranks)
            attributes={x.item_id:x.metadata for x in candidates}
            by_task[example.id,view]=ranks
            arms[view]={str(b):{h:[n.node_id for n in pack(ranks,attributes,b,h)]
                     for h in (["prefix","skip","value"]+(["related"] if view=="provenance" else []))} for b in BUDGETS}
        cards.append({"query":example.id,"trajectory":tid,"sets":arms})
    dump("selections.json.gz",cards)
    dump("native-ranks.json.gz",[{"q":q,"v":v,"ranking":[n.model_dump() for n in ranks]} for (q,v),ranks in by_task.items()])
    dump("projection.json",{"rejections":rejected,"native_matching":dict(summary),
           "nodes":{t:{v:len(c) for v,c in views.items()} for t,views in pool.items()}})
    dump("prediction-seal.json",{n:sha(ROOT/n) for n in ("assignment.json","selections.json.gz","native-ranks.json.gz","projection.json")})
    # Only after selection lock resolve quotes and pass gold to native scoring.
    gold={e.id:[s.model_dump() for s in native._resolve_gold_spans(e,contexts[e.id][1])] for e in examples}
    dump("gold-spans.json.gz",gold)
    print("sealed",len(cards),"queries",len(graphs),"trajectories",flush=True)
def evaluate():
    for n,h in load("prediction-seal.json").items():assert sha(ROOT/n)==h
    gold={q:tuple(SourceSpan.model_validate(s) for s in src) for q,src in load("gold-spans.json.gz").items()}
    ranks={(r["q"],r["v"]):tuple(RankedNodeRecord.model_validate(n) for n in r["ranking"]) for r in load("native-ranks.json.gz")}
    rows=[]
    for task in load("selections.json.gz"):
        q=task["query"];tid=task["trajectory"]
        for view,bb in task["sets"].items():
            rr=ranks[q,view];lookup={n.node_id:n for n in rr}
            for sb,policies in bb.items():
                budget=int(sb)
                for p,ids in policies.items():
                    sub=tuple(lookup[k] for k in ids)
                    used=sum(n.token_count for n in sub)
                    assert used<=budget and len(ids)==len(set(ids))
                    m=span_metrics_under_token_budget(sub,gold[q],budget)
                    if p=="prefix":assert m==span_metrics_under_token_budget(rr,gold[q],budget)
                    rows.append(dict(query=q,trajectory=tid,view=view,policy=p,budget=budget,tokens=used,nodes=len(sub),**dataclasses.asdict(m)))
    dump("outcomes.json.gz",rows)
    aggregates={}
    pairs=collections.defaultdict(dict)
    for row in rows:
        key=f"{row['budget']}/{row['view']}/{row['policy']}"
        pairs[key][row['query']]=row
    for k,items in pairs.items():
        aggregates[k]={m:float(np.mean([r[m] for r in items.values()])) for m in ("full_support","density","coverage","f1","tokens","nodes")}
        aggregates[k]["full_count"]=int(sum(r["full_support"] for r in items.values()))
    ci={}
    for v in ["flat","provenance"]:
        contrasts=[("skip","prefix"),("value","skip")]+([("related","skip")] if v=="provenance" else [])
        for p,c in contrasts:
            b=2048
            tgt=pairs[f"{b}/{v}/{p}"];ref=pairs[f"{b}/{v}/{c}"]
            clusters=collections.defaultdict(list)
            for q,r in tgt.items():clusters[r["trajectory"]].append(r["full_support"]-ref[q]["full_support"])
            data=list(clusters.values());sums=np.array([sum(x) for x in data]);sizes=np.array(list(map(len,data)))
            rng=np.random.default_rng(13);idx=rng.integers(len(data),size=(10000,len(data)))
            sample=sums[idx].sum(1)/sizes[idx].sum(1)
            diff=np.concatenate(data)
            ci[f"{v}/{p}-{c}"]={"n":len(diff),"delta":float(np.mean(diff)),"wins":int(sum(diff>0)),"losses":int(sum(diff<0)),
                            "cluster_ci95":[float(v) for v in np.quantile(sample,[.025,.975])]}
    dump("results.json",{"n":len(gold),"trajectories":len(set(r["trajectory"] for r in rows)),"means":aggregates,"contrasts":ci})
    print(json.dumps({"n":len(gold),"fs2048":{k:round(d["full_support"],3) for k,d in aggregates.items() if k.startswith("2048")},"contrasts":ci}),flush=True)

if __name__=="__main__":
    action=argparse.ArgumentParser();action.add_argument("stage",choices=["cohort","rank","score"]);name=action.parse_args().stage
    {"cohort":cohort,"rank":ranking,"score":evaluate}[name]()
