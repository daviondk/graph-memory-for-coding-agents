"""One prospective replication of the already fitted visible-title policies on HotpotQA."""
import argparse
import collections
import hashlib
import json
from pathlib import Path
import socket
import subprocess
import sys
import time

import requests

D=Path(__file__).resolve().parent
BASE=D.parent
sys.path.insert(0,str(BASE))
from study import raw, digest, ci_records
from complete_answers import SERVER,MODEL,READER,token_hash,generate
from hotpot_select import decisions
from grade_complete import module
from verify import score
import numpy as np
import gzip

ROUTE=BASE.parent/"routing"
SCRATCH=Path("D:/CodexResearch/x20-r51-hotpot-routing")
RUNTIME=Path("D:/CodexResearch/x20-r51-pairwise-completion")
R50=BASE.parents[1]/"graph_memory_round50"


def put(name,data):
    b=(json.dumps(data,sort_keys=True,ensure_ascii=True,indent=None if name.endswith(".gz") else 2,
                  allow_nan=False)+"\n").encode()
    (D/name).write_bytes(gzip.compress(b,compresslevel=9,mtime=0) if name.endswith(".gz") else b)


def select():
    for x,h in raw(D/"fixed.json").items():
        assert digest(BASE.parent/x)==h
    ranks,lex=[raw(ROUTE/x) for x in ("orders.json.gz","lex-orders.json.gz")]
    flags=raw(ROUTE/"flags.json.gz")
    assert digest(ROUTE/"flags.json.gz")==raw(ROUTE/"panel.json")["flags"]
    assert len(ranks)==len(lex)==len(flags)==1280
    assert not set(ranks)&set(raw(BASE/"hotpot-decisions.json.gz"))
    pred=decisions(ranks,lex,raw(BASE/"model.json"))
    for q,r in pred.items():
        r["router"]=r["dense"] if flags[q] else r["linked"]
    put("choices.json.gz",pred)
    put("predictions-seal.json",{"fixed":digest(D/"fixed.json"),"script":digest(Path(__file__)),
                                "choices":digest(D/"choices.json.gz"),"flags":digest(ROUTE/"flags.json.gz"),
                                "orders":digest(ROUTE/"orders.json.gz"),"lex":digest(ROUTE/"lex-orders.json.gz")})
    print("Sealed",len(pred),"predictions",digest(D/"choices.json.gz"))


def inputs(session):
    assert digest(D/"choices.json.gz")==raw(D/"predictions-seal.json")["choices"]
    choices=raw(D/"choices.json.gz")
    old=raw(ROUTE/"contexts.json.gz")
    old_prompts=raw(ROUTE/"prompts.json.gz")
    old_ans=raw(ROUTE/"answers.json.gz")
    assert digest(ROUTE/"answers.json.gz")==raw(ROUTE/"answer-seal.json")["answers"]
    for k,ts in old_prompts.items(): assert k==token_hash(ts)
    tail=raw(ROUTE/"reader-boundaries.json")["tail"]
    visible=raw(SCRATCH/"visible.json.gz")
    assert digest(SCRATCH/"visible.json.gz")==raw(ROUTE/"panel.json")["visible"]
    examples={}
    need={}
    for q,modes in choices.items():
        orig=old[q];n=orig["n"]
        original={i:k for i,k,L in orig["refs"].values()}
        first_key=next(iter(original.values()))
        baseline=old_prompts[first_key];prefix=baseline[:len(baseline)-n-len(tail)]
        second={i:old_prompts[k][len(prefix):-len(tail)] for i,k in original.items()}
        for i,k in original.items():assert prefix+second[i]+tail==old_prompts[k] and len(second[i])==n
        targets=set(modes.values())
        if targets-set(original):
            cat={idx:t+"\n"+b for idx,t,b in visible[q][1]}
            for i in targets|set(original):
                rsp=session.post("http://127.0.0.1:18896/tokenize",json={"content":cat[i],"parse_special":False,"add_special":False},timeout=30)
                rsp.raise_for_status()
                tokens=rsp.json()["tokens"][:192]
                if i in second:assert second[i]==tokens[:n]
                else:second[i]=tokens
        cap=min(n,min(len(second[i]) for i in targets))
        refs={}
        for name,i in modes.items():
            assert i!=orig["seed"]
            ts=prefix+second[i][:cap]+tail
            k=token_hash(ts)
            refs[name]=[i,k,len(ts)]
            if k not in old_prompts: assert need.setdefault(k,ts)==ts
        assert len({v[2] for v in refs.values()})==1
        examples[q]={"seed":orig["seed"],"original":n,"cap":cap,"prefix":token_hash(prefix),"suffix":token_hash(tail),
                     "refs":refs,"cluster":orig["cluster"]}
    reps=sorted(old_prompts,key=lambda k:hashlib.sha256(("r51-confirm-replay|"+k).encode()).hexdigest())[:12]
    put("contexts.json.gz",examples);put("new-prompts.json.gz",need)
    put("input-seal.json",{"choices":digest(D/"choices.json.gz"),"ctx":digest(D/"contexts.json.gz"),
                           "prompts":digest(D/"new-prompts.json.gz"),"replay":reps,"params":READER,
                           "reference_inputs":digest(ROUTE/"input-seal.json")})
    return need,old_prompts,old_ans,reps


def run_reader():
    url="http://127.0.0.1:18896"
    with socket.socket() as sock:sock.bind(("127.0.0.1",18896))
    old=raw(R50.parent/"graph_memory_round46/reader_transfer/plan.json")
    assert digest(MODEL)==old["model"] and digest(SERVER)==old["server"]
    args=[str(SERVER),"-m",str(MODEL),"--host","127.0.0.1","--port","18896","--parallel","1","--ctx-size","1024",
          "--n-gpu-layers","all","--flash-attn","on","--threads","4","--no-warmup"]
    with (RUNTIME/"confirm-server.log").open("wb") as log, requests.Session() as session:
        session.trust_env=False
        proc=subprocess.Popen(args,stdout=log,stderr=log,creationflags=subprocess.CREATE_NO_WINDOW)
        try:
            for _ in range(150):
                if proc.poll() is not None: raise RuntimeError("reader exited")
                try:
                    if session.get(url+"/health",timeout=1).ok:break
                except requests.RequestException:pass
                time.sleep(.4)
            else: raise TimeoutError("reader timed out")
            props=session.get(url+"/props",timeout=10).json()
            assert props["total_slots"]==1 and Path(props["model_path"])==MODEL and props["build_info"]==old["props"]["build_info"]
            assert hashlib.sha256(props["chat_template"].encode()).hexdigest()==old["chat_template"]
            apps=subprocess.check_output(["nvidia-smi","--query-compute-apps=pid,name","--format=csv,noheader"],text=True)
            assert any(v.startswith(str(proc.pid)+",") and v.endswith("llama-server.exe") for v in apps.splitlines())
            device=subprocess.check_output(["nvidia-smi","--query-gpu=name,driver_version,memory.total","--format=csv,noheader"],text=True).strip()
            need,oldp,olda,reps=inputs(session)
            print("Sealed",len(need),"new prompts",flush=True)
            check={}
            for k in reps:
                x=generate(session,oldp[k])
                assert x==olda[k]
                check[k]=x
            put("replay.json",check)
            start=time.perf_counter()
            answers={k:generate(session,v) for k,v in sorted(need.items())}
            put("new-answers.json.gz",answers)
            put("answer-seal.json",{"inputs":digest(D/"input-seal.json"),"answers":digest(D/"new-answers.json.gz"),
                                   "replay":digest(D/"replay.json"),"n_new":len(answers),"new_seconds":time.perf_counter()-start,
                                   "model":old["model"],"binary":old["server"],"build":props["build_info"],"device":device})
        finally:
            if proc.poll() is None:
                proc.terminate();proc.wait(timeout=30)
    print("Reader complete",flush=True)


def signflip(delta):
    d=np.array([v for v in delta if abs(v)>1e-12])
    obs=abs(d.sum());weights=np.abs(d);rng=np.random.default_rng(510272)
    if len(d)<=20:
        s=np.array([0.])
        for w in weights:s=np.r_[s-w,s+w]
        extreme=int((np.abs(s)>=obs-1e-12).sum());draws=len(s);p=extreme/draws
    else:
        extreme=0;draws=1000000
        for i in range(0,draws,1000):
            signs=rng.integers(0,2,size=(1000,len(d)),dtype=np.int8)*2-1
            extreme+=int((np.abs((signs*weights).sum(axis=1))>=obs-1e-12).sum())
        p=(extreme+1)/(draws+1)
    return {"observed_abs_sum":obs,"nonzero":len(d),"draws":draws,"extreme":extreme,"two_sided_p":p}


def grade(official=True):
    assert digest(D/"new-answers.json.gz")==raw(D/"answer-seal.json")["answers"]
    ctx=raw(D/"contexts.json.gz");keys=sorted(ctx); n=len(keys)
    assert len({r["cluster"] for r in ctx.values()})==n==1280
    old_clusters={r["cluster"] for r in raw(BASE.parent/"transfer"/"contexts.json.gz").values()}
    assert not old_clusters&{r["cluster"] for r in ctx.values()}
    ans=raw(ROUTE/"answers.json.gz"); missing=raw(D/"new-answers.json.gz");assert not set(ans)&set(missing)
    ans.update(missing)
    gold=raw(ROUTE/"gold.json.gz")
    author=module(Path("D:/CodexResearch/x20-r51-hotpot-gate/official.py"),
                  "d35fc91a6db21d791dbdda11daf3856e9359f5701d54e3eefba20d88fecc02c0") if official else None
    records={}
    for q,c in ctx.items():
        labels=gold[q]; supp=set(labels["support_titles"]);titles=labels["titles"]
        row={}
        for a,(i,k,sz) in c["refs"].items():
            text=ans[k]["answer"];em,f1=score(text,[labels["answer"]])
            if author:
                assert em==author.exact_match_score(text,labels["answer"]) and abs(f1-author.f1_score(text,labels["answer"])[0])<1e-12
            hits={titles[c["seed"]],titles[i]}&supp
            row[a]={"full":int(len(hits)==len(supp)),"recall":len(hits)/len(supp),"em":em,"f1":f1}
        records[q]=row
    metrics=("full","recall","em","f1");policies={}
    for a in records[keys[0]]:
        policies[a]={k:sum(records[q][a][k] for q in keys)/n for k in metrics}
        policies[a]["changed"]=sum(ctx[q]["refs"][a][0]!=ctx[q]["refs"]["dense"][0] for q in keys)
    pairs=[("graph",b) for b in ("hybrid","gate","linked","dense","router")]+[("graph_pair","gate"),("answer_pair","gate")]
    diffs=[];cols=[]
    for a,b in pairs:
        for k in metrics:
            cols.append((a,b,k));diffs.append([records[q][a][k]-records[q][b][k] for q in keys])
    estimates=ci_records(np.array(diffs).T,np.random.default_rng(510271));comparisons={}
    for (a,b,k),diff,interval in zip(cols,diffs,estimates):
        out={"delta_pp":interval[0],"ci95_pp":interval[1:],"gains":sum(v>1e-12 for v in diff),"losses":sum(v< -1e-12 for v in diff)}
        if a=="graph" and b=="hybrid" and k=="f1":out["sign_flip"]=signflip(diff)
        comparisons.setdefault(a+"-"+b,{})[k]=out
    result={"n":n,"panels_disjoint_qids_and_first_documents":True,"n_new_prompts":len(missing),"policies":policies,
            "contrasts":comparisons,"shortened":{q:[c["original"],c["cap"]] for q,c in ctx.items() if c["original"]!=c["cap"]}}
    if official:
        put("records.json.gz",records);put("results.json",result)
        put("grade-seal.json",{"answers":digest(D/"answer-seal.json"),"records":digest(D/"records.json.gz"),
                               "results":digest(D/"results.json"),"gold":digest(ROUTE/"gold.json.gz"),
                               "assignments":n*len(policies),"author":"d35fc91a6db21d791dbdda11daf3856e9359f5701d54e3eefba20d88fecc02c0"})
    else:
        assert records==raw(D/"records.json.gz") and result==raw(D/"results.json")
    print("Graded",n*len(policies),"assignments")


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage",choices=("select","reader","grade","verify"))
    stage=parser.parse_args().stage
    {"select":select,"reader":run_reader,"grade":grade,"verify":lambda:grade(False)}[stage]()
