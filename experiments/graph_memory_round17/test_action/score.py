"""Validate fresh JUnit results against the earlier full-suite oracle after the choices are frozen."""
from collections import Counter,defaultdict
from math import comb
from pathlib import Path
import json
import xml.etree.ElementTree as ET
from study import ROOT, GROUPS, h, lock, read, save

def paired(rows,a,b):
    w=sum(r[a]["caught"] and not r[b]["caught"] for r in rows)
    l=sum(r[b]["caught"] and not r[a]["caught"] for r in rows)
    n=w+l
    p=min(1.0,2*sum(comb(n,i) for i in range(min(w,l)+1))/(2**n)) if n else 1.0
    return {"wins":w,"losses":l,"ties":len(rows)-n,"different_actions":sum(r[a]["node"]!=r[b]["node"] for r in rows),"p":p}

def main():
    lock()
    decisions=read(ROOT/"decisions.json")
    executed={(r["commit"],r["arm"]):r for r in map(json.loads,(ROOT/"executions.jsonl").read_bytes().splitlines())}
    full={}
    panels={}
    for label in GROUPS:
        for r in read(ROOT.parent/label/"testmon-graded.gz"):
            assert r["truth"] in ("fail","pass")
            full[r["commit"],r["node"]] = r["truth"]=="fail"
            panels[r["commit"]]=label
    by=defaultdict(dict)
    for row in decisions:
        k,a,node=row["commit"],row["arm"],row["node"]
        z=executed.get((k,a))
        if node is not None:
            assert z and z["node"]==node and z["failed"]==full[k,node]
            q=list(ET.fromstring(z["xml"]).iter("testcase"))
            assert len(q)==1 and z["failed"]==(q[0].find("failure") is not None or q[0].find("error") is not None)
        by[k][a]={"caught":bool(z and z["failed"]),"node":node,"valid":node is not None}
    assert len(executed)==sum(x["node"] is not None for x in decisions)
    results={}
    for panel in ("all",*GROUPS):
        keys=[k for k in by if panel=="all" or panels[k]==panel]
        rows=[by[k] for k in keys];arms=rows[0]
        results[panel]=dict(n=len(rows),opportunity=sum(any(v for (k,n),v in full.items() if k==key) for key in keys),
                    caught={a:sum(row[a]["caught"] for row in rows) for a in arms},
                    paired={a+"-"+b:paired(rows,a,b) for a,b in (("graph","names"),("graph","permuted"),("graph","rank_graph"),
                                                                   ("names","rank_names"),("rank_graph","rank_names"))})
    calls=list(map(json.loads,(ROOT/"calls.jsonl").read_bytes().splitlines()))
    resources=dict(unique_calls=len(calls),valid_executions=len(executed),
                   input_tokens=sum(z["response"]["usage"]["prompt_tokens"] for z in calls),
                   output_tokens=sum(z["response"]["usage"]["completion_tokens"] for z in calls),
                   model_seconds=sum(z["seconds"] for z in calls),test_seconds=sum(z["seconds"] for z in executed.values()))
    save("results.json",{"panels":results,"by_commit":by,"resources":resources})
    print(resources,results["all"], {p:results[p]["caught"] for p in GROUPS})


if __name__=="__main__":
    main()

