"""Choose optional evidence before observing the completion, then evaluate against a rate-matched control."""
import re
import sys
from collections import defaultdict
from infer import D, read, save, sha
from infer import main as infer

def headers(snippet):
    types = re.findall(r"\b(?:class|interface|enum|record|new)\s+([A-Za-z_$][\w$]*)", snippet)
    methods = re.findall(r"\b(?:[A-Za-z_$][\w$<>.,?\[\]]*\s+)+([A-Za-z_$][\w$]*)\s*\(", snippet)
    return set(types + methods) - {"if","for","while","try","switch","catch","return","new","super","this"}

def plan():
    plan = {}
    for key in ("A","B"):
        rows = read(key+"_packets.json.gz")
        items = {}
        strata = defaultdict(list)
        for row in rows:
            names = headers(row["snippets"]["graph"][0])
            context = set(re.findall(r"[A-Za-z_$][\w$]*", row["ctx"]))
            hits = sorted(names & context)
            items[row["id"]] = {"use":bool(hits),"hits":hits}
            strata[row["panel"]].append(row["id"])
        for ids in strata.values():
            n = sum(items[i]["use"] for i in ids)
            control = set(sorted(ids,key=lambda i:sha("r4matched-random|"+i))[:n])
            for i in ids:
                items[i]["random"] = i in control
        plan[key]=items
    save("selective_choices.json",plan)
    packets = read("B_packets.json.gz")
    for x in packets:
        x["snippets"]={"empty":["(no external fragment)",0]}
    save("Z_packets.json.gz",packets)
    save("Z_data_lock.json",{n:sha((D/n).read_bytes()) for n in ["B_data_lock.json","A_data_lock.json","SELECTIVE_READ_RU.md","selective_choices.json","selective.py","Z_packets.json.gz"]})

def grade():
    from score import paired, first, sim
    from math import comb
    import numpy as np
    assert all(sha((D/n).read_bytes())==v for n,v in read("Z_data_lock.json").items())
    assert all(sha((D/"Z_calls"/n).read_bytes())==v for n,v in read("Z_decisions.json").items())
    plan = read("selective_choices.json")
    lookup=read("Z_assignment.json")
    report={}
    for key in ("A","B"):
        rows=read(key+"_items.json.gz")
        for x in rows:
            m=x["methods"]
            if key=="B":
                k=lookup[x["id"]]["empty"];r=read("Z_calls/"+k+".json.gz")["reply"]
                out=first(r["choices"][0]["message"].get("content") or "")
                m["empty"]={"em":int(out==x["gold"]),"es":sim(out,x["gold"]),"prompt_tokens":r["usage"]["prompt_tokens"],"snippet_tokens":0,"generated":out}
            for dest in ("use","random"):
                m[dest]=m["graph"] if plan[key][x["id"]][dest] else m["empty"]
        tab={k:{field:(sum(v) if field=="em" else float(np.mean(v))) for field in ["em","es","prompt_tokens","snippet_tokens"] if (v:=[x["methods"][k][field] for x in rows])} for k in rows[0]["methods"]}
        pairs={a+"-"+b:{f:paired(rows,a,b,f) for f in ["em","es","prompt_tokens"]} for a,b in [("use","random"),("use","graph"),("graph","empty"),("semlith","empty"),("use","empty")]}
        report[key]=dict(n=len(rows),read=sum(x["use"] for x in plan[key].values()),methods=tab,pairs=pairs)
        save(key+"_selective_items.json.gz",rows)
    save("selective_results.json",report)

if __name__=="__main__":
    if sys.argv[1]=="plan":plan()
    elif sys.argv[1]=="infer":infer("Z")
    elif sys.argv[1]=="grade":grade()

