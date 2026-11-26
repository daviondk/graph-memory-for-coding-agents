"""Run SQLite on the local disk. Per-episode states are isolated by integer key."""
from inputs import D,get,put,sha,h
from storage import initialize,transition,lookup,rows
from pathlib import Path
from tempfile import TemporaryDirectory
from itertools import permutations
from time import perf_counter_ns
import ctypes,sqlite3,sys,platform,os

kernel=ctypes.WinDLL("kernel32",use_last_error=True)
kernel.GetCurrentThread.restype=ctypes.c_void_p
kernel.QueryThreadCycleTime.argtypes=(ctypes.c_void_p,ctypes.POINTER(ctypes.c_ulonglong))
def cycles():
    x=ctypes.c_ulonglong()
    if not kernel.QueryThreadCycleTime(kernel.GetCurrentThread(),ctypes.byref(x)):raise ctypes.WinError(ctypes.get_last_error())
    return x.value
def stats(db,path,kind):
    t=("f","v","r") if kind=="L" else ("f",)
    return dict(sql_counts={k:db.execute("SELECT COUNT(*) FROM "+k).fetchone()[0] for k in t},page_count=db.execute("PRAGMA page_count").fetchone()[0],
            page_size=db.execute("PRAGMA page_size").fetchone()[0],main=path.stat().st_size,wal=Path(str(path)+"-wal").stat().st_size)
def main():
    plan=get(D/"plan.json");assert sha(D/"storage.py")==plan["sqlite_code"] and sha(Path(__file__))==plan["benchmark_code"]
    assert sha(D/"prefix_inputs.json.gz")==plan["input"] and sha(D/"reference.json.gz")==plan["evaluator"]
    x=get(D/"prefix_inputs.json.gz");ref={q:rows(v) for q,v in get(D/"reference.json.gz").items()}
    for v in x.values():
        v["base"]=rows(v["base"]);v["receipt"]=dict(rows(v["receipt"]))
    full={};io_phys={};timed={q:[] for q in plan["panel"]};methods=("A","M","L");orders=list(permutations(methods))
    # All working DB files live in a fresh temporary subdirectory on the same D volume.
    with TemporaryDirectory(dir=D,prefix="sqlite_") as td:
        for rep in range(-2,6):  # first exhaustive accounting, then warmup, six measured schedules
            qs=sorted(x) if rep==-2 else plan["panel"]; items={i:x[q] for i,q in enumerate(qs)}
            files={k:Path(td)/(k+str(rep)+".sqlite") for k in methods}
            db={k:initialize(files[k],k,items) for k in methods}
            if rep==-2:before={k:stats(db[k],files[k],k) for k in methods}
            for i,q in enumerate(qs):
                item=x[q];sample={}
                if rep==-2:full[q]={}
                offset=int(h("sqlite-order|"+q)[:12],16)%6
                order=orders[(max(rep,0)+offset)%6]
                for k in order:
                    con=db[k];wp=Path(str(files[k])+"-wal")
                    if rep==-2:startwal=wp.stat().st_size
                    w=perf_counter_ns();cc=cycles()
                    writes,nprep,selectprep=transition(con,k,i,item)
                    cw=cycles()-cc;ww=perf_counter_ns()-w
                    w=perf_counter_ns();cc=cycles()
                    val,nread=lookup(con,k,i,item)
                    cr=cycles()-cc;wr=perf_counter_ns()-w
                    assert val==ref[q] and len(set(n for n,s in val))==len(val)
                    if rep==-2:
                        endwal=wp.stat().st_size;delta=endwal-startwal
                        page=before[k]["page_size"]
                        frames=(delta-(32 if startwal==0 and delta else 0))//(page+24)
                        assert delta==frames*(page+24)+(32 if startwal==0 and delta else 0)
                        full[q][k]=dict(writes=writes,pre_read_rows=nprep,pre_selects=selectprep,read_rows=nread,read_selects=1,rows_out=len(val),wal_bytes=delta,wal_frames=frames)
                    else:
                        w=perf_counter_ns();cc=cycles()
                        last=[lookup(con,k,i,item)[0] for _ in range(3)]
                        c3=cycles()-cc;w3=perf_counter_ns()-w
                        assert all(v==val for v in last)
                        sample[k]=[ww,wr,w3,cw,cr,c3]
                if rep>=0:timed[q].append(sample)
            if rep==-2:io_phys={k:dict(initial=before[k],final=stats(db[k],files[k],k)) for k in methods}
            for con in db.values():con.close()
            print("block",rep,len(qs),flush=True)
        a=put(D/"full_counts.json.gz",full);b=put(D/"timings.json.gz",timed)
        put(D/"run-seal.json",dict(plan=sha(D/"plan.json"),full=a,timed=b,sqlite_version=sqlite3.sqlite_version,
            python=platform.python_version(),page_metrics=io_phys,columns=["update_wall","first_read_wall","three_more_wall","update_cycles","first_read_cycles","three_more_cycles"]))
if __name__=="__main__":main()
