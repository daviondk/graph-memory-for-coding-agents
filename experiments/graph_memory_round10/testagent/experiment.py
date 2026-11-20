"""Construct blinded action prompts and run a local one-test policy on immutable snapshots."""
import collections
import difflib
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import sys
ROOT=Path(__file__).resolve().parent
WORK=ROOT.parents[1]
R9=WORK/"graph_memory_round9"
PANELS=("testmemory_compat","testmemory_holdout")
def read(p):return json.loads(gzip.decompress(p.read_bytes()) if p.suffix==".gz" else p.read_bytes())
def save(p,v):p.write_text(json.dumps(v,indent=2)+"\n",encoding="utf8")
def digest(b):return hashlib.sha256(b).hexdigest()
def order(s):return digest(s.encode())
SYS='You are a software testing agent. You may rerun exactly one previously executed test. Pick the test whose previous PASS or FAIL result seems most likely to change under the shown production-code diff. A priority flag, when present, is only a hint. Return only a JSON object {"test": INTEGER} with one listed test number.'
def generate():
    rows=[]
    for cohort in PANELS:
        src=R9/cohort
        forecasts=read(src/"forecasts.json.gz")
        groups=collections.defaultdict(list)
        for r in forecasts:groups[r["task"],r["direction"]].append(r)
        for (i,d),cases in groups.items():
            node_order=sorted(cases,key=lambda r:order("R10-testslots|"+i+"|"+r["node"]))
            k=len(cases)
            file=read(src/"runs"/i/"change.json.gz")
            a,b=(file["before"],file["after"]) if d=="fix" else (file["after"],file["before"])
            delta="\n".join("".join(difflib.unified_diff(a[p].splitlines(True),b[p].splitlines(True),fromfile=p,tofile=p,n=1)) for p in sorted(a))
            if len(delta)>3500:delta=delta[:2300]+"\n[... omitted ...]\n"+delta[-1150:]
            nodes=[x["node"] for x in node_order]
            actual=[int(x["selected"]["symbol"]) for x in node_order]
            prior=[x["prior"] for x in node_order]
            id_=i+"|"+d
            tokens=set(re.findall(r"[a-z][a-z0-9]*",delta.lower()))
            lex=[len({t for t in re.findall(r"[a-z][a-z0-9]*",node.rpartition("::")[2].lower()) if t not in ("test","sympy","issue")}&tokens) for node in nodes]
            ranked=sorted(range(k),key=lambda j:(prior[j]!="failed",-lex[j],j))
            tied=sorted(range(k),key=lambda j:(prior[j]!="failed",-actual[j],-lex[j],j))
            rows.append(dict(id=id_,cohort=cohort,task=i,direction=d,nodes=nodes,prior=prior,diff=delta,
                flags=dict(off=["-"]*k,graph=actual,shuffled=actual[1:]+actual[:1]),baseline=ranked[0],baseline_graph=tied[0]))
    save(ROOT/"inputs.json",rows)
    save(ROOT/"input-lock.json",{f:digest((ROOT/f).read_bytes()) for f in ("PROTOCOL.md","experiment.py","inputs.json")})
def solver():
    spec=importlib.util.spec_from_file_location("testagent_runtime",WORK/"graph_memory_round8/agent/harness.py")
    h=importlib.util.module_from_spec(spec);spec.loader.exec_module(h)
    h.D=ROOT;h.ENDPOINT="http://127.0.0.1:18947/v1/chat/completions"
    return h
def check(lock):
    assert all(digest((ROOT/p).read_bytes())==sha for p,sha in read(ROOT/lock).items())
def run(privileged):
    check("input-lock.json")
    if privileged:check("sealed.json")
    h=solver();answers=[]
    for r in sorted(read(ROOT/"inputs.json"),key=lambda r:order("R10-queue|"+r["id"])):
        flags=r["flags"]
        if privileged:
            grades=read(R9/r["cohort"]/"outcomes.json")
            target={x["node"]:int(x["changed"]) for x in grades if (x["task"],x["direction"])==(r["task"],r["direction"])}
            assert set(target)==set(r["nodes"])
            flags={"privileged":[target[n] for n in r["nodes"]]}
        for arm in sorted(flags,key=lambda a:order(r["id"]+"|"+a)):
            tab="\n".join(f"{j+1:02d}  {prior.upper()}  {bit}  {n}" for j,(n,prior,bit) in enumerate(zip(r["nodes"],r["prior"],flags[arm])))
            prompt="Production diff:\n"+r["diff"]+"\n\nTests (ID, prior result, priority flag, node ID):\n"+tab+"\nChoose one ID."
            key,response=h.call(r["id"],"decision",SYS,prompt,50)
            item=h.obj(response).get("test")
            ix=item-1 if type(item)==int and 1<=item<=len(r["nodes"]) else None
            log=read(ROOT/"calls"/(key+".json.gz"))
            answers.append(dict(id=r["id"],arm=arm,index=ix,call=key,usage=log["response"]["usage"]))
    f="oracle-answers.json" if privileged else "answers.json"
    save(ROOT/f,answers)
    save(ROOT/("oracle-sealed.json" if privileged else "sealed.json"),{p:digest((ROOT/p).read_bytes()) for p in ("input-lock.json",f)})
    print(f,len(answers),len({a["call"] for a in answers}))
if __name__=="__main__":
    {"prepare":generate,"run":lambda:run(False),"oracle":lambda:run(True)}[sys.argv[1]]()
