"""Replay exact R50 reader prompts and fill remaining paired policy answers."""
import hashlib
import json
from pathlib import Path
import socket
import struct
import subprocess
import time
import requests
from study import HERE, SOURCE, raw, save, digest


SCRATCH=Path("D:/CodexResearch/x20-r51-pairwise-completion")
SCRATCH.mkdir(exist_ok=True)
SERVER=Path("D:/CodexResearch/x20-qwen38-27b/bin/llama-server.exe")
MODEL=Path("D:/CodexResearch/x20-published-output-audit/Qwen3-4B-Instruct-2507-Q4_K_M.gguf")
PANELS={
    "adaptive_address": (SOURCE/"adaptive_address",Path("D:/CodexResearch/x20-r50-adaptive-address")),
    "gate_confirmation": (SOURCE/"gate_confirmation",Path("D:/CodexResearch/x20-r50-gate-confirmation")),
    "hotpot": (HERE.parent/"transfer",Path("D:/CodexResearch/x20-r51-hotpot-gate")),
}
HOST="http://127.0.0.1:18896"
READER=dict(temperature=0,top_k=1,seed=460001,n_predict=96,cache_prompt=False,
            ignore_eos=False,stop=["\n"],stream=False)


def token_hash(tokens):
    return hashlib.sha256(struct.pack(f"<{len(tokens)}I",*tokens)).hexdigest()


def prepare(session):
    sel=raw(HERE/"decisions.json.gz")
    assert digest(HERE/"decisions.json.gz")==raw(HERE/"decision-seal.json")["decisions"]
    assert digest(HERE/"hotpot-decisions.json.gz")==raw(HERE/"hotpot-decision-seal.json")["choices"]
    sel["hotpot"]=raw(HERE/"hotpot-decisions.json.gz")
    mats,need,cached,replay={},{},{},{}
    for name,(path,scratch) in PANELS.items():
        print("prepare",name,flush=True)
        old=raw(path/"contexts.json.gz")
        prompts=raw(path/"prompts.json.gz")
        answers=raw(path/"answers.json.gz")
        assert digest(path/"answers.json.gz")==raw(path/"answer-seal.json")["answers"]
        assert set(answers)==set(prompts)
        for k,ts in prompts.items():
            assert k==token_hash(ts)
            assert cached.setdefault(k,answers[k])==answers[k]
        keys=sorted(prompts,key=lambda k:hashlib.sha256(("r51-frozen-replay|"+k).encode()).hexdigest())[:12]
        replay[name]={k:prompts[k] for k in keys}
        visible=raw(scratch/"visible.json.gz")
        assert digest(scratch/"visible.json.gz")==raw(path/"panel.json")["visible"]
        tail=raw(path/"reader-boundaries.json")["tail"]
        df={}
        for q,actions in sel[name].items():
            first=old[q]["seed"];previous=old[q]["n"]
            ref=old[q]["refs"]["dense"]
            ts=prompts[ref[1]]
            prefix=ts[:len(ts)-previous-len(tail)]
            assert ts[-len(tail):]==tail
            saved={i:(k,prompts[k]) for i,k,L in old[q]["refs"].values()}
            extra=set(actions.values())-set(saved)
            second={i:v[len(prefix):len(v)-len(tail)] for i,(k,v) in saved.items()}
            assert all(len(v)==previous for v in second.values())
            assert all(prefix+t+tail==saved[i][1] for i,t in second.items())
            if extra:
                catalog={i:(t,b) for i,t,b in visible[q][1]}
                for i in set(saved)|extra:
                    text="\n".join(catalog[i])
                    req=session.post(HOST+"/tokenize",json={"content":text,"parse_special":False,"add_special":False},timeout=30)
                    req.raise_for_status()
                    encoded=req.json()["tokens"][:192]
                    if i in saved:
                        assert encoded[:previous]==second[i]
                    else:
                        second[i]=encoded
            n=min([previous]+[len(second[i]) for i in actions.values()])
            refs={}
            for policy,i in actions.items():
                assert i!=first
                ts_new=prefix+second[i][:n]+tail
                k=token_hash(ts_new)
                if k not in cached:
                    assert need.setdefault(k,ts_new)==ts_new
                refs[policy]=[i,k,len(ts_new)]
            assert len({x[2] for x in refs.values()})==1
            df[q]={"first":first,"original_n":previous,"n":n,"cluster":old[q]["cluster"],
                   "prefix":token_hash(prefix),"tail":token_hash(tail),"refs":refs}
        mats[name]=df
    save("matched-contexts.json.gz",mats)
    save("new-prompts.json.gz",need)
    save("replay-prompts.json.gz",replay)
    save("completion-input-seal.json",{"complete_protocol":digest(HERE/"COMPLETION_PROTOCOL_RU.md"),
                "hotpot_protocol":digest(HERE/"HOTPot_PROTOCOL_RU.md"),"decisions":digest(HERE/"decisions.json.gz"),
                "hotpot_decisions":digest(HERE/"hotpot-decisions.json.gz"),"script":digest(Path(__file__)),
                "contexts":digest(HERE/"matched-contexts.json.gz"),"prompts":digest(HERE/"new-prompts.json.gz"),
                "replay":digest(HERE/"replay-prompts.json.gz"),"reader_params":READER})
    return need,cached,replay


def generate(session,ts):
    response=session.post(HOST+"/completion",json=dict(READER,prompt=ts),timeout=100)
    response.raise_for_status()
    r=response.json()
    return {"answer":r["content"].strip(),"tokens":r["tokens_predicted"],"stop":r["stop_type"]}


def main():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1",18896))
    archive=raw(SOURCE.parent/"graph_memory_round46/reader_transfer/plan.json")
    assert digest(MODEL)==archive["model"] and digest(SERVER)==archive["server"]
    args=[str(SERVER),"-m",str(MODEL),"--host","127.0.0.1","--port","18896","--parallel","1",
          "--ctx-size","1024","--n-gpu-layers","all","--flash-attn","on","--threads","4","--no-warmup"]
    with (SCRATCH/"server.log").open("wb") as log, requests.Session() as session:
        session.trust_env=False
        run=subprocess.Popen(args,stdout=log,stderr=log,creationflags=subprocess.CREATE_NO_WINDOW)
        try:
            for _ in range(150):
                if run.poll() is not None: raise RuntimeError("reader process terminated")
                try:
                    if session.get(HOST+"/health",timeout=1).ok: break
                except requests.RequestException: pass
                time.sleep(.4)
            else: raise TimeoutError("reader did not start")
            props=session.get(HOST+"/props",timeout=10).json()
            assert props["total_slots"]==1 and props["build_info"]==archive["props"]["build_info"]
            assert Path(props["model_path"])==MODEL
            assert hashlib.sha256(props["chat_template"].encode()).hexdigest()==archive["chat_template"]
            gpu=subprocess.check_output(["nvidia-smi","--query-gpu=name,driver_version,memory.total","--format=csv,noheader"],text=True).strip()
            apps=subprocess.check_output(["nvidia-smi","--query-compute-apps=pid,name","--format=csv,noheader"],text=True)
            assert any(s.startswith(str(run.pid)+",") and s.endswith("llama-server.exe") for s in apps.splitlines())
            need,known,replay=prepare(session)
            print("Sealed",len(need),"new unique prompts,",sum(map(len,replay.values())),"replay checks",flush=True)
            check={}
            for p,rows in replay.items():
                check[p]={}
                for k,ts in rows.items():
                    observed=generate(session,ts)
                    check[p][k]={"expected":known[k],"observed":observed}
                    assert observed==known[k],(p,k,observed,known[k])
            save("reader-replay.json",check)
            outputs={}
            start=time.perf_counter()
            for k,ts in sorted(need.items()):
                outputs[k]=generate(session,ts)
            save("new-answers.json.gz",outputs)
            save("completion-answer-seal.json",{"inputs":digest(HERE/"completion-input-seal.json"),
                     "outputs":digest(HERE/"new-answers.json.gz"),"replay":digest(HERE/"reader-replay.json"),
                     "n_new":len(need),"replay_count":sum(map(len,replay.values())),"gpu":gpu,"process":SERVER.name,
                     "model":archive["model"],"server":archive["server"],"build":props["build_info"],
                     "seconds_new":time.perf_counter()-start})
            print("Completed",len(outputs),"new answers",flush=True)
        finally:
            if run.poll() is None:
                run.terminate()
                run.wait(timeout=30)


if __name__=="__main__":
    main()
