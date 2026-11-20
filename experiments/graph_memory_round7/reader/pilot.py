"""Paired comparison using fixed R7 contexts, R6 model and R6 local evaluator."""
import concurrent.futures
import gzip
import hashlib
import importlib.util
import json
import math
import shutil
import sys
import tarfile
import time
import urllib.error
import urllib.request
from pathlib import Path

D = Path(__file__).resolve().parent
R6 = D.parents[1] / "graph_memory_round6" / "repair"
OLD = R6 / "transfer"
LOC = D.parent / "localization"
NAMES = {"flat": "bm25", "evidence": "doclink"}
def read(path):
    raw = path.read_bytes()
    return json.loads(gzip.decompress(raw) if path.suffix == ".gz" else raw)
def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf8")
def digest(raw):
    return hashlib.sha256(raw).hexdigest()
def filehash(p):
    h=hashlib.sha256()
    with p.open("rb") as f:
        for buf in iter(lambda:f.read(2**20),b""):h.update(buf)
    return h.hexdigest()
def atomic(path, data):
    temp=path.with_suffix(path.suffix+".tmp")
    temp.write_bytes(data)
    temp.replace(path)
def save(p, x):
    atomic(p, json.dumps(x,indent=2,ensure_ascii=False).encode("utf8"))
def sealed():
    x=read(D/"input_lock.json")
    for key,h in x["files"].items():
        assert filehash(D/key)==h,key
    return x["ids"]
def freeze():
    if (D/"input_lock.json").exists(): raise RuntimeError("Inputs already locked")
    ids=read(OLD/"cohort.json")["ids"][12:20]
    assert len(ids)==8 and len(set(ids))==8
    loc_lock=read(LOC/"predictions.lock.json")
    jobs={}; assign={}; details={}
    system="Repair a mathematics library using code fragments observed by a previous developer. Output only JSON with an edits array. Each item has path (as shown), old (one exact, unique contiguous substring in the unmodified file) and new (replacement). Preserve literal spaces and indentation. Use minimal edits. Give your best fix."
    for i in ids:
        f=LOC/"predictions"/(i+".json.gz"); assert filehash(f)==loc_lock["predictions"][i]
        rec=read(f); pub=read(OLD/"tasks"/i/"public.json")
        assert rec["id"]==i and pub["repo"]=="sympy/sympy" and rec["base"]==pub["base_commit"]
        task=D/"tasks"/i;task.mkdir(exist_ok=True,parents=True)
        info={"paths":rec["paths"],"base_commit":rec["base"],"issue":rec["issue"],"arms":{}}
        assignment={}
        for alias,arm in NAMES.items():
            data=rec["arms"][arm]
            assert data["tokens"]<=1800 and 0<len(rec["paths"])<=8
            prompt="Issue:\n"+rec["issue"]+"\n\nObserved Python code:\n"+data["packet"]
            req=dict(model="qwen38-27b-ud-q4km",messages=[dict(role="system",content=system),dict(role="user",content=prompt)],temperature=0,seed=int(digest(i.encode())[:7],16),max_tokens=850,repeat_penalty=1,cache_prompt=False,stream=False,chat_template_kwargs={"enable_thinking":False})
            key=digest(canonical(req));jobs[key]=req;assignment[alias]=key
            info["arms"][arm]={"memory_tokens":data["tokens"],"packet_sha256":digest(data["packet"].encode()),"request_id":key}
        atomic(task/"packets.json.gz",gzip.compress(canonical({"paths":rec["paths"]}),mtime=0))
        assign[i]=assignment;details[i]=info
    save(D/"assign.json",assign);save(D/"packets.json",details)
    atomic(D/"requests.json.gz",gzip.compress(canonical(jobs),mtime=0))
    names=["assign.json","packets.json","requests.json.gz","PROTOCOL_RU.md","pilot.py","start_server.ps1","../localization/predictions.lock.json","../../graph_memory_round6/repair/transfer/grade.py","../../graph_memory_round6/repair/transfer/cohort.json","../../graph_memory_round6/repair/model_receipt.json","../../graph_memory_round6/repair/runtime_receipt.json"]
    names += ["tasks/"+i+"/packets.json.gz" for i in ids]
    save(D/"input_lock.json",{"ids":ids,"gpu_calls":len(jobs),"files":{n:filehash(D/n) for n in names},
                             "cohort_basis":"R6 transfer public SHA order indices [12:20]","arms":NAMES})
    print(len(ids),"tasks;",len(jobs),"unique requests",flush=True)
def extract_one(i):
    source=OLD/"tasks"/i
    path=source/"checkout.tar.gz"; record=read(source/"ready.json")
    assert filehash(path)==record["sha256"]
    dst=D/"tasks"/i/"base";dst.mkdir(exist_ok=True)
    with tarfile.open(path) as tar:
        for member in tar:
            parts=member.name.split("/",1)
            if len(parts)!=2 or not member.isfile():continue
            target=(dst/parts[1]).resolve()
            if not target.is_relative_to(dst.resolve()):raise ValueError(target)
            target.parent.mkdir(parents=True,exist_ok=True)
            with tar.extractfile(member) as src,target.open("wb") as out:shutil.copyfileobj(src,out)
    save(dst.parent/"checkout_receipt.json",record)
    print(i,"checkout verified",flush=True)
def extract():
    ids=sealed()
    with concurrent.futures.ThreadPoolExecutor(3) as p:
        list(p.map(extract_one,ids))
def infer():
    ids=sealed(); jobs=read(D/"requests.json.gz")
    calls=D/"calls";calls.mkdir(exist_ok=True)
    for j,key in enumerate(sorted(jobs,key=lambda k:digest(("r7-reader|"+k).encode())),1):
        req=jobs[key];path=calls/(key+".json.gz")
        if path.exists():
            assert read(path)["request"]==req
            continue
        attempts=[]
        for trial in range(3):
            start=time.monotonic()
            try:
                request=urllib.request.Request("http://127.0.0.1:18917/v1/chat/completions",data=canonical(req),headers={"Content-Type":"application/json"})
                with urllib.request.urlopen(request,timeout=240) as response:result=json.load(response)
                attempts.append({"elapsed":time.monotonic()-start,"success":True});break
            except urllib.error.HTTPError as e:
                print("HTTP",e.code,e.read(220),flush=True);raise
            except OSError as e:
                attempts.append({"elapsed":time.monotonic()-start,"error":type(e).__name__})
                if trial==2:raise
                time.sleep(2)
        assert result["choices"][0]["message"]["content"] is not None
        atomic(path,gzip.compress(canonical({"request":req,"response":result,"attempts":attempts}),mtime=0))
        print(j,len(jobs),result["usage"],round(attempts[-1]["elapsed"],2),flush=True)
    save(D/"answer_lock.json",{"input":filehash(D/"input_lock.json"),"calls":{f.name:filehash(f) for f in sorted(calls.glob("*.json.gz"))}})
def dependency():
    spec=importlib.util.spec_from_file_location("original_grader",OLD/"grade.py");mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod);mod.D=D
    return mod
def grade():
    ids=sealed();lock=read(D/"answer_lock.json")
    assert lock["input"]==filehash(D/"input_lock.json")
    for name,h in lock["calls"].items():assert filehash(D/"calls"/name)==h
    mod=dependency()
    def one(i):
        dest=D/"tasks"/i
        assert read(dest/"checkout_receipt.json")==read(OLD/"tasks"/i/"ready.json")
        shutil.copyfile(OLD/"tasks"/i/"grading.json",dest/"grading.json")
        for stage in ["control","solver"]:
            if not (dest/"grades_v2"/(stage+".json")).exists():mod.task((i,stage))
    with concurrent.futures.ThreadPoolExecutor(3) as pool:list(pool.map(one,ids))
def report():
    ids=sealed();assign=read(D/"assign.json");rows=[]
    for i in ids:
        folder=D/"tasks"/i/"grades_v2";control=read(folder/"control.json");result=read(folder/"solver.json")
        base=control["base"]["tests"];gold=control["gold"]["tests"]
        valid=bool(base["FAIL_TO_PASS"]["complete"] and base["FAIL_TO_PASS"]["failed"] and gold["FAIL_TO_PASS"]["complete"] and not gold["FAIL_TO_PASS"]["failed"])
        basegreen=set(base["PASS_TO_PASS"]["passed"]);row={"id":i,"valid_control":valid,"f2p_n":len(gold["FAIL_TO_PASS"]["requested"]),"base_green_n":len(basegreen),"base_p2p_complete":base["PASS_TO_PASS"]["complete"],"gold_pass_f2p":len(gold["FAIL_TO_PASS"]["passed"]),"arms":{}}
        for alias,arm in NAMES.items():
            val=result[alias];f=val["tests"]["FAIL_TO_PASS"];p=val["tests"]["PASS_TO_PASS"]
            passed=bool(valid and val["applied"] and f["complete"] and not f["failed"])
            missing=len(basegreen-set(p["passed"]));strict=bool(passed and missing==0 and base["PASS_TO_PASS"]["complete"] and p["complete"])
            row["arms"][arm]={"applied":int(val["applied"]),"valid_pass":int(passed),"strict_pass":int(strict),"passed_f2p":len(f["passed"]),"missing_green":missing,"reason":val["reason"],"request":assign[i][alias],"id_differs":assign[i]["flat"]!=assign[i]["evidence"]}
        rows.append(row)
    res={"n":len(rows),"controls":sum(r["valid_control"] for r in rows),"f2p_n":sum(r["f2p_n"] for r in rows),"base_green_n":sum(r["base_green_n"] for r in rows),"totals":{}}
    for arm in NAMES.values():
        res["totals"][arm]={k:sum(x["arms"][arm][k] for x in rows) for k in ["applied","valid_pass","strict_pass","passed_f2p","missing_green"]}
    for k in ["valid_pass","strict_pass","applied"]:
        pairs=[(x["arms"]["bm25"][k],x["arms"]["doclink"][k]) for x in rows];w=pairs.count((0,1));l=pairs.count((1,0));n=w+l
        res[k]={"better":w,"worse":l,"tied":len(rows)-n,"exact_p":min(1,2*sum(math.comb(n,j) for j in range(min(w,l)+1))/(2**n)) if n else 1}
    cs=[read(p) for p in (D/"calls").glob("*.json.gz")];res["unique_calls"]=len(cs)
    res["tokens"]={k:sum(c["response"]["usage"][k] for c in cs) for k in ["prompt_tokens","completion_tokens"]}
    res["elapsed_generation_s"]=sum(t["elapsed"] for c in cs for t in c["attempts"]);save(D/"rows.json",rows);save(D/"results.json",res);print(json.dumps(res))
if __name__=="__main__":
    {"freeze":freeze,"extract":extract,"infer":infer,"grade":grade,"report":report}[sys.argv[1]]()
