"""Prospective replication, strong matched controls, and a 16-line budget replay."""
import collections
import gzip
import json
import pathlib
import sys
ROOT=pathlib.Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parent))
import importlib.util
spec=importlib.util.spec_from_file_location("r7_search_replay",ROOT.parent/"run.py")
parent=importlib.util.module_from_spec(spec)
spec.loader.exec_module(parent)
from prepare import WORK,REPOS,BAD,digest,dumps,save,rows
from score import bootstrap

def write(fp,x):
    fp.write((dumps(x)+"\n").encode())

def collect():
    sys.path.insert(0,str(WORK/"graph_memory_round5/action_transfer"))
    import replicate
    base=WORK/"graph_memory_round5/writer"
    terminal=WORK/"graph_memory_round5/action_probe/raw_pairs.jsonl.gz"
    terms=dict(rows(terminal))
    veto={r["id"] for r in rows(ROOT.parent/"observations.jsonl.gz")}
    files=sorted(base.glob("source_*.jsonl.gz"))
    assert len(files)==8
    used={}
    with gzip.GzipFile(str(ROOT/"independent.jsonl.gz"),"wb",mtime=0) as out:
        for f in files:
            for q in rows(f):
                i=q["instance"]
                if i in veto or q["official_repo"] not in REPOS or BAD.search(q["issue"]):
                    continue
                assert i not in used and i in terms
                used[i]=q["official_repo"]
                write(out,dict(panel="kimi_replication",repo=used[i],id=i,events=parent.extract(q["events"],terms[i],replicate.pol)))
    save(ROOT/"freeze.json",{"n_selected":len(used),"n_veto":len(veto),"source":{f.relative_to(WORK).as_posix():digest(f) for f in [*files,terminal]},
         "files":{n:digest(ROOT/n) for n in ["PROTOCOL.md","evaluate.py","independent.jsonl.gz","../run.py",
                                             "../observations.jsonl.gz","../predictions_lock.json","../../prepare.py","../../score.py"]}})

def trajectories():
    yield from rows(ROOT.parent/"observations.jsonl.gz")
    yield from rows(ROOT/"independent.jsonl.gz")

def make():
    seal=json.loads((ROOT/"freeze.json").read_bytes())
    assert all(digest(ROOT/f)==h for f,h in seal["files"].items())
    with gzip.GzipFile(str(ROOT/"predictions.jsonl.gz"),"wb",mtime=0) as out, gzip.GzipFile(str(ROOT/"prefetch.jsonl.gz"),"wb",mtime=0) as pf:
        for q in trajectories():
            first=median=None
            seen={}
            for t,((s,active,arms),ev) in enumerate(zip(parent.forecasts(q["events"]),q["events"],strict=True),1):
                assert s==t
                write(out,[q["id"],t,[*arms,first or arms[0],median or arms[0]]])
                if not ev:
                    continue
                kind,path,ns=ev
                if kind=="search":
                    first=[path,ns[0]]
                    median=[path,sorted(ns)[(len(ns)-1)//2]]
                    write(pf,[q["id"],t,path,ns[0],seen.get(path,1)])
                else:
                    first=median=None
                    seen[path]=sorted(ns)[(len(ns)-1)//2]
    save(ROOT/"predictions_lock.json",{"files":{n:digest(ROOT/n) for n in ["freeze.json","prefetch.jsonl.gz","predictions.jsonl.gz"]}})

def finish(row,why,target=None):
    record={k:v for k,v in row.items() if k not in ("grep",)}
    path=row["path"]
    p,ns=target if target else ("",[])
    shown=set(ns)
    record.update(reason=why,target_rows=len(shown),same_file=(p==path),short16=bool(shown) and len(shown)<=16,
                  short64=bool(shown) and len(shown)<=64)
    for cond,anchor in zip(("search","path_only"),row["anchors"]):
        lo=1+16*((anchor-1)//16)
        intersect=shown.intersection(range(lo,lo+16)) if path==p else set()
        record[cond]=dict(rows=len(intersect),new=len(intersect-set(row["grep"])),
                          full=int(bool(shown) and intersect==shown))
    return record

def cost(rs):
    result={"attempts":len(rs),"eligible_reads":sum(x["target_rows"]>0 for x in rs),
            "target_rows":sum(x["target_rows"] for x in rs),"reasons":collections.Counter(x["reason"] for x in rs)}
    for cond in ("search","path_only"):
        n=len(rs)
        hits=sum(x[cond]["rows"]>0 for x in rs)
        new=sum(x[cond]["new"] for x in rs)
        total=sum(x[cond]["rows"] for x in rs)
        full=sum(x[cond]["full"] for x in rs)
        result[cond]=dict(hits=hits,misses=n-hits,used=total,unconsumed_capacity=16*n-total,new=new,full=full,
                          new_rows_per_attempt=new/n if n else None,full_share=full/n if n else None)
    return result

def score():
    assert all(digest(ROOT/n)==v for n,v in json.loads((ROOT/"predictions_lock.json").read_bytes())["files"].items())
    assert all(digest(ROOT/n)==v for n,v in json.loads((ROOT/"freeze.json").read_bytes())["files"].items())
    it=iter(rows(ROOT/"predictions.jsonl.gz"))
    triggers={(i,t):(p,n,c) for i,t,p,n,c in rows(ROOT/"prefetch.jsonl.gz")}
    gains=[]
    visits=[]
    for r in trajectories():
        slot=None
        for t,ev in enumerate(r["events"],1):
            iid,step,arms=next(it)
            assert (iid,step)==(r["id"],t)
            if slot and t-slot["t"]>2:
                gains.append(finish(slot,"expired"))
                slot=None
            if ev is None:
                continue
            k,p,ns=ev
            if k=="search":
                if slot:
                    gains.append(finish(slot,"replaced"))
                cp,first,base=triggers.pop((iid,t))
                assert cp==p and first==ns[0]
                slot=dict(panel=r["panel"],repo=r["repo"],id=iid,t=t,path=p,anchors=[first,base],grep=ns)
            elif k=="edit":
                if slot:
                    gains.append(finish(slot,"edit"))
                    slot=None
            else:
                assert k in ("view","shell")
                if slot:
                    gains.append(finish(slot,"read",(p,ns)))
                    slot=None
                flags=[int(a is not None and a[0]==p and a[1] in ns) for a in arms]
                visits.append(dict(panel=r["panel"],id=iid,repo=r["repo"],t=t,n=len(ns),kind=k,hit=flags))
        if slot:
            gains.append(finish(slot,"end"))
    assert not triggers and next(it,None) is None
    for name,series in [("cost_rows",gains),("visits",visits)]:
        with gzip.GzipFile(str(ROOT/(name+".jsonl.gz")),"wb",mtime=0) as fp:
            for q in series:write(fp,q)
    summary={}
    prior=json.loads((ROOT.parent/"results.json").read_bytes())
    for panel in ("kimi","claude","kimi_replication"):
        v=[q for q in visits if q["panel"]==panel]
        g=[q for q in gains if q["panel"]==panel]
        h=[sum(q["hit"][a] for q in v) for a in range(5)]
        if panel!="kimi_replication":
            assert h[:3]==prior["panels"][panel]["all"]["totals"]["hit"]
        comp={}
        for name,j in (("baseline",0),("path_only",2),("unlimited_first",3),("unlimited_median",4)):
            ps=[dict(repo=q["repo"],id=q["id"],delta=q["hit"][1]-q["hit"][j]) for q in v]
            ds=[p["delta"] for p in ps]
            comp[name]=dict(wins=ds.count(1),losses=ds.count(-1),delta_pp=100*sum(ds)/len(ds),
                            ci95_task=bootstrap(ps,"id"))
        summary[panel]=dict(tasks=len({q["id"] for q in v}),repos=len({q["repo"] for q in v}),reads=len(v),target_rows=sum(q["n"] for q in v),
                            hit=h,comparisons=comp,cost=cost(g),cost_short16=cost([q for q in g if q["short16"]]),
                            cost_short64=cost([q for q in g if q["short64"]]))
        print(panel,len(v),h,comp["baseline"],"cost",summary[panel]["cost"])
    save(ROOT/"results.json",summary)

if __name__=="__main__":
    {"prepare":collect,"predict":make,"score":score}[sys.argv[1]]()
