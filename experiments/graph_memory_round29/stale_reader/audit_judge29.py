"""Independent masked reviewer agreement and consistency on literally identical candidate answers."""
from collections import defaultdict,Counter
from setup29 import D,P,sha,read,save,Path
def tab(pairs):
    counts=Counter((a,b) for a,b in pairs)
    return {"n":len(pairs),"agree":sum(a==b for a,b in pairs),
            "local_by_independent":{"/".join(k):v for k,v in sorted(counts.items())}}
def main():
    items=[r for r in read(D/"score-rows.json.gz") if "grade" in r]
    audit_keys=read(P/"audit-map.json");packet=read(P/"audit-packet.json")
    raw=read(P/"peer-ratings.json")
    if isinstance(raw,list):raw={r["token"]:r for r in raw}
    if "ratings" in raw:raw=raw["ratings"]
    blind={k:str(v["label"] if isinstance(v,dict) else v) for k,v in raw.items()}
    assert set(audit_keys)==set(blind)=={p["token"] for p in packet}
    by={(r["q"],r["arm"]):r for r in items};public={};pairs=defaultdict(list);pool=defaultdict(list)
    for r in items:
        pool[r["q"],r["answer_sha"]].append(r)
    conf=[]
    for (q,a),members in pool.items():
        if len(members)>1 and len({r["grade"] for r in members})>1:
            conf.append({"q":q,"answer_sha":a,"mode":members[0]["mode"],"grades":{r["arm"]:r["grade"] for r in members}})
    for k,(q,arm) in audit_keys.items():
        item=by[q,arm];g=item["grade"];y=blind[k];group="historical" if item["mode"].startswith("past") else "native"
        assert y in ("V","R","U","X") if group=="historical" else y in ("0","1")
        pairs[group].append((g,y));public[k]={"grade":g,"independent":y,"mode":item["mode"],"q":q,"arm":arm}
    vals=[(g=="V",h=="V") for g,h in pairs["historical"]]
    result=dict(scored=sha(D/"score-rows.json.gz"),packet=sha(P/"audit-packet.json"),independent=sha(P/"peer-ratings.json"),
                mapping=sha(P/"audit-map.json"),code=sha(Path(__file__)),grades=public,native=tab(pairs["native"]),historical=tab(pairs["historical"]),
                historical_correct_binary=sum(x==y for x,y in vals),all=tab(pairs["native"]+pairs["historical"]),
                repeated_exact_groups=sum(len(v)>1 for v in pool.values()),inconsistent_exact_groups=conf)
    save(D/"judge-audit.json",result)
    print({k:result[k] for k in ("native","historical","all","repeated_exact_groups")},len(conf))
if __name__=="__main__":main()
