"""Identical-context auxiliary stratum; uses the frozen primary safety and rendering functions."""
import sys
from collections import Counter
from pathlib import Path
import reader as r

BASE=r.ROOT
OUT=BASE/"matched_controls"
CACHE=r.PRIVATE/"matched_controls"
def lock():
    r.save(OUT/"design-lock.json",{name:r.pilot.sha(BASE/name) for name in ("reader.py","controls.py","CONTROL_PROTOCOL_RU.md","panel-lock.json","panel.json.gz","design-lock.json")})
def prepare():
    for f,sha in r.load(OUT/"design-lock.json").items():assert r.pilot.sha(BASE/f)==sha
    prior={row["t"] for row in r.load(BASE/"panel.json.gz").values()}
    assert len(prior)==27
    original=r.load(r.OFF/"cohort.json");old=set(r.load(r.OFF/"sensitivity-excluded-ids.json"))
    eligible={a["query_id"] for a in original if a["memory_mode"]=="direct_recall" and a["trajectory_id"] not in prior and a["query_id"] not in old}
    questions={row["id"]:row["query"] for _,row in r.pilot.stream(r.pilot.Q) if row["id"] in eligible and not r.excluded(row["query"])}
    counts=Counter(new_direct_not_primary=len(eligible),question_filter_pass=len(questions))
    locked=r.load(r.OFF/"forecast-lock.json")["forecasts"];selected={}
    for i in range(8):
        fname=f"forecasts-shard-{i}.jsonl.gz"
        assert r.pilot.sha(r.OFF/fname)==locked[fname]
        candidates={}
        for rec in r.streamgz(r.OFF/fname):
            subset={}
            for q,v in rec["queries"].items():
                if q in questions and set(v["provenance"]["arms"]["related"])==set(v["provenance"]["arms"]["value"]):subset[q]=v["provenance"]
            if subset:candidates[rec["trajectory_id"]]=(rec["source_record_sha256"],subset)
        counts["equal_sets"]+=sum(len(u[1]) for u in candidates.values())
        for raw,row in r.pilot.stream(r.RAW/f"trajectories-{i:05d}.jsonl"):
            t=row["session_id"]
            if t not in candidates:continue
            digest,opts=candidates[t];assert r.h(raw)==digest
            intent=" ".join(a["natural_language_intent"] for a in row["source_intents"])
            if r.excluded(intent):continue
            tr=r.adapt_isetrace_record(r.parse_isetrace_record(row),source_revision=r.pilot.RAW[1])
            ev={e.event_id:e for e in (*tr.tool_calls,*tr.tool_outputs)}
            for q,pu in sorted(opts.items(),key=lambda i:r.priority(i[0])):
                if not r.BENIGN.search(questions[q]+" "+intent):continue
                counts["intent_topic_pass"]+=1
                shape={}
                for node in pu["ranked"]:
                    k=node["node_id"];s=node["source_spans"][0];assert len(node["source_spans"])==1
                    e=ev[s["event_id"]]
                    shape[k]=((e.position.message_index,e.position.sub_index,s["char_start"],k),node,e)
                ids={k:j for j,k in enumerate(sorted(shape,key=lambda k:shape[k][0]),1)}
                visible=sorted(pu["arms"]["related"],key=ids.__getitem__);bits=[];coords=[]
                for k in visible:
                    _,node,e=shape[k];s=node["source_spans"][0];rawtext=e.content if s["json_pointer"]=="/content" else e.raw_arguments
                    chunk=rawtext[s["char_start"]:s["char_end"]]
                    if r.excluded(chunk):break
                    bits.append({"id":ids[k],"text":chunk})
                    coords.append({"id":ids[k],"node":k,"text_sha256":r.h(chunk.encode()),"token_count":node["token_count"],"spans":node["source_spans"]})
                else:
                    counts["fragments_filter_pass"]+=1
                    p=r.payload(questions[q],bits)
                    if len(r.stable(p))>42000:continue
                    key=r.h(r.stable(p));first=next(n["node_id"] for n in pu["ranked"] if n["node_id"] in visible)
                    mapped={"prompt_sha256":key,"bm25_id":ids[first],"e5_tokens":sum(a["token_count"] for a in coords),"fragments":coords}
                    counts["eligible_queries"]+=1
                    if t not in selected:selected[t]=(q,p,{"t":t,"arms":{v:mapped for v in ("related","value")}})
        print("control shard",i,"eligible trajectories",len(selected),flush=True)
    panel={};private={}
    for t in sorted(selected,key=r.priority)[:13]:
        q,p,record=selected[t];panel[q]=record;private[r.h(r.stable(p))]=p
    assert len(panel)==len(private)
    counts["eligible_trajectories"]=len(selected);counts["assigned_trajectories"]=len(panel)
    r.save(OUT/"panel.json.gz",panel);r.save(OUT/"selection.json",dict(counts));r.save(CACHE/"payloads.json.gz",private)
    r.save(OUT/"panel-lock.json",{"panel":r.pilot.sha(OUT/"panel.json.gz"),"private_payloads":r.pilot.sha(CACHE/"payloads.json.gz"),
                               "design":r.pilot.sha(OUT/"design-lock.json"),"selection":dict(counts)})
    print("assigned controls",len(panel),dict(counts),flush=True)
def infer():
    r.ROOT=OUT;r.PRIVATE=CACHE;r.infer()
if __name__=="__main__":{"lock":lock,"prepare":prepare,"infer":infer}[sys.argv[1]]()
