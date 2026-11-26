"""Fill only uncached equal-budget prompts using the original local Qwen reader."""
from common import D,BASE,DATA,raw,digest,put,source,R50
from complete_answers import READER,SERVER,MODEL,token_hash,generate
import hashlib
import socket
import subprocess
import time
from pathlib import Path
import requests

URL="http://127.0.0.1:18896"
SCRATCH=Path("D:/CodexResearch/x20-r51-pairwise-completion")

def prepare(session):
    choices=raw(D/"choices.json.gz")
    assert digest(D/"choices.json.gz")==raw(D/"decision-seal.json")["choices"]
    contexts={};needed={};all_answers={};checks={}
    for panel,(root,scratch) in DATA.items():
        _,previous,more_prompts,more_answers=source(panel)
        oldp=raw(root/"prompts.json.gz");olda=raw(root/"answers.json.gz")
        prompts={**oldp,**more_prompts};all_answers.update(olda);all_answers.update(more_answers)
        tail=raw(root/"reader-boundaries.json")["tail"]
        view=raw(scratch/"visible.json.gz")
        assert digest(scratch/"visible.json.gz")==raw(root/"panel.json")["visible"]
        rows={};eligible=set()
        for q,c in choices[panel].items():
            ref=previous[q];limit=ref["n" if panel=="2wiki" else "cap"]
            seed=ref["first" if panel=="2wiki" else "seed"]
            known={i:(k,prompts[k]) for i,k,_ in ref["refs"].values()}
            doc_id=ref["refs"]["graph"][0];cur=known[doc_id][1]
            prefix=cur[:len(cur)-len(tail)-limit];eligible.update(v[0] for v in known.values())
            second={i:ts[len(prefix):-len(tail)] for i,(k,ts) in known.items()}
            assert all(prefix+ts+tail==known[i][1] and len(ts)==limit for i,ts in second.items())
            acts={a:c[a] for a in ("graph","masked","hybrid")}
            extra=set(acts.values())-set(known)
            if extra:
                texts={i:t+"\n"+b for i,t,b in view[q][1]}
                for i in extra|{doc_id}:
                    rsp=session.post(URL+"/tokenize",json={"content":texts[i],"add_special":False,"parse_special":False},timeout=20)
                    rsp.raise_for_status();v=rsp.json()["tokens"][:192]
                    if i in known:assert v[:limit]==second[i]
                    else:second[i]=v
            cap=min([limit]+[len(second[i]) for i in acts.values()])
            refs={}
            for a,i in acts.items():
                ts=prefix+second[i][:cap]+tail;k=token_hash(ts)
                if k in prompts:assert prompts[k]==ts
                else:assert needed.setdefault(k,ts)==ts
                refs[a]=[i,k,len(ts)]
            rows[q]={"seed":seed,"original":limit,"cap":cap,"refs":refs,"edge":c["edge"],
                     "cluster":ref["cluster"],"prefix":token_hash(prefix),"suffix":token_hash(tail)}
        contexts[panel]=rows
        pick=sorted(eligible,key=lambda k:hashlib.sha256(("r51-mask-control|"+k).encode()).hexdigest())[:6]
        checks[panel]={k:prompts[k] for k in pick}
    put("contexts.json.gz",contexts);put("new-prompts.json.gz",needed)
    put("input-seal.json",{"code":digest(D/"run_reader.py"),"contexts":digest(D/"contexts.json.gz"),
                          "choices":digest(D/"choices.json.gz"),"new":digest(D/"new-prompts.json.gz"),
                          "replay":{p:list(rows) for p,rows in checks.items()},"params":READER})
    return needed,all_answers,checks


def main():
    plan=raw(R50.parent/"graph_memory_round46/reader_transfer/plan.json")
    assert digest(SERVER)==plan["server"] and digest(MODEL)==plan["model"]
    with socket.socket() as probe:probe.bind(("127.0.0.1",18896))
    args=[str(SERVER),"-m",str(MODEL),"--host","127.0.0.1","--port","18896","--parallel","1","--ctx-size","1024",
          "--n-gpu-layers","all","--flash-attn","on","--threads","4","--no-warmup"]
    with (SCRATCH/"frozen-ablation-server.log").open("wb") as log, requests.Session() as client:
        client.trust_env=False
        proc=subprocess.Popen(args,stdout=log,stderr=log,creationflags=subprocess.CREATE_NO_WINDOW)
        try:
            for _ in range(150):
                if proc.poll() is not None:raise RuntimeError("reader terminated")
                try:
                    if client.get(URL+"/health",timeout=1).ok:break
                except requests.RequestException:pass
                time.sleep(.4)
            else:raise TimeoutError()
            props=client.get(URL+"/props",timeout=10).json()
            assert props["build_info"]==plan["props"]["build_info"] and props["total_slots"]==1 and Path(props["model_path"])==MODEL
            assert hashlib.sha256(props["chat_template"].encode()).hexdigest()==plan["chat_template"]
            apps=subprocess.check_output(["nvidia-smi","--query-compute-apps=pid,name","--format=csv,noheader"],text=True)
            assert any(v.startswith(str(proc.pid)+",") and v.endswith("llama-server.exe") for v in apps.splitlines())
            gpu=subprocess.check_output(["nvidia-smi","--query-gpu=name,driver_version","--format=csv,noheader"],text=True).strip()
            need,old,replay=prepare(client)
            print("Sealed",len(need),"new prompts",flush=True)
            checks={}
            for p,part in replay.items():
                checks[p]={}
                for k,ts in part.items():
                    got=generate(client,ts);assert got==old[k]
                    checks[p][k]=got
            new={k:generate(client,ts) for k,ts in sorted(need.items())}
            put("replay.json",checks);put("new-answers.json.gz",new)
            put("answer-seal.json",{"inputs":digest(D/"input-seal.json"),"answers":digest(D/"new-answers.json.gz"),
                                   "replay":digest(D/"replay.json"),"device":gpu,"build":props["build_info"],
                                   "model":plan["model"],"binary":plan["server"],"n":len(new)})
        finally:
            if proc.poll() is None:proc.terminate();proc.wait(timeout=30)
    print("Completed new answers and replay controls")
if __name__=="__main__":main()
