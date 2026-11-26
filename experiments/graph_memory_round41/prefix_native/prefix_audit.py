"""Physically remove future raw messages before the official dataset adapter.

No query, embedding, checkpoint, model output or gold is read.
"""
from collections import Counter
import sys
from shared import D, W, OFF, C, read, save, sha
import os
os.environ["CUDA_VISIBLE_DEVICES"]="-1"
os.environ["TOKENIZERS_PARALLELISM"]="false"
os.environ["RAYON_NUM_THREADS"]="1"
sys.path.insert(0,str(OFF))
import inputs as official
from graph_memory.graphs.provenance import build_provenance_graph
from graph_memory.datasets.isetrace.adapter import adapt_isetrace_record, parse_isetrace_record


def raw_prefix(t, messages, step):
    prefix=[]
    count=0
    calls=0
    for msg in messages:
        if count > step:
            break
        prefix.append(msg)
        added=len(msg.get("tool_calls",())) if msg["role"]=="assistant" else 0
        count+=1+added
        calls+=added
    assert count==step+1 and prefix[-1]["role"]=="tool"
    return dict(status="as-of",session_id=t,source_intent_count=1,source_intent_ids=["as-of"],
        source_intents=[dict(intent_id="as-of",natural_language_intent="as-of")],
        session_finalized_by_intent_id="as-of",total_steps=calls,enable_thinking=False,
        messages=prefix,tools=[],final_output="",intent_id="as-of",metadata={})


def main():
    reg=read(D/"registration.json")
    audit=set(reg["terminal_panel"])
    historical=official.graphfiles()
    tok=official.pilot.offsets(official.pilot.Tokenizer.from_file(str(official.pilot.CACHE/"tokenizer.json")))
    def chunk(text):
        return official.pilot.token_chunks(text,tokenizer=tok,max_tokens=504,overlap_tokens=64)
    checked=[]
    locks={r["path"]:r["sha256"] for r in read(official.R18/"isetrace_official/source-lock.json")}
    for sh in range(8):
        state=C/f"state-{sh}.json.gz"
        assert sha(state)==read(C/f"state-{sh}-seal.json")["data"]
        steps={(t,cut):step for q,t,cut,step,*rest in read(state) if cut==50 or (cut==100 and t in audit)}
        path=official.RAW/f"trajectories-{sh:05d}.jsonl"
        assert sha(path)==locks["trajectories/"+path.name]
        for _,raw in official.pilot.stream(path):
            t=raw["session_id"]
            for cut in (50,100):
                if (t,cut) not in steps:
                    continue
                step=steps[t,cut]
                clipped=raw_prefix(t,raw["messages"],step)
                trajectory=adapt_isetrace_record(parse_isetrace_record(clipped),source_revision=official.pilot.RAW[1])
                assert len(trajectory.events)==step+1 and not trajectory.final_response
                trajectory=trajectory.model_copy(update={"source_metadata":None})
                g=build_provenance_graph(trajectory,content_chunker=chunk)
                if cut==100:
                    f,digest=historical[t]
                    assert sha(f)==digest
                    saved=read(f)["g"]
                    output=g.model_dump(mode="json")
                    assert output["nodes"]==saved["nodes"] and output["edges"]==saved["edges"]
                checked.append([t,cut,step,len(g.nodes),len(g.edges),g.fingerprint()])
        print("raw prefix audit",sh,len(checked),flush=True)
    assert len(checked)==1255
    save(D/"prefix-audit.json.gz",checked)
    save(D/"prefix-audit-seal.json",dict(graphs=sha(D/"prefix-audit.json.gz"),registered=sha(D/"registration.json"),
        raw_prefix_models=1207,terminal_public_graphs=48,program=sha(D/"prefix_audit.py")))


if __name__=="__main__":
    main()
