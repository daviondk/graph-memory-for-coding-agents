"""Extract literal historical signals, seal prefix-only forecasts, then evaluate."""
import collections
import gzip
import json
import pathlib
import re
import sys

ROOT=pathlib.Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parent))
from prepare import WORK,REPOS,BAD,LINE,project,digest,save,dumps,rows
from score import bootstrap

def dumpout(out,row):
    out.write((dumps(row)+"\n").encode())

def inputs():
    ext=WORK/"graph_memory_round6/version/external"
    yield "claude",ext/"source.gz",ext/"terminal.gz"
    kimi=WORK/"graph_memory_round5/action_transfer"
    for i in range(8):
        yield "kimi",kimi/f"source_{i}.gz",kimi/f"terminal_{i}.gz"

def extract(raw,shell,parser):
    result=[]
    cwd=True
    for (name,args,text),extra in zip(raw,shell,strict=True):
        code=project([name,args,text])
        ev=None
        if code:
            ev=[code[0],code[1],sorted({int(m[1]) for line in text.splitlines() if (m:=LINE.match(line))})]
        else:
            seen=collections.defaultdict(list)
            for p,n,_,kind in parser.readlines(extra,cwd):
                if p.endswith(".py"):
                    seen[kind.startswith("search"),p].append(n)
            if seen:
                (search,p),ns=next(iter(seen.items()))
                ev=["search" if search else "shell",p,list(dict.fromkeys(ns))]
        if extra:
            cmd=extra["command"]
            if re.search(r"(?:^|[;&\n])\s*(?:cd|pushd|popd)\b",cmd):
                cwd=False
            if re.fullmatch(r"\s*cd\s+/testbed/?\s*",cmd):
                cwd=True
        result.append(ev)
    return result

def prepare():
    sys.path.insert(0,str(WORK/"graph_memory_round5/action_transfer"))
    import replicate
    source={}
    ids=set()
    groups=collections.Counter()
    with gzip.GzipFile(str(ROOT/"observations.jsonl.gz"),"wb",mtime=0) as out:
        for g,f,t in inputs():
            for k in (f,t):
                source[k.relative_to(WORK).as_posix()]=digest(k)
            for task,(i,terminal) in zip(rows(f),rows(t),strict=True):
                assert task["instance"]==i
                if task["official_repo"] not in REPOS or BAD.search(task["issue"]):
                    continue
                assert i not in ids
                ids.add(i)
                groups[g]+=1
                dumpout(out,dict(id=i,panel=g,repo=task["official_repo"],
                                 events=extract(task["events"],terminal,replicate.pol)))
    save(ROOT/"freeze.json",{"sources":source,"parser":digest(pathlib.Path(replicate.pol.__file__)),
                             "common":{str(p):digest(ROOT/p) for p in ["../prepare.py","../score.py"]},
                             "files":{n:digest(ROOT/n) for n in ["run.py","PROTOCOL.md","observations.jsonl.gz"]},
                             "tasks":groups})

def forecasts(events):
    last=None
    assoc={}
    hint=None
    for t,ev in enumerate(events,1):
        active=hint is not None and t-hint[0]<=2
        if active:
            _,p,n=hint
            alt=[p,assoc.get(p,1)]
            choice=[p,n]
        else:
            choice=last
            alt=last
        yield t,active,[last,choice,alt]
        if ev:
            kind,p,ns=ev
            if kind=="search":
                hint=(t,p,ns[0])
            else:
                ordered=sorted(ns)
                n=ordered[(len(ordered)-1)//2]
                last=[p,n]
                assoc[p]=n
                hint=None

def predict():
    sealed=json.loads((ROOT/"freeze.json").read_bytes())
    assert all(digest(ROOT/k)==v for k,v in (sealed["files"]|sealed["common"]).items())
    demo=[None,["search","p.py",[17]],None,["shell","a.py",[1,2,3,4]]]
    for t in range(len(demo)):
        assert list(forecasts(demo))[:t+1]==list(forecasts(demo[:t]+[None]*(len(demo)-t)))[:t+1]
    n=0
    with gzip.GzipFile(str(ROOT/"predictions.jsonl.gz"),"wb",mtime=0) as out:
        for row in rows(ROOT/"observations.jsonl.gz"):
            for t,hot,pred in forecasts(row["events"]):
                dumpout(out,[row["id"],t,hot,pred])
                n+=1
    save(ROOT/"predictions_lock.json",{"sha256":digest(ROOT/"predictions.jsonl.gz"),"steps":n,
                                       "freeze":digest(ROOT/"freeze.json"),"suffix_invariance":True})

def summarize(group):
    if not group:
        return {"n":0}
    counts=collections.Counter
    totals={k:[sum(q[k][i] for q in group) for i in range(3)] for k in ["hit","file","first_page"]}
    pairs=[dict(id=q["id"],repo=q["repo"],delta=q["hit"][1]-q["hit"][0]) for q in group]
    vals=counts(q["delta"] for q in pairs)
    return dict(n=len(group),tasks=len({q["id"] for q in group}),repos=len({q["repo"] for q in group}),
                totals=totals,delta_pp=100*(vals[1]-vals[-1])/len(group),
                ci95_task_pp=bootstrap(pairs,"id"),ci95_project_pp=bootstrap(pairs,"repo"),
                wins=vals[1],losses=vals[-1])

def score():
    preds=json.loads((ROOT/"predictions_lock.json").read_bytes())
    assert preds["sha256"]==digest(ROOT/"predictions.jsonl.gz") and preds["freeze"]==digest(ROOT/"freeze.json")
    freeze=json.loads((ROOT/"freeze.json").read_bytes())
    assert all(digest(ROOT/k)==v for k,v in (freeze["files"]|freeze["common"]).items())
    it=iter(rows(ROOT/"predictions.jsonl.gz"))
    allrows=[]
    with gzip.GzipFile(str(ROOT/"scores.jsonl.gz"),"wb",mtime=0) as out:
        for r in rows(ROOT/"observations.jsonl.gz"):
            for t,ev in enumerate(r["events"],1):
                iid,idx,active,pred=next(it)
                assert (iid,idx)==(r["id"],t)
                if not ev or ev[0] not in ("view","shell"):
                    continue
                kind,p,ns=ev
                keep=lambda x:x is not None and x[0]==p
                q=dict(panel=r["panel"],repo=r["repo"],id=iid,t=t,active=active,kind=kind,lines=len(ns),
                       hit=[int(keep(x) and x[1] in ns) for x in pred],
                       file=[int(keep(x)) for x in pred],
                       first_page=[int(keep(x) and (x[1]-1)//16==(min(ns)-1)//16) for x in pred])
                allrows.append(q)
                dumpout(out,q)
    assert next(it,None) is None
    output={}
    for name in ("kimi","claude"):
        q=[s for s in allrows if s["panel"]==name]
        output[name]={k:summarize([r for r in q if cond(r)]) for k,cond in {
            "all":lambda x:True,"after_search":lambda x:x["active"],"short_64":lambda x:x["lines"]<=64,
            "shell":lambda x:x["kind"]=="shell","editor":lambda x:x["kind"]=="view"}.items()}
        print(name,output[name]["all"],"activated:",output[name]["after_search"])
    save(ROOT/"results.json",dict(arms=["baseline","search","path_only"],panels=output))

if __name__=="__main__":
    {"prepare":prepare,"predict":predict,"score":score}[sys.argv[1]]()
