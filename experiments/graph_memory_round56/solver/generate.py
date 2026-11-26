"""Prepare equal-token queries and run the pinned, deterministic single-slot GPU reader."""
import os
import struct
import sys
import time
from study import *
sys.path.insert(0,str(R52/"reranker"))
import common
PARAMS=dict(temperature=0,top_k=1,seed=560271,n_predict=640,cache_prompt=False,stream=False)
def key(tokens):return digest(struct.pack(f"<{len(tokens)}I",*tokens))
def main():
    seal=read("selection-seal.json")
    assert all(digest((HERE/k).read_bytes())==v for k,v in seal["hashes"].items())
    common.RUN=RAW;selected=read("selections.json.gz")
    expected=common.read(R52/"global_answers/confirm/input-seal.json")
    assert common.sha(common.READER)==expected["reader"] and common.sha(common.EXE)==expected["server"]
    with common.server(common.READER,["--parallel","1","--ctx-size","4096","--flash-attn","on","--threads","4"],"reader",18956) as (url,s,hw):
        def tok(t,special=False):
            req=s.post(url+"/tokenize",json=dict(content=t,parse_special=special,add_special=False),timeout=30)
            req.raise_for_status();return req.json()["tokens"]
        sysmsg=tok("<|im_start|>system\nImplement the requested public Python function in its existing library. Return just the complete Python function definition. Do not use Markdown or tests. Match the stated contract; you may use existing module helpers or Python standard library imports inside the function.<|im_end|>\n<|im_start|>user\n",True)
        mark=tok("\nPreviously observed test source from this repository:\n")
        suffix=tok("<|im_end|>\n<|im_start|>assistant\n",True)
        prompts={};assign={};view={}
        for q,rec in sorted(selected.items()):
            t=rec["task"]
            pre=sysmsg+tok(t["repo"]+" — "+t["path"]+"\n"+t["question"])
            # Capture exact text and token IDs that the actor can actually see.
            obs={a:e["path"]+" / "+e["name"]+"\n"+e["text"] for a,e in rec["evidence"].items()}
            parts={a:tok(text) for a,text in obs.items()};width=min(240,*(len(v) for v in parts.values()))
            assert width>0
            variants={a:pre+mark+ids[:width]+suffix for a,ids in parts.items()}
            variants["contract"]=pre+suffix
            assert len(set(len(ids) for a,ids in variants.items() if a!="contract"))==1
            assign[q]={}
            decoded={}
            for a,seq in variants.items():
                h=key(seq);assert len(seq)+640<=4096 and prompts.setdefault(h,seq)==seq
                assign[q][a]=dict(hash=h,tokens=len(seq),evidence=width if a!="contract" else 0)
                if a!="contract":
                    r=s.post(url+"/detokenize",json={"tokens":parts[a][:width]},timeout=20);r.raise_for_status()
                    decoded[a]=r.json()["content"]
            view[q]=decoded
        write("assignments.json.gz",assign);write("prompts.json.gz",prompts);write("visible.json.gz",view)
        receipt=dict(n=len(assign),unique=len(prompts),params=PARAMS,model=expected["reader"],server=expected["server"],hardware=hw,
                     inputs=digest((HERE/"selection-seal.json").read_bytes()),prompts=digest((HERE/"prompts.json.gz").read_bytes()),
                     assignments=digest((HERE/"assignments.json.gz").read_bytes()),source=digest((HERE/"generate.py").read_bytes()))
        write("input-seal.json",receipt)
        answers={};log=RAW/("answers-"+receipt["prompts"]+".jsonl")
        if log.exists():
            answers=dict(json.loads(line) for line in log.read_bytes().splitlines())
        print("sealed",len(prompts),"prompts for",len(assign),"tasks",flush=True)
        with log.open("a",encoding="utf8") as f:
            for h,ids in sorted(prompts.items()):
                if h in answers:continue
                r=s.post(url+"/completion",json=dict(PARAMS,prompt=ids),timeout=100)
                r.raise_for_status();v=r.json()
                a=dict(text=v["content"],tokens=v["tokens_predicted"],stop=v["stop_type"])
                answers[h]=a;f.write(json.dumps([h,a],ensure_ascii=True)+"\n");f.flush()
                if len(answers)%20==0:print(len(answers),"/",len(prompts),flush=True)
        assert set(answers)==set(prompts)
        write("answers.json.gz",answers)
        write("answer-seal.json",dict(answers=digest((HERE/"answers.json.gz").read_bytes()),
                 input=digest((HERE/"input-seal.json").read_bytes()),n=len(answers),tokens=sum(x["tokens"] for x in answers.values())))
if __name__=="__main__":
    main()
