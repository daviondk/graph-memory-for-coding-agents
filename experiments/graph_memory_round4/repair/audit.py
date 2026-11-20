"""Reconstruct the reported counts, pairings, historical/future split and bounded writes from disk."""
import ast
from collections import Counter
from base import D, read, save, sha, stable
from prepare import assertions

def main():
    past, future, out, packets, full = [read(n+".json.gz") for n in ["past","future","per_task","packets","full_suite_items"]]
    official={r["task_id"]:r for r in read("humanevalpack.json")}
    rs=read("results.json"); fs=read("full_results.json")
    assert len(past)==len({r["id"] for r in past})==64
    overlap=0
    for p,f,s,c,d in zip(past,future,out,packets,full,strict=True):
        assert p["id"]==f["id"]==s["id"]==c["id"]==d["id"]
        _,every_old=assertions(official[p["id"]])
        for args,_,_ in f["novel"]:
            overlap+=sum(args==a for a in every_old)
        for arm in ("failed","recent","individual","union"):
            assert len(c["memory"][arm])<=2 and len(stable(c["memory"][arm]).encode())<=384
        for k,v in s["methods"].items():
            b=s["receipts"][v["hash"]]["bits"];h=s["historical"]
            assert sum(b[h:])==v["new"] and sum(b[:h])==v["old"] and v["hit"]==int(all(b[h:]))
    assert not overlap
    for k,tot in rs["scores"].items():
        assert tot["all"]==sum(s["methods"][k]["hit"] for s in out)
    for suite,metrics in fs["results"].items():
        for k,counts in metrics["all"]["scores"].items():
            assert counts==dict(Counter(s["tests"][suite][k]["status"] for s in full))
    keys=set()
    for folder in ["calls","sample_calls"]:
        for p in (D/folder).glob("*.gz"):
            x=read(p);assert p.name.split(".")[0]==sha(stable(x["request"]))
            assert x["reply"]["id"] not in keys;keys.add(x["reply"]["id"])
    assert len(keys)==rs["native_calls"]==286
    save("audit.json",{"verified_tasks":len(out),"raw_generations":len(keys),"cross_split_argument_intersection":overlap,"historical":sum(len(x["cards"]) for x in past),"future":sum(len(x["novel"]) for x in future),"recomputed_all_methods":len(rs["scores"]),"full_suites":["human","plus"],"full_unique_program_suite_jobs":fs["unique_runs"],"all_bounded_writes_within_limits_at_final_checkpoint":True,"verified_sha256":{n:sha((D/n).read_bytes()) for n in ["results.json","per_task.json.gz","full_results.json","full_suite_items.json.gz","choices_lock.json"]}})
if __name__=="__main__":main()

