"""Paired ingest-edit-read workload on local D; schedule deliberately unavailable to edit()."""
from inputs import *
from engine import dbopen,compile_model,ingest,edit,answer
from tempfile import TemporaryDirectory
from itertools import permutations
from time import perf_counter_ns
from pathlib import Path
import ctypes,sqlite3

kernel=ctypes.WinDLL("kernel32",use_last_error=True);kernel.GetCurrentThread.restype=ctypes.c_void_p
kernel.QueryThreadCycleTime.argtypes=(ctypes.c_void_p,ctypes.POINTER(ctypes.c_ulonglong))
def cycles():
    x=ctypes.c_ulonglong()
    if not kernel.QueryThreadCycleTime(kernel.GetCurrentThread(),ctypes.byref(x)):raise ctypes.WinError(ctypes.get_last_error())
    return x.value

def reference(item):
    receipt=dict(item["receipt"]);extra={}
    for n,s in item["base"]:
        k=item["start"]
        if k is None or k<=n<=item["end"]:continue
        target=n if n<k else n+item["delta"]
        if target not in receipt:extra[target]=s
    left=128-len(receipt)
    for n in sorted(extra,key=lambda j:(h("R37-128|"+item["path"]+"|"+str(j)),j))[:left]:receipt[n]=extra[n]
    return tuple(sorted((n,bytes.fromhex(s)) for n,s in receipt.items()))

def actual_restarts(root,panel,snap,models,dec,correct):
    path=root/"verify_restart.sqlite"
    db=dbopen(path,"H")
    for e,q in enumerate(panel):
        x=snap[q];ingest(db,"H",e,x["base"],x["past_types"],x["prev"])
    db.close();db=dbopen(path,"H",False)
    for e,q in enumerate(panel):
        x=snap[q];algo,*_=edit(db,"H",models[x["repo"]],e,None,x);assert algo==dec[q]["H"]
    db.close();db=dbopen(path,"H",False)
    for e,q in enumerate(panel):
        values,trips,_=answer(db,"H",e,snap[q]["path"],None);assert trips==1 and values==correct[q]
    db.close()
def run():
    plan=get(D/"plan.json");assert plan["engine"]==sha(D/"engine.py") and plan["timing"]==sha(Path(__file__))
    panel=plan["panel"];snap=get(D/"prefixes.json.gz");future=get(D/"schedule.json.gz");dec=get(H/"decisions.json.gz");models=get(H/"models.json")
    correct={q:reference(snap[q]) for q in panel};order=list(permutations("ALH"))
    data={s:{q:[] for q in panel} for s in ("resident","miss")};comp={s:[] for s in data}
    def compile_all():return {repo:compile_model(m["ridge"]) for repo,m in models.items()}
    with TemporaryDirectory(dir=D,prefix="runtime_") as td:
        root=Path(td)
        for rep in range(-1,6):
            for scen in (("resident","miss") if rep%2==0 else ("miss","resident")):
                w=perf_counter_ns();cc=cycles();compiled=compile_all();cy=cycles()-cc;wt=perf_counter_ns()-w
                if rep>=0:comp[scen].append([wt,cy])
                db={m:dbopen(root/(scen+m+str(rep)+".db"),m) for m in "ALH"}
                for e,q in enumerate(panel):
                    x=snap[q];timing={}
                    for mode in order[(max(rep,0)+int(h("R38-plan-order|"+q)[:16],16))%6]:
                        con=db[mode];mod=compiled[x["repo"]];before=con.total_changes
                        w=perf_counter_ns();c=cycles()
                        old=ingest(con,mode,e,x["base"],x["past_types"],x["prev"])
                        ci=cycles()-c;wi=perf_counter_ns()-w;wi_rows=con.total_changes-before
                        if scen=="miss":old=None
                        before=con.total_changes;w=perf_counter_ns();c=cycles()
                        picked,state,prep,pr=edit(con,mode,mod,e,old,x)
                        ce=cycles()-c;we=perf_counter_ns()-w;we_rows=con.total_changes-before
                        assert mode!="H" or picked==dec[q]["H"]
                        if scen=="miss":state=None
                        n=future[q]["reads"];trips=rows=0
                        if n:
                            w=perf_counter_ns();c=cycles();actual=[]
                            for _ in range(n):
                                val,tt,rr=answer(con,mode,e,x["path"],state)
                                trips+=tt;rows+=rr;state=("ready",val);actual.append(val)
                            cr=cycles()-c;wr=perf_counter_ns()-w
                            assert all(v==correct[q] for v in actual)
                        else:wr=cr=0
                        timing[mode]=[wi,we,wr,ci,ce,cr,wi_rows,we_rows,prep,pr,trips,rows,n]
                    if rep>=0:data[scen][q].append(timing)
                for con in db.values():con.close()
        actual_restarts(root,panel,snap,compiled,dec,correct)
    z=put(D/"raw.json.gz",data)
    put(D/"run-seal.json",dict(plan=sha(D/"plan.json"),raw=z,sqlite=sqlite3.sqlite_version,compile_all=comp,verified_actual_restarts=len(panel),
      columns=["ingest_wall","edit_wall","read_wall","ingest_cycles","edit_cycles","read_cycles","ingest_writes","edit_writes","edit_selects","edit_fetched","read_selects","read_fetched","nread"]))
if __name__=="__main__":run()
