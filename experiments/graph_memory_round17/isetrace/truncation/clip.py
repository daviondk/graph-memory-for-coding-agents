"""Sub-token-quota prefix using original source coordinates. Score original and partial nodes identically."""
from pathlib import Path
import collections
import dataclasses
import gzip
import hashlib
import json
import re
import sys
ROOT=Path(__file__).resolve().parent
HOME=ROOT.parent
sys.path.insert(0,str(HOME))
import pilot
from summarize import load,matched,summary
from verify_records import metrics

PANELS=[HOME,HOME/"replication"]
def write(name,obj):
    path=ROOT/name;data=json.dumps(obj,ensure_ascii=False,sort_keys=True,separators=(",",":")).encode("utf8")+b"\n"
    if name.endswith(".gz"):data=gzip.compress(data,mtime=0)
    if path.exists():assert path.read_bytes()==data,name
    else:path.write_bytes(data)
def allranks(method):
    if method=="dense":
        return {r["query"]:(r["shard"],r["trajectory"],r["ranking"]) for r in load(HOME/"dense/ranked.json.gz")}
    ret={}
    for i,p in enumerate(PANELS):
        tid={r["query"]:r["trajectory"] for r in load(p/"selections.json.gz")}
        for r in load(p/"native-ranks.json.gz"):
            if r["v"]=="provenance":ret[r["q"]]=(i,tid[r["q"]],r["ranking"])
    return ret
def produce(method):
    ranks=allranks(method);pending=collections.defaultdict(list);targets={}
    for q,(i,tid,nodes) in ranks.items():
        targets[q]={}
        for b in pilot.BUDGETS:
            used=0;idx=0
            while idx<len(nodes) and used+nodes[idx]["token_count"]<=b:
                used+=nodes[idx]["token_count"];idx+=1
            targets[q][str(b)]={"prefix_length":idx,"used":used,"partial":None}
            if idx<len(nodes) and used<b:
                node=nodes[idx]
                spans=node["source_spans"]
                assert len(spans)==1
                span=spans[0]
                pending[i,tid,span["event_id"]].append((q,b,b-used,node,span))
    tokenizer=pilot.Tokenizer.from_file(str(pilot.CACHE/"tokenizer.json"))
    solved=0
    for i,p in enumerate(PANELS):
        selected=load(p/"cohort.json")["selected"]
        target_tids={t for j,t,e in pending if j==i}
        for raw,data in pilot.stream(pilot.SHARD.parent/f"trajectories-{i:05d}.jsonl"):
            tid=data["session_id"]
            if tid not in target_tids:continue
            assert hashlib.sha256(raw).hexdigest()==selected[tid]["record_sha"]
            src={}
            for msg in data["messages"]:
                for tc in msg.get("tool_calls") or []:src[f"{tid}:call:{tc['id']}"]=tc["function"]["arguments"]
                if msg["role"]=="tool":src[f"{tid}:output:{msg['tool_call_id']}"]=msg["content"]
            for ev,txt in src.items():
                work=pending.get((i,tid,ev))
                if not work:continue
                offsets=[(a,b) for a,b in tokenizer.encode(txt,add_special_tokens=False).offsets if b>a]
                for q,b,left,node,span in work:
                    pos=int(node["node_id"].rsplit(":chunk:",1)[1])*440
                    size=min(504,len(offsets)-pos)
                    assert size==node["token_count"] and 0<left<size
                    start=offsets[pos][0] if pos else 0
                    end=len(txt) if pos+size==len(offsets) else offsets[pos+size][0]
                    assert span["char_start"]==start and span["char_end"]==end
                    new_end=offsets[pos+left][0]
                    assert start<new_end<=end
                    partial={**node,"node_id":node["node_id"]+"#prefix:"+str(left),"token_count":left,"source_spans":[{**span,"char_end":new_end}]}
                    cell=targets[q][str(b)]
                    assert cell["partial"] is None and cell["used"]+left==b
                    cell["partial"]=partial;cell["used"]=b;solved+=1
    assert solved==sum(len(v) for v in pending.values()),(solved,len(pending))
    name=method+"-selections.json.gz";write(name,targets)
    write(method+"-seal.json",{n:pilot.sha(ROOT/n) for n in ("clip.py","PROTOCOL_RU.md",name)})
    print(method,len(targets),"partial",solved,flush=True)
def score(method):
    for n,h in load(ROOT/(method+"-seal.json")).items():assert pilot.sha(ROOT/n)==h
    targets=load(ROOT/(method+"-selections.json.gz"));ranks=allranks(method)
    gold={k:v for p in PANELS for k,v in load(p/"gold-spans.json.gz").items() if k in ranks}
    if method=="dense":
        base=[r for r in load(HOME/"dense/outcomes.json.gz") if r["ranker"]=="dense"]
    else:base=[dict(r,shard=i) for i,p in enumerate(PANELS) for r in load(p/"outcomes.json.gz") if r["view"]=="provenance"]
    out=[]
    for q,bb in targets.items():
        i,tid,rank=ranks[q]
        for b,plan in bb.items():
            selected=rank[:plan["prefix_length"]]+([plan["partial"]] if plan["partial"] is not None else [])
            expected=metrics(gold[q],selected)
            nodes=tuple(pilot.RankedNodeRecord.model_validate(n) for n in selected)
            g=tuple(pilot.SourceSpan.model_validate(v) for v in gold[q])
            result=pilot.span_metrics_under_token_budget(nodes,g,int(b))
            assert all(abs(getattr(result,k)-v)<1e-12 for k,v in zip(("coverage","density","full_support"),expected,strict=True))
            out.append(dict(query=q,trajectory=tid,budget=int(b),shard=i,policy="clip",tokens=plan["used"],nodes=len(selected),**dataclasses.asdict(result)))
    write(method+"-outcomes.json.gz",out)
    stats={}
    for i in (0,1):
        for b in pilot.BUDGETS:
            clip={r["query"]:r for r in out if r["shard"]==i and r["budget"]==b}
            studies={}
            for h in ("prefix","skip","value","related"):
                rhs={r["query"]:r for r in base if r["policy"]==h and r["shard"]==i and r["budget"]==b}
                studies[h+"-clip"]=matched(rhs,clip)
            stats[f"{i}/{b}"]={"clip":summary(list(clip.values())),"matched":studies}
    write(method+"-results.json",stats)
    print(method,[(k,v["clip"]["full"],v["clip"]["tokens"],v["matched"]["skip-clip"]) for k,v in stats.items() if k.endswith("/2048")],flush=True)
if __name__=="__main__":{"rank":produce,"score":score}[sys.argv[1]](sys.argv[2])
