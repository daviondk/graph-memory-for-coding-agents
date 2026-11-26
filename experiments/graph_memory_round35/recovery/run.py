import os,sys,tempfile,subprocess,platform
from collections import Counter
from support import *
def difference(got,oracle):
    return [len(set(got)-oracle),len(oracle-set(got))]
def main():
    plan=load(D/"plan.json");assert plan["source"]==sha(D/"source.sqlite3") and plan["protocol"]==sha(D/"PROTOCOL_RU.md")
    for n,v in plan["engine"].items():assert sha(D/n)==v
    logs,hashes,ss=original();assert plan["id_hashes"]==hashes and plan["operations"]==ss
    out=[];summ={}
    with tempfile.TemporaryDirectory(prefix="r35-recovery-",dir=D) as temp:
        for case in plan["cases"]:
            cid=case["case"];hist=case["history"]; loc=Path(temp)/str(cid);loc.mkdir();args=[sys.executable,str(D/"worker.py")];tail=[json.dumps(case,separators=(",",":")),str(loc)]
            dead=subprocess.run(args+["crash"]+tail,capture_output=True,text=True);assert dead.returncode==73,(cid,dead.stderr)
            pre=json.loads(dead.stdout);assert all(x>0 for x in pre["wal_bytes"]) and pre["in_transaction"]==[case["type"]=="uncommitted_first"]*2
            rr=subprocess.run(args+["restart"]+tail,capture_output=True,text=True);assert rr.returncode==0,(cid,rr.stderr)
            rec=json.loads(rr.stdout);assert pre["pid"]!=rec["pid"] and os.getpid() not in (pre["pid"],rec["pid"])
            log=logs[hist];at=case["received"];b=case["barrier"];live=set();base=set();since=set();truth={};u=d=0
            for i,(_,_,cuts,add,rm) in enumerate(log,1):
                live.update(add);live.difference_update(rm)
                if i==b:base=set(live)
                if b<i<=at:since.update(add);u+=len(add);d+=len(rm)
                if cuts and i>at:truth[i]=set(live)
            assert next(iter(truth))==at+1
            row={**case,"crash_pid":pre["pid"],"restart_pid":rec["pid"],"pending_at_crash":len((base|since)-((base|since) if at==0 else immediate_before(log,at))),"wal_bytes":pre["wal_bytes"],"branches":{}}
            for mode,x in rec["branches"].items():
                replay=mode=="replay";assert x["b"]==b and set(x["initial"])==base|since and x["final_b"]==max(truth)
                assert (x["replayed_rows"],x["up"],x["down"],x["replay_selects"])==((at-b,u,d,1) if replay else (0,0,0,0));assert x["ignored_inserts"]==(u if replay else 0)
                assert [i for i,v in x["reads"]]==list(truth)
                diff=[difference(v,truth[i]) for i,v in x["reads"]];term=difference(x["terminal"],live)
                if replay:assert not any(any(y) for y in diff+[term])
                row["branches"][mode]={"next":diff[0],"terminal":term,"reads":diff,"reread_rows":x["replayed_rows"],"reread_up":x["up"],"reread_down":x["down"],"idempotent_ignores":x["ignored_inserts"],"range_selects":x["replay_selects"]}
            out.append(row)
    for group in ("first","third","post","uncommitted_first"):
        xs=[r for r in out if (r["type"] in ("first","third") if group=="post" else r["type"]==group)]
        stat={"cases":len(xs),"histories":len({v["history"] for v in xs}),"distinct_positions":len({(v["history"],v["received"]) for v in xs}),"nonempty_queue":sum(r["pending_at_crash"]>0 for r in xs),"max_pending_pairs":max(r["pending_at_crash"] for r in xs),"max_wal_bytes_per_db":max(max(r["wal_bytes"]) for r in xs),"methods":{}}
        for m in ("naive","replay"):
            xx=[r["branches"][m] for r in xs];rrs=sorted(v["reread_rows"] for v in xx);n=len(rrs)
            stat["methods"][m]={"next_mismatch":sum(any(v["next"]) for v in xx),"terminal_mismatch":sum(any(v["terminal"]) for v in xx),"reads":sum(len(v["reads"]) for v in xx),"wrong_reads":sum(any(p) for v in xx for p in v["reads"]),"histories_wrong_next":len({r["history"] for r in xs if any(r["branches"][m]["next"])}),"next_extra":sum(v["next"][0] for v in xx),"next_missing":sum(v["next"][1] for v in xx),"terminal_extra":sum(v["terminal"][0] for v in xx),"from_snapshot_rows":sum(rrs),"nonzero_ranges":sum(v>0 for v in rrs),"range_selects":sum(v["range_selects"] for v in xx),"p50_rows":(rrs[(n-1)//2]+rrs[n//2])/2,"p95_rows_nearest_rank":rrs[(95*n+99)//100-1],"max_rows":rrs[-1],"ups":sum(v["reread_up"] for v in xx),"downs":sum(v["reread_down"] for v in xx),"ignored_insertions":sum(v["idempotent_ignores"] for v in xx)}
        summ[group]=stat
    save(D/"cases.json.gz",out);save(D/"results.json",{"groups":summ,"new_process_pairs":len(out),"wal":True,"synchronous":"FULL","sqlite":sqlite3.sqlite_version,"python":platform.python_version(),"platform":platform.platform(),"plan":sha(D/"plan.json"),"case_sha":sha(D/"cases.json.gz")});print(summ["post"],flush=True)
def immediate_before(log,at):
    alive=set()
    for _,_,_,plus,minus in log[:at]:alive|=set(plus);alive-=set(minus)
    return alive
if __name__=="__main__":main()
