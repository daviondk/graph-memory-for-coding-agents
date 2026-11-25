"""Build train-only provenance and exact target spans. Text is local, outside git."""
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor
import hashlib
import os
from pathlib import Path
import sys
os.environ["RAYON_NUM_THREADS"]="2"
D=Path(__file__).resolve().parent;OLD=D.parents[1]/"graph_memory_round19";PRIVATE=Path("D:/CodexResearch/x20-isetrace-fine-train")
sys.path.insert(0,str(D.parent/"fine_read"));import reader
sys.path.insert(0,str(OLD/"trained_rank"))
# The name prepare would collide when imported; load the pinned R19 module by file path.
import importlib.util
spec=importlib.util.spec_from_file_location("r19_prepare",OLD/"trained_rank/prepare.py");up=importlib.util.module_from_spec(spec);spec.loader.exec_module(up)
from reader import load,save,sha,stream,key
def build(i):
    by=defaultdict(set)
    for r in load(OLD/"trained_rank/split.json.gz")["train"]:by[r["t"]].add(r["q"])
    ask={q for qs in by.values() for q in qs}
    ex={q["id"]:up.N._QUERY_ADAPTER.validate_python(q) for _,q in up.pilot.stream(up.pilot.Q) if q["id"] in ask}
    file=up.RAW/f"trajectories-{i:05d}.jsonl";assert sha(file)==next(r["sha256"] for r in load(up.OFF/"source-lock.json") if r["path"]=="trajectories/"+file.name)
    tokenizer=stream.Tokenizer.from_file(str(stream.TOKENIZER));entries={};counts=[0,0,0]
    for raw,obj in up.pilot.stream(file):
        t=obj["session_id"]
        if t not in by:continue
        p=load(up.RUN/"projection/train"/(t+".json.gz"));assert p["digest"]==hashlib.sha256(raw).hexdigest()
        tr=up.adapt_isetrace_record(up.parse_isetrace_record(obj),source_revision=up.pilot.RAW[1]);assert tr.trajectory_id==t
        fields={**{e.event_id:e.raw_arguments for e in tr.tool_calls},**{e.event_id:e.content for e in tr.tool_outputs}}
        ad,bl,_,_=stream.stream_blocks(fields,p["pool"],tokenizer)
        targets={};query={r["q"]:r for r in p["qs"]};assert set(query)==by[t]
        for q in sorted(by[t]):
            m=up.N._match_task_text(ex[q],tr);assert m is not None
            gold=tuple(up.N._resolve_gold_spans(ex[q],m));intervals=defaultdict(list)
            for s in gold:intervals[s.event_id,s.json_pointer].append((s.char_start,s.char_end))
            pos={c["item_id"] for c in p["pool"] for s in c["source_spans"] if any(s["char_start"]<h and l<s["char_end"] for l,h in intervals.get((s["event_id"],s["json_pointer"]),()))}
            assert pos==set(query[q]["positive"])
            target=[j for j,(e,a,b,c,_) in enumerate(bl) if any(a<h and l<b for l,h in intervals.get(tuple(ad[e]),()))]
            assert target;targets[q]=target
        path=PRIVATE/f"{i}-{t}.json.gz";save(path,{"t":t,"fields":fields,"addresses":ad,"blocks":bl,"targets":targets})
        entries[t]=sha(path);counts[0]+=len(targets);counts[1]+=len(bl);counts[2]+=sum(len(v) for v in targets.values())
    save(D/f"inventory-{i}.json",{"files":entries,"counts":counts});return counts
if __name__=="__main__":
    with ProcessPoolExecutor(2) as ex:r=list(ex.map(build,range(8)))
    assert sum(a[0] for a in r)==3894
    save(D/"data-lock.json",{"n":3894,"shards":{f"inventory-{i}.json":sha(D/f"inventory-{i}.json") for i in range(8)},"raw_code":sha(D/"prepare.py"),"protocol":sha(D/"PROTOCOL_RU.md")})
