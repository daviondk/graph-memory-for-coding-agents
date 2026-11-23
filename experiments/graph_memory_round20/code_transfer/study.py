"""Native coding handoff; the parser, models, cohort and objective are frozen in plan()."""
import argparse
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
import gzip
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
import tarfile
import time

import numpy as np

ROOT = Path(__file__).resolve().parent
R19 = ROOT.parents[1] / "graph_memory_round19"
WRITER = R19 / "write_learned"
ONLINE = R19 / "online_write"
PRIV = Path(os.environ.get("QUIX_PRIVATE", "D:/CodexResearch/x20-r20-code-transfer-private"))
SOURCE = Path(os.environ.get("QUIX_REFERENCE", "D:/CodexResearch/x20-session3-quixbugs"))
EXE = Path(os.environ.get("QUIX_PYTHON", "D:/CodexResearch/x20-binding-testmon-current/Scripts/python.exe"))
REV = "4257f44b0ff1181dedaedee6a447e133219fcebf"
MODEL_SHA = "403fef4a84746cdf3fa1c6c73ddc96d55432ff01f93be9a87a28ac67b5200513"
sys.path.insert(0, str(WRITER))
from forecast_write import choose, stream

QUERY = "Which previously failed pytest test case should be rerun? Return the exact failed test identifier, if any."
ARMS = ("full","output_head","fifo","positional","full_history","failure_index")
NODE = r"python_testcases/test_[A-Za-z0-9_]+\.py::[A-Za-z0-9_]+(?:\[[^\]\r\n]{1,180}\])?"
# Require a complete line up to the status or end-of-summary delimiter; never accept
# a trailing fragment of a parametrized ID as a non-parametrized ID.
STATUS = re.compile(r"(?m)(?<![A-Za-z0-9_/])(" + NODE + r")\s+FAILED(?:\s|$)")
SUMMARY = re.compile(r"(?m)^FAILED\s+(" + NODE + r")(?=\s+-\s+|\r?$)")


def put(path, obj):
    raw = (json.dumps(obj,sort_keys=True,ensure_ascii=False,separators=(",",":"))+"\n").encode()
    path.write_bytes(gzip.compress(raw,mtime=0) if path.suffix==".gz" else raw)


def load(path):
    raw = path.read_bytes()
    return json.loads(gzip.decompress(raw) if path.suffix==".gz" else raw)


def dg(x):
    if isinstance(x,Path):
        x=x.read_bytes()
    if isinstance(x,str):
        x=x.encode()
    return hashlib.sha256(x).hexdigest()


def file_name(name):
    return "python_testcases/test_"+name+".py"


def source_name(name, state):
    return ("correct_python_programs/" if state=="correct" else "python_programs/")+name+".py"


def plan():
    assert dg(WRITER/"model.json")==MODEL_SHA
    PRIV.mkdir(parents=True,exist_ok=True)
    checkout=PRIV/"checkout"
    checkout.mkdir(exist_ok=True)
    cmd=["git","-C",str(SOURCE),"archive","--format=tar",REV,"conftest.py","python_programs",
         "correct_python_programs","python_testcases","json_testcases","LICENSE"]
    package=subprocess.check_output(cmd)
    sources={}
    with tarfile.open(fileobj=io.BytesIO(package)) as tf:
        for entry in tf:
            rel=PurePosixPath(entry.name)
            assert not rel.is_absolute() and ".." not in rel.parts
            if not entry.isfile():
                continue
            data=tf.extractfile(entry).read()
            where=checkout/entry.name
            where.parent.mkdir(exist_ok=True,parents=True)
            if not where.exists():
                where.write_bytes(data)
            assert dg(where)==dg(data)
            sources[entry.name]=dg(data)
    prior=set(p.name for p in (ROOT.parents[1]/"graph_memory_round9/agentvalue/tasks").iterdir() if p.is_dir())
    eligible=sorted(p.stem for p in (checkout/"json_testcases").glob("*.json") if p.stem not in prior
                    and all(k in sources for k in [source_name(p.stem,"buggy"),source_name(p.stem,"correct"),file_name(p.stem)]))
    targets=sorted(eligible,key=lambda n:dg("R20 code transfer target|"+n))[:18]
    assert len(targets)==18
    roster={}
    for name in targets:
        context=sorted(set(eligible)-{name},key=lambda n:dg("R20 context|"+name+"|"+n))[:12]
        roster[name]=sorted(context+[name],key=lambda n:dg("R20 order|"+name+"|"+n))
    deps={n:dg(p) for n,p in {"r19_weights":WRITER/"model.json","r19_choose":WRITER/"forecast_write.py",
          "r19_features":WRITER/"features.py","r19_stream":ONLINE/"predict.py","tokenizer":stream.TOKENIZER,
          "study.py":ROOT/"study.py","local_run.py":ROOT/"local_run.py","protocol":ROOT/"PROTOCOL_RU.md"}.items()}
    put(ROOT/"design-lock.json",dict(revision=REV,roster=roster,eligible=eligible,excluded_prior=sorted(prior),
        model_sha=MODEL_SHA,files=sources,inputs=deps,query=QUERY,arms=ARMS))


def run_actual(job):
    tag,name,state,node=job
    fold=PRIV/tag
    fold.mkdir(parents=True,exist_ok=True)
    key=dg(json.dumps([name,state,node]))[:32]
    receipt=fold/(key+".json")
    audit=fold/(key+"-plugin.json")
    if receipt.exists():
        return load(receipt)
    command=[str(EXE),"-B",str(ROOT/"local_run.py"),str(audit),state,node]
    env={**os.environ,"PYTHONDONTWRITEBYTECODE":"1","PYTEST_DISABLE_PLUGIN_AUTOLOAD":"1",
         "PYTHONHASHSEED":"0","NO_COLOR":"1","PYTHONIOENCODING":"utf-8","COLUMNS":"120"}
    start=time.perf_counter()
    try:
        result=subprocess.run(command,cwd=PRIV/"checkout",env=env,capture_output=True,timeout=8)
        rc=result.returncode
        text=result.stdout
        err=result.stderr
    except subprocess.TimeoutExpired as exc:
        rc="timeout";text=exc.stdout or b"";err=exc.stderr or b""
    s=text.decode("utf8",errors="replace").replace("\r\n","\n")
    # The public input has no machine paths, timing or OS-specific root banner.
    s=s.replace((PRIV/"checkout").as_posix()+"/","").replace(str(PRIV/"checkout")+"\\","")
    s=re.sub(r"(?im)^rootdir:.*\n", "",s)
    s=re.sub(r'(?i)\b\d+(?:\.\d+)?s(?=\s*=*\s*(?:\n|$))',"<time>",s)
    pub=fold/(key+".txt")
    pub.write_bytes(s.encode("utf8"))
    trusted=load(audit) if audit.is_file() else {"collected":[],"reports":[]}
    known=rc in (0,1) and trusted.get("rc")==rc and bool(trusted["collected"])
    fail=sorted({nid for nid,phase,value in trusted["reports"] if phase=="call" and value=="failed"})
    if known:
        phases=defaultdict(set)
        for nid,phase,value in trusted["reports"]:
            phases[nid].add((phase,value))
        known=all(("teardown","passed") in phases[nid] and not any(v=="failed" and ph!="call" for ph,v in phases[nid])
                  for nid in trusted["collected"])
    out=dict(key=key,name=name,state=state,node=node,rc=rc,known=known,fail=fail,collect=trusted["collected"],
             seconds=time.perf_counter()-start,output_sha=dg(pub),stderr_sha=dg(err))
    put(receipt,out)
    return out


def jobs_for(roster):
    return sorted({("initial",n,"correct",file_name(n)) for ns in roster.values() for n in ns}
                  |{("initial",t,"buggy",file_name(t)) for t in roster})


def observe():
    lock=load(ROOT/"design-lock.json")
    assert lock["inputs"]["study.py"]==dg(ROOT/"study.py")
    with ThreadPoolExecutor(max_workers=3) as pool:
        observed=list(pool.map(run_actual,jobs_for(lock["roster"])))
    # The observation stage exposes stdout only; the numerical predictions have
    # no access to the trusted statuses, selected node IDs or test labels.
    mapping={(r["name"]+"/"+r["state"]):dict(key=r["key"],sha=r["output_sha"]) for r in observed}
    put(PRIV/"observation.json",mapping)
    put(PRIV/"initial.json",observed)
    put(ROOT/"observation-lock.json",dict(count=len(observed),sha=dg(PRIV/"observation.json"),
        oracle_sha=dg(PRIV/"initial.json"),design=dg(ROOT/"design-lock.json")))


def parse_failure(text):
    return set(STATUS.findall(text))|set(SUMMARY.findall(text))


def trace(order,target,scenario,observed):
    fields={};pool=[]
    def event(name,arg,buf):
        for output,value in enumerate([arg,buf]):
            i=len(pool);e="e"+str(i).zfill(4)
            pointer="/content" if output else "/arguments"
            fields[e]=value
            pool.append(dict(metadata=dict(message_index=i,sub_index=0,
                node_kind="content.tool_output" if output else "argument",tool_name=name),
                source_spans=[dict(event_id=e,json_pointer=pointer)]))
    for member in order:
        state=scenario if member==target else "correct"
        for real,shown in [(source_name(member,state),"python_programs/"+member+".py"),
                           (file_name(member),file_name(member)),("json_testcases/"+member+".json","json_testcases/"+member+".json")]:
            s=(PRIV/"checkout"/real).read_text(encoding="utf8")
            event("read","read "+shown,s)
        meta=observed[member+"/"+state]
        source=PRIV/"initial"/(meta["key"]+".txt")
        assert dg(source)==meta["sha"]
        event("exec","python -m pytest -vv --tb=short "+file_name(member),source.read_text(encoding="utf8"))
    return fields,pool


def read_spans(ids,blocks,ad,fields):
    pieces=[]
    start=end=event=None
    for j in sorted(ids):
        e,a,b,_,_=blocks[j]
        if e!=event or a!=end:
            if event is not None:pieces.append(fields[ad[event][0]][start:end])
            start=a;event=e
        end=b
    if event is not None:pieces.append(fields[ad[event][0]][start:end])
    return pieces


def predict():
    lock=load(ROOT/"design-lock.json");obs=load(PRIV/"observation.json")
    assert dg(PRIV/"observation.json")==load(ROOT/"observation-lock.json")["sha"]
    assert dg(ROOT/"study.py")==lock["inputs"]["study.py"] and dg(WRITER/"model.json")==MODEL_SHA
    tok=stream.Tokenizer.from_file(str(stream.TOKENIZER));tok.no_truncation();tok.no_padding()
    model=load(WRITER/"model.json");rows=[];q=[("q",stream.content_tokens(QUERY))]
    starttime=time.perf_counter()
    for target,order in lock["roster"].items():
        for state in ("correct","buggy"):
            fields,pool=trace(order,target,state,obs)
            ad,blocks,keys,unmatched=stream.stream_blocks(fields,pool,tok)
            assert not unmatched
            costs=[b[3] for b in blocks]
            fitted=choose(ad,blocks,fields,pool,model)
            kept={a:fitted["tokens/"+a][0] for a in ("full","positional")}
            for a in ("fifo","output_head"):
                kept[a]=stream.select(costs,keys,stream.POLICIES.index(a),8192)
            kept["full_history"]=list(range(len(blocks)))
            lex=[stream.content_tokens(fields[ad[e][0]][a:b]) for e,a,b,_,_ in blocks]
            outcomes={}
            for arm,keep in kept.items():
                ids=stream.read(keep,costs,lex,q)["q"]
                candidates=set().union(*(parse_failure(s) for s in read_spans(ids,blocks,ad,fields)))
                choice=min(candidates,default=None)
                outcomes[arm]=dict(selected=choice,stored=sum(costs[i] for i in keep),read=sum(costs[i] for i in ids),
                    kept=keep,picked=ids,entries=len(candidates))
            matches=set()
            for unit in pool:
                if unit["metadata"]["tool_name"]=="exec" and unit["metadata"]["node_kind"]=="content.tool_output":
                    matches.update(parse_failure(fields[unit["source_spans"][0]["event_id"]]))
            choice=min(matches,default=None)
            outcomes["failure_index"]=dict(selected=choice,bytes=len(choice.encode())+1 if choice else 1,entries=len(matches))
            rows.append(dict(target=target,state=state,raw_tokens=sum(costs),blocks=len(blocks),events=len(ad),arms=outcomes))
    put(ROOT/"forecasts.json.gz",rows)
    put(ROOT/"forecast-seal.json",dict(forecast=dg(ROOT/"forecasts.json.gz"),observation=dg(ROOT/"observation-lock.json"),
        design=dg(ROOT/"design-lock.json"),seconds=time.perf_counter()-starttime))


def grade():
    seal=load(ROOT/"forecast-seal.json");assert seal["forecast"]==dg(ROOT/"forecasts.json.gz")
    design=load(ROOT/"design-lock.json");observed=load(PRIV/"initial.json")
    assert load(ROOT/"observation-lock.json")["oracle_sha"]==dg(PRIV/"initial.json")
    base={(r["name"],r["state"]):r for r in observed};plans=load(ROOT/"forecasts.json.gz")
    jobs=set();rows=[]
    for entry in plans:
        target=entry["target"];state=entry["state"]
        runs=[base[n,state if n==target else "correct"] for n in design["roster"][target]]
        eligible={node:(r["name"],r["state"]) for r in runs for node in r["collect"]}
        gold={node for r in runs for node in r["fail"]}
        unknown=not all(r["known"] for r in runs)
        actions={}
        for arm,forecast in entry["arms"].items():
            node=forecast["selected"];job=None
            if node is not None and node in eligible:
                name,variant=eligible[node]
                job=("rerun",name,variant,node);jobs.add(job)
            actions[arm]=dict(node=node,job=job,valid=node in eligible)
        rows.append(dict(target=target,state=state,unknown=unknown,gold=sorted(gold),actions=actions))
    with ThreadPoolExecutor(max_workers=3) as ex:
        runs=list(ex.map(run_actual,sorted(jobs)))
    rerun={(r["name"],r["state"],r["node"]):r for r in runs}
    for row in rows:
        for act in row["actions"].values():
            job=act.pop("job");trial=rerun.get(tuple(job[1:])) if job else None;node=act["node"]
            act["confirmed"]=bool(trial and trial["known"] and node in trial["fail"] and trial["collect"]==[node])
            act["success"]=not row["unknown"] and ((node is None and not row["gold"]) or (node in row["gold"] and act["confirmed"]))
    put(ROOT/"native-receipts.json.gz",dict(initial=observed,reruns=runs))
    put(ROOT/"outcomes.json.gz",rows)
    res={}
    for arm in ARMS:
        act=[x["actions"][arm] for x in rows]
        res[arm]=dict(success=sum(a["success"] for a in act),proposals=sum(a["node"] is not None for a in act),
            confirmed=sum(a["confirmed"] for a in act),positive=sum(x["actions"][arm]["success"] for x in rows if x["gold"]),
            negative=sum(x["actions"][arm]["success"] for x in rows if not x["gold"]),
            stored=float(np.mean([r["arms"][arm]["stored"] for r in plans])) if arm!="failure_index" else None,
            read=float(np.mean([r["arms"][arm]["read"] for r in plans])) if arm!="failure_index" else None)
    pair={}
    for a in ARMS:
        by=defaultdict(list)
        for r in rows:by[r["target"]].append(int(r["actions"]["full"]["success"])-int(r["actions"][a]["success"]))
        d=np.array([np.mean(v) for _,v in sorted(by.items())])
        ix=np.random.default_rng(20).integers(len(d),size=(10000,len(d)))
        pair[a]=dict(delta=d.mean(),ci=np.quantile(d[ix].mean(1),[.025,.975]).tolist())
    result=dict(n=len(rows),targets=len(design["roster"]),unconfirmed=sum(r["unknown"] for r in rows),
        positives=sum(bool(r["gold"]) and not r["unknown"] for r in rows),negatives=sum(not r["gold"] and not r["unknown"] for r in rows),
        overflow=sum(r["raw_tokens"]>8192 for r in plans),token_range=[min(r["raw_tokens"] for r in plans),max(r["raw_tokens"] for r in plans)],
        run_count=len(observed),rerun_count=len(runs),initial_seconds=sum(r["seconds"] for r in observed),rerun_seconds=sum(r["seconds"] for r in runs),
        index_max_bytes=max(r["arms"]["failure_index"]["bytes"] for r in plans),stats=res,paired_full_minus=pair)
    put(ROOT/"results.json",result);print(json.dumps(result),flush=True)


if __name__=="__main__":
    args=argparse.ArgumentParser();args.add_argument("stage",choices=["plan","observe","predict","grade"])
    globals()[args.parse_args().stage]()
