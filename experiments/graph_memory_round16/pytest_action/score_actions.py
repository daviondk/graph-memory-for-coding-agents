"""Paired action scores. Clinical-sounding units are deliberately avoided: one issue contributes one item."""
import collections,gzip,json,math,statistics
from pathlib import Path
D=Path(__file__).resolve().parent
def get(n):
    b=(D/n).read_bytes();return json.loads(gzip.decompress(b) if n.endswith(".gz") else b)
def exact(b,c):
    n=b+c
    return min(1.,2*sum(math.comb(n,k) for k in range(min(b,c)+1))/2**n) if n else 1.
def main():
    ex=get("assignment.gz");data=get("ledger.json");actions={(r["uid"],r["arm"]):r["action"] for r in data}
    calls=[json.loads(l) for l in (D/"model-calls.jsonl").read_text(encoding="utf8").splitlines()];stats={};audfile=D/"blind-labels.json"
    if audfile.exists():audit=get("blind-labels.json")
    else:audit={}
    by_item=[]
    for r in ex:
        uid=r["uid"];a={arm:actions[uid,arm] for arm in ("shell","raw","parser","structured")}
        same=r["query"]==r["selector"]
        a["static_shell"]="record_passing_edge" if same and r["rc"]==0 else "queue_verification"
        a["static_parser"]="record_passing_edge" if same and r["state"]=="pass" else "queue_verification"
        item=dict(uid=uid,repo=r["repo"],iid=r["iid"],stratum=r["design"],silver=r["design"]=="positive",actions=a)
        label=audit.get(r["blind_id"])
        if label is not None:item["audited"]=((label["label"] if isinstance(label,dict) else label) in ("WRITE","write","record_passing_edge"))
        by_item.append(item)
    def summarise(items,t):
        y=sum(e[t] for e in items);res={}
        for arm in ("shell","raw","parser","structured","static_shell","static_parser"):
            v=[e["actions"][arm] for e in items];tp=sum(e[t] and e["actions"][arm]=="record_passing_edge" for e in items)
            fp=sum(not e[t] and e["actions"][arm]=="record_passing_edge" for e in items);tn=sum(not e[t] and e["actions"][arm]=="queue_verification" for e in items)
            res[arm]=dict(n=len(v),positive=y,negative=len(v)-y,true_writes=tp,false_writes=fp,correct_rechecks=tn,accuracy_count=tp+tn,
                          invalid=v.count("invalid"),rechecks=v.count("queue_verification"))
        b=c=0
        for e in items:
            target="record_passing_edge" if e[t] else "queue_verification"
            sr=e["actions"]["structured"]==target;raw=e["actions"]["raw"]==target
            b+=sr and not raw;c+=raw and not sr
        return dict(arms=res,paired_structured_vs_raw={"structured_only_correct":b,"raw_only_correct":c,"exact_two_sided_p":exact(b,c)})
    for truth in ("silver","audited"):
        selected=[e for e in by_item if truth in e]
        if selected:stats[truth]={"all":summarise(selected,truth),**{s:summarise([e for e in selected if e["stratum"]==s],truth) for s in sorted(set(e["stratum"] for e in selected))}}
    stats["cost"]={}
    for arm in ("shell","raw","parser","structured"):
        g=[r for r in calls if r["arm"]==arm];stats["cost"][arm]={"calls":len(g),"input_tokens":sum(r["response"].get("usage",{}).get("prompt_tokens",0) for r in g),
             "output_tokens":sum(r["response"].get("usage",{}).get("completion_tokens",0) for r in g),"elapsed_sum":sum(r["elapsed"] for r in g),
             "median_elapsed":statistics.median(r["elapsed"] for r in g),"median_payload_bytes":statistics.median(r["payload_bytes"] for r in g)}
    (D/"actions-scored.json").write_text(json.dumps(by_item,sort_keys=True,indent=2),encoding="utf8")
    (D/"results.json").write_text(json.dumps(stats,sort_keys=True,indent=2),encoding="utf8")
    print(json.dumps({t:stats[t]["all"] for t in ("silver","audited") if t in stats}))
if __name__=="__main__":main()
