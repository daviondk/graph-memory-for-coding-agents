"""Run a pinned two-step generation and historical-test observation experiment."""
import gzip
import hashlib
import json
from pathlib import Path
import struct
import sys

HERE = Path(__file__).resolve().parent
OLD = HERE.parents[1] / "graph_memory_round56/solver"
sys.path.insert(0, str(OLD))
import grade
import isolation
import study
import witness
sys.path.insert(0, str(study.R52 / "reranker"))
import common

PARAMS = dict(temperature=0, top_k=1, seed=560271, n_predict=640, cache_prompt=False, stream=False)
ARMS = ("static", "adaptive", "masked", "review")


def save(name, obj):
    common.save(HERE / name, obj)


def read(name):
    return common.read(HERE / name)


def select():
    prior = study.read("selections.json.gz")
    hist = study.read("history.json.gz")
    tasks = study.read("candidates.json.gz")
    eligible = {}
    for q, t in sorted(tasks.items()):
        if q in prior:
            continue
        es = hist[t["repo"]]["episodes"]
        candidates = {i: witness.assertions(e["text"], t["name"])
                      for i, e in enumerate(es) if t["name"] + "(" in e["text"]}
        if not any(candidates.values()):
            continue
        scores = study.score_query(es, t)
        order = sorted(range(len(es)), key=lambda i: (-scores[i], -es[i]["i"], es[i]["path"], es[i]["address"]))
        e = es[order[0]]
        first = dict(path=e["path"], address=e["address"], text=e["text"], sha=e["sha"])
        checks = {}
        for i in order:
            e = es[i]
            for expr, op, expect in candidates.get(i, []):
                key = (expr, op, expect)
                if key not in checks:
                    checks[key] = dict(expr=expr, op=op, expected=expect, episode=i, sha=e["sha"],
                                       path=e["path"], address=e["address"], score=scores[i])
        eligible[q] = dict(task=t, first=first, available=list(checks.values()))
    jobs = [dict(id=q+"|"+kind, repo=r["task"]["repo"], path=r["task"]["path"], name=r["task"]["name"], kind=kind)
            for q, r in eligible.items() for kind in ("reference", "stub")]
    calibration = isolation.execute(jobs)
    save("calibration.json.gz", calibration)
    selected = {}
    for q, r in eligible.items():
        ref, stub = (calibration[q+"|"+v] for v in ("reference", "stub"))
        if ref["passed"] and not stub["passed"] and ref["run"] == stub["run"] and ref["run"] >= 2:
            selected[q] = r
    save("selection.json.gz", selected)
    save("selection-seal.json", dict(candidates=list(eligible), selected=list(selected),
         protocol=common.sha(HERE/"PROTOCOL_RU.md"), selected_sha=common.sha(HERE/"selection.json.gz"),
         prior={n:common.sha(OLD/n) for n in ("pins.json","selections.json.gz","history.json.gz","candidates.json.gz",
             "study.py","grade.py","isolation.py","witness.py")}))
    print("Calibration", len(eligible), "before,", len(selected), "after", flush=True)
    return selected


def format_check(e, status):
    left = "bool("+e["expr"]+")" if e["op"] == "bool" else e["expr"]
    return (e["path"]+" / "+e["address"]+"\nRecorded check: "+left+" == "+e["expected"]
            +"\nObserved result for the draft: "+status+"\n")


def main():
    tasks = select()
    expected = common.read(study.R52/"global_answers/confirm/input-seal.json")
    assert common.sha(common.READER) == expected["reader"] and common.sha(common.EXE) == expected["server"]
    common.RUN = HERE
    with common.server(common.READER, ["--parallel","1","--ctx-size","4096","--flash-attn","on","--threads","4"],
                       "gpu", 18958) as (url, sess, hardware):
        def post(endpoint, body):
            r = sess.post(url+"/"+endpoint, json=body, timeout=140)
            r.raise_for_status()
            return r.json()
        def tok(text, special=False):
            return post("tokenize",dict(content=text,parse_special=special,add_special=False))["tokens"]
        def cap(ids):
            assert len(ids)+PARAMS["n_predict"] <= 4096
            return hashlib.sha256(struct.pack(f"<{len(ids)}I",*ids)).hexdigest()
        suffix=tok("<|im_end|>\n<|im_start|>assistant\n",True)
        def inst(text):
            return tok("<|im_start|>system\n"+text+"<|im_end|>\n<|im_start|>user\n",True)
        intro=inst("Implement the requested public Python function in its existing library. Return just the complete Python function definition. Do not use Markdown or tests. Match the stated contract; you may use existing module helpers or Python standard library imports inside the function.")
        reviewer=inst("Review your draft implementation for its stated contract. Return just the complete revised Python function definition, or KEEP to retain the exact draft. Do not use Markdown or tests. You may use existing module helpers and Python standard library imports inside the function.")
        marker=tok("\nPreviously observed test source from this repository:\n")
        blank=tok(" ")
        assert len(blank)==1
        prompts={}
        answers={}
        ledger=HERE/"generated.jsonl"
        fingerprint=common.sha(HERE/"solve.py")+":"+expected["reader"]+":"+expected["server"]
        if ledger.exists():
            for line in ledger.read_bytes().splitlines():
                f,h,a=json.loads(line)
                assert f==fingerprint
                answers[h]=a
        def ask(h):
            if h not in answers:
                r=post("completion",dict(PARAMS,prompt=prompts[h]))
                a=dict(text=r["content"],tokens=r["tokens_predicted"],stop=r["stop_type"])
                answers[h]=a
                with ledger.open("a",encoding="utf8") as log:
                    print(json.dumps([fingerprint,h,a],ensure_ascii=True),file=log,flush=True)
            return answers[h]
        def register(ids):
            h=cap(ids)
            assert prompts.setdefault(h,ids)==ids
            return h
        inputs={}
        drafts={}
        checks={}
        for q,r in tasks.items():
            t,e=r["task"],r["first"]
            inputs[q]=tok(t["repo"]+" — "+t["path"]+"\n"+t["question"])
            snippet=tok(e["path"]+" / "+e["address"]+"\n"+e["text"])[:240]
            drafts[q]=register(intro+inputs[q]+marker+snippet+suffix)
            checks[q]=[]
            for v in r["available"]:
                if max(len(tok(format_check(v,x))) for x in ("PASS","FAIL","UNKNOWN","HIDDEN"))<=240:
                    checks[q].append(v)
                    if len(checks[q])==6:break
            assert checks[q]
        save("draft-design.json.gz",dict(assign=drafts,checks=checks))
        for h in sorted(set(drafts.values())):
            ask(h)
        print("Generated",len(drafts),"drafts", flush=True)
        probe_jobs=[]
        for q,h in drafts.items():
            t=tasks[q]["task"]
            code,_=grade.parse_answer(answers[h]["text"],t["name"])
            if code:
                probe_jobs.append(dict(id=q,repo=t["repo"],path=t["path"],name=t["name"],answer=code,checks=checks[q]))
        original=isolation.WORKER
        try:
            isolation.WORKER=witness.WORKER
            outcomes=isolation.execute(probe_jobs)
        finally:
            isolation.WORKER=original
        save("probe-execution.json.gz",outcomes)
        plan={}
        for q,h in drafts.items():
            raw=outcomes.get(q,{}).get("values",[])
            status=["PASS" if ok else "FAIL" if tag is not None else "UNKNOWN" for tag,ok in raw]
            if len(status)!=len(checks[q]):
                status=["UNKNOWN"]*len(checks[q])
            j=next((i for i,x in enumerate(status) if x=="FAIL"),0)
            arms={}
            prefix=reviewer+inputs[q]+tok("\nYour draft implementation:\n")+tok(answers[h]["text"])+tok("\nAvailable observation from earlier tests:\n")
            for arm,index,st in (("static",0,status[0]),("adaptive",j,status[j]),("masked",j,"HIDDEN"),("review",None,None)):
                s=format_check(checks[q][index],st) if index is not None else ""
                ids=tok(s) if s else []
                assert len(ids)<=240
                k=register(prefix+ids+blank*(240-len(ids))+suffix)
                arms[arm]=dict(hash=k,index=index,status=st,record_tokens=len(ids))
            assert len({len(prompts[a["hash"]]) for a in arms.values()})==1
            plan[q]=dict(draft=h,status=status,arms=arms)
        save("inputs.json.gz",prompts)
        save("assignments.json.gz",plan)
        save("generation-seal.json",dict(model=expected["reader"],server=expected["server"],settings=PARAMS,hardware=hardware,
             hashes={n:common.sha(HERE/n) for n in ("PROTOCOL_RU.md","solve.py","inputs.json.gz","assignments.json.gz","probe-execution.json.gz","draft-design.json.gz","selection-seal.json")}))
        new=sorted(set(prompts)-set(drafts.values()))
        print("Planned",len(new),"unique revisions",flush=True)
        for i,h in enumerate(new,1):
            ask(h)
            if i%15==0:print("Revision",i,"/",len(new),flush=True)
        assert set(answers)==set(prompts)
        save("answers.json.gz",answers)
        save("answer-seal.json",{n:common.sha(HERE/n) for n in ("answers.json.gz","generation-seal.json")})
        print("Sealed",len(answers),"unique responses",flush=True)


if __name__=="__main__":
    main()
