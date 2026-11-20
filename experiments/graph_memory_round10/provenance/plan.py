"""Lock confirmation schedules based exclusively on bytes returned by historical MemTrace."""
from common import *
from collections import Counter

POLICIES=("empty","strict","unchecked","fixed","selected","carry_all","confirm_all")
def main():
    records=get(ROOT/"inputs.gz");past={s["key"]:s for s in get(ROOT/"history.gz")}
    out=[];red=Counter()
    for r in records:
        reader=past[r["key"]];nodes=[o["node"] for o in r["items"]]
        n=len(nodes);b=n//3
        history=[v["historical"] for v in reader["answers"]]
        ties=[sha(packed([r["task"],r["direction"],k,"r10-priority"])) for k in nodes]
        for policy in POLICIES:
            bits=reader["packets"].get(policy)
            if bits is not None:assert all(x or not exact for x,exact in zip(bits,r["expected_impact"]))
            if policy=="empty":order=sorted(range(n),key=lambda i:ties[i])
            else:
                order=sorted(range(n),key=lambda i:(int(not bits[i]) if bits is not None else 0,
                             int(history[i]!="failed"),ties[i]))
            cap=n if policy=="confirm_all" else (0 if policy=="carry_all" else b)
            paid=set(order[:cap])
            for i,node in enumerate(nodes):
                infer=policy in ("unchecked","carry_all") or (bits is not None and not bits[i])
                action="confirm" if i in paid else ("historical_prediction" if infer and history[i] in ("passed","failed") else "abstain")
                out.append(dict(key=r["key"],policy=policy,node=node,source=action,historical=history[i] if action=="historical_prediction" else None,
                                dependency_hit=bits[i] if bits is not None else None))
                red[policy,action]+=1
    put(ROOT/"plans.gz",out)
    put(ROOT/"plan-lock.json",dict(inputs=fh(ROOT/"inputs.gz"),history=fh(ROOT/"history.gz"),plans=fh(ROOT/"plans.gz"),
                    code={n:fh(ROOT/n) for n in ("PROTOCOL_RU.md","SMOKE.py","common.py","native_reads.py","plan.py")}))
    print(len(out), sorted(red.items()))
if __name__=="__main__":main()
