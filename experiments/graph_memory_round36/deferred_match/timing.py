from common_match import *
from time import process_time_ns,perf_counter_ns
from types import SimpleNamespace
import sqlite3,itertools,platform,ctypes
kernel=ctypes.WinDLL("kernel32",use_last_error=True)
kernel.GetCurrentThread.restype=ctypes.c_void_p
kernel.QueryThreadCycleTime.argtypes=(ctypes.c_void_p,ctypes.POINTER(ctypes.c_ulonglong))
def cycles():
    result=ctypes.c_ulonglong()
    if not kernel.QueryThreadCycleTime(kernel.GetCurrentThread(),ctypes.byref(result)):raise ctypes.WinError(ctypes.get_last_error())
    return result.value
ARMS=("eager","deferred_ref","deferred_sql")
def material(evs,store,events,mode):
    if mode=="eager":
        m=eager.HistoricalFeeds()
        for i,e,has in evs:m.consume(e,has)
    else:
        m=DeferredFeeds(events.__getitem__ if mode=="deferred_ref" else store)
        for i,e,has in evs:m.consume(e,i,has)
    return m.observed_pairs
def one(t,events,chunks):
    steps=[(i,e,e.event_type=="tool_output" and chunks[e.call_id]>0) for i,e in enumerate(events) if e.event_type in ("tool_call","tool_output")]
    db=sqlite3.connect(":memory:");db.execute("pragma temp_store=MEMORY");db.execute("create table args(h integer primary key, raw text not null, parsed text not null)")
    db.executemany("insert into args values (?,?,?)",[(i,*args_wire(e)) for i,e,_ in steps if e.event_type=="tool_call"]);db.commit();assert all(not f for _,_,f in db.execute("pragma database_list"))
    def fetch(h):
        raw,parsed=db.execute("select raw, parsed from args where h=?",(h,)).fetchone()
        return SimpleNamespace(raw_arguments=raw,arguments=json.loads(parsed))
    base=None
    for mode in ARMS:
        got=material(steps,fetch,events,mode)
        if base is None:base=got
        assert got==base
    rec={};by_block=[];s=int.from_bytes(hashlib.sha256(t.encode()).digest()[:8],"big")
    perms=list(itertools.permutations(ARMS));start=perms[s%6]
    for j in range(4):
        order=start if j%2==0 else start[::-1];samples={}
        for method in order:
            wall=perf_counter_ns();cpu=process_time_ns();cy=cycles();result=material(steps,fetch,events,method);work=cycles()-cy;dt=process_time_ns()-cpu;wt=perf_counter_ns()-wall
            assert result==base;samples[method]=[dt,wt,work]
        by_block.append(samples)
    # Instrument a separate SQL replay to record actual payload returned by SQLite.
    receipts=[0,0,0]
    def traced(h):
        raw,parsed=db.execute("select raw, parsed from args where h=?",(h,)).fetchone();receipts[0]+=1;receipts[1]+=len(raw.encode());receipts[2]+=len(parsed.encode());return SimpleNamespace(raw_arguments=raw,arguments=json.loads(parsed))
    assert material(steps,traced,events,"deferred_sql")==base
    db.close();return {"measurements":by_block,"order":list(start),"events":len(steps),"actual_sql_receipts":receipts}
def main():
    assert (D/"plan.json").exists();panel=load(D/"plan.json")["timed_ids"];timed={}
    for sh in range(8):
        for t,events,chunks,_ in rows(sh,panel):timed[t]=one(t,events,chunks)
        print("timed",sh,len(timed),flush=True)
    assert set(timed)==set(panel);p=D/"timings.json.gz";put(p,timed);put(D/"timing-seal.json",dict(cpu_clock=__import__("time").get_clock_info("process_time").implementation,cpu_resolution=__import__("time").get_clock_info("process_time").resolution,
        wall_resolution=__import__("time").get_clock_info("perf_counter").resolution,python=platform.python_version(),sqlite=sqlite3.sqlite_version,samples=sha(p),plan=sha(D/"plan.json"),code=sha(Path(__file__))))
if __name__=="__main__":main()