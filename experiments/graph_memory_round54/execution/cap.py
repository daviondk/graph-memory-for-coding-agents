"""Balanced output-cap sensitivity. Recover and validate original token IDs before extension."""
from study import *
from grade import extracted
from generate import PARAMS,EXE,READER,server
import common
def generate():
    prompts=get("prompts.json.gz");primary=get("answers.json.gz")
    assert get("answer-seal.json")["answers"]==sha(D/"answers.json.gz")
    low=sorted(h for h,v in primary.items() if v["stop"]=="limit")
    eos=sorted((h for h,v in primary.items() if v["stop"]=="eos"),
               key=lambda k:hash_bytes(("r54-eos-replay|"+k).encode()))[:3]
    assert len(low)==7 and len(eos)==3
    put("cap-registration.json",dict(protocol=sha(D/"CAP_PROTOCOL_RU.md"),code=sha(Path(__file__)),low=low,eos=eos,
       source=sha(D/"answer-seal.json"),inputs=sha(D/"input-seal.json")))
    common.RUN=WORK;checks={};extended={}
    def item(r):return dict(code=r["content"],tokens=r["tokens_predicted"],stop=r["stop_type"])
    with server(READER,["--parallel","1","--ctx-size","4096","--flash-attn","on","--threads","4"],"class-reader-768",18954) as (url,s,hw):
        assert get("input-seal.json")["hardware"]["build"]==hw["build"]
        def run(h,n):
            req={**PARAMS,"n_predict":n,"prompt":prompts[h],"return_tokens":True}
            r=s.post(url+"/completion",json=req,timeout=120);r.raise_for_status()
            return r.json()
        for h in eos:
            obs=run(h,768);assert item(obs)==primary[h]
            checks[h]=dict(kind="eos",same_text=True,token_ids=obs["tokens"])
        for h in low:
            short=run(h,384);long=run(h,768)
            assert item(short)==primary[h] and len(short["tokens"])==384
            assert long["tokens"][:384]==short["tokens"] and long["content"].startswith(short["content"])
            extended[h]=item(long)
            checks[h]=dict(kind="limit",same_text_prefix=True,short_ids=short["tokens"],long_ids=long["tokens"])
    put("cap-answers.json.gz",extended);put("cap-token-replay.json.gz",checks)
    put("cap-answer-seal.json",dict(answers=sha(D/"cap-answers.json.gz"),checks=sha(D/"cap-token-replay.json.gz"),
        registration=sha(D/"cap-registration.json"),hardware=hw,remaining_limits=sum(z["stop"]=="limit" for z in extended.values())))
    print("Native token prefixes verified",len(low),"EOS replays",len(eos),flush=True)

def grade_extended():
    import numpy as np
    from grade import signflip
    from isolate import execute
    extended=get("cap-answers.json.gz");ctx=get("contexts.json.gz");data=get("observations.json.gz")
    primary=get("records.json.gz");old_log=get("unittest.json.gz");raw={r["task_id"]:r for r in dataset()}
    assert sha(D/"cap-answers.json.gz")==get("cap-answer-seal.json")["answers"]
    jobs={};new_parses={}
    for q,row in ctx.items():
        task=data[q];src=raw[task["task_id"]]
        for _,h,n in row["refs"].values():
            if h not in extended:continue
            k=q+"|"+h
            if k in new_parses:continue
            tree,mark=extracted(extended[h]["code"],task["method"]);new_parses[k]=mark
            if tree:jobs[k]=dict(id=k,src=patched(src,task["method"],tree),test=src["test"],suite=task["test_class"])
    measured=execute(list(jobs.values()),4)
    records={}
    for q,row in ctx.items():
        qs={};ntests=old_log["expected_tests"][q]
        for arm,(_doc,h,n) in row["refs"].items():
            k=q+"|"+h
            if h not in extended:qs[arm]=primary[q][arm];continue
            v=measured.get(k,{});success=int(v.get("run")==ntests and v.get("passed",False))
            tests=0 if v.get("run")!=ntests else max(0,ntests-v.get("failures",0)-v.get("errors",0)-v.get("skipped",0))
            status=new_parses[k]
            if status=="executed":
                status="pass" if success else "timeout" if v.get("timeout") else "runtime_error" if v.get("errors") else "assertion_failure"
            qs[arm]=dict(pass1=success,fraction=tests/ntests,tests_passed=tests,total=ntests,status=status)
        records[q]=qs
    order=sorted(ctx)
    unique,index=np.unique([ctx[q]["cls"] for q in order],return_inverse=True);sizes=np.bincount(index)
    rng=np.random.default_rng(540272);draws=rng.integers(len(sizes),size=(10000,len(sizes)))
    summaries={};contrasts={}
    for a in ARMS:
        rows=[records[q][a] for q in order]
        summaries[a]=dict(passed=sum(x["pass1"] for x in rows),passed_tests=sum(x["tests_passed"] for x in rows),total_tests=sum(x["total"] for x in rows),
            status=dict(Counter(x["status"] for x in rows)),mean_test_fraction=np.mean([x["fraction"] for x in rows]))
    for a,b in ((ARMS[0],ARMS[1]),(ARMS[0],ARMS[2]),(ARMS[1],ARMS[2])):
        comps={}
        for m in ("pass1","fraction"):
            d=np.array([records[q][a][m]-records[q][b][m] for q in order]);total=np.bincount(index,weights=d)
            samples=100*total[draws].sum(axis=1)/sizes[draws].sum(axis=1)
            comps[m]=dict(delta_pp=100*d.mean(),ci95_pp=list(np.quantile(samples,[.025,.975])),
                         wins=int((d>1e-12).sum()),losses=int((d< -1e-12).sum()),signflip=signflip(total))
        contrasts[a+" vs "+b]=comps
    put("cap-unittest.json.gz",dict(raw=measured,parse=new_parses));put("cap-records.json.gz",records)
    put("cap-results.json",dict(summaries=summaries,contrasts=contrasts,methods=len(ctx),new_tests=len(jobs),
        rerun=len(extended),remaining_limits=get("cap-answer-seal.json")["remaining_limits"]))
    put("cap-grade-seal.json",dict(results=sha(D/"cap-results.json"),records=sha(D/"cap-records.json.gz"),tests=sha(D/"cap-unittest.json.gz"),
        answers=sha(D/"cap-answer-seal.json"),primary=sha(D/"grade-seal.json"),code=sha(Path(__file__))))
    print("768 caps",summaries,contrasts['caller_bm25 vs bm25'])
if __name__=="__main__":
    generate();grade_extended()
