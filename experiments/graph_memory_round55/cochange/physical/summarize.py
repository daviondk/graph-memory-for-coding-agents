"""Summarize paired blocks; timings are empirical evidence and must not be regenerated for hash checks."""
import argparse
from collections import defaultdict
from hashlib import sha256
from statistics import median
from bench import HERE, PLANS, read_json, write_json

def main(check):
    data=read_json(HERE/"timings.json.gz")
    results={}
    for storage in ("memory","wal"):
        block=defaultdict(lambda:defaultdict(lambda:defaultdict(int)))
        repos=defaultdict(lambda:defaultdict(list))
        for rep,medium,project,plan,sequence,stats in data["runs"]:
            if medium!=storage:
                continue
            for k,v in stats.items():
                block[rep][plan][k]+=v
            repos[project][plan].append(stats["full_ns"]/1e6)
        assert len(block)==7 and all(len(v)==5 for v in block.values())
        plans={}
        for name in PLANS:
            plans[name]={}
            for key in ("full_ns","index_ns","cold_control_ns","cold_sql_ns"):
                values=[block[i][name][key]/1e6 for i in range(7)]
                plans[name][key.replace("_ns","_ms")]={"median":median(values),"by_block":values}
        pairs={}
        for a,b in (("partial8","classic9"),("partial8","classic8"),("partial12","classic13")):
            pair={}
            for k in ("full_ms","index_ms"):
                delta=[x-y for x,y in zip(plans[a][k]["by_block"],plans[b][k]["by_block"],strict=True)]
                pair[k]={"differences":delta,"median":median(delta),"range":[min(delta),max(delta)],
                         "a_faster":sum(v<0 for v in delta)}
            pairs[a+"-"+b]=pair
        results[storage]={"plans":plans,"paired":pairs,
             "median_full_ms_by_project":{p:{n:median(ts) for n,ts in rec.items()} for p,rec in repos.items()}}
    write_json(HERE/"timing-results.json",results,check)
    for s,item in results.items():
        print(s,[(p,round(g["full_ms"]["median"],2),round(g["index_ms"]["median"],3),
                  round(g["cold_control_ms"]["median"],3)) for p,g in item["plans"].items()])
        for k,g in item["paired"].items():
            print(k,round(g["full_ms"]["median"],3),g["full_ms"]["range"],g["full_ms"]["a_faster"],
                  round(g["index_ms"]["median"],3),g["index_ms"]["a_faster"])
if __name__=="__main__":
    ap=argparse.ArgumentParser()
    ap.add_argument("--verify",action="store_true")
    main(ap.parse_args().verify)
