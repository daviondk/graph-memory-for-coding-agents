from collections import Counter,defaultdict
from statistics import median
import numpy as np
from local import D,read,save,sha

METHODS=("file","ast","content","range","edges","local")
PAIRS=(("local","range"),("local","content"),("local","edges"),("edges","range"),("local","ast"))


def measure(ids,rows,pred):
    grouped=defaultdict(list);repos=defaultdict(list)
    totals={m:Counter() for m in METHODS};ops=Counter();times=Counter()
    latency={k:[] for k in ("align","map","dp","action_bytes","full_bytes")}
    for key in ids:
        r,p=rows[key],pred[key];grouped[r["issue"]].append(key);repos[r["repo"]].append(key)
        for m in METHODS:totals[m].update(r["metrics"][m])
        s,q=p["stats"],p["resource"]
        ops.update(dict(bounded=int(s["bounded"]),has_edges=int(bool(s["left"]+s["right"])),
                        has_interior=int(bool(s["central"])),old_target=int(p["target_selected"]),
                        added_units_interior=len(p["positions"]["local"])-len(p["positions"]["edges"]),
                        added_to_fully_retained=int(r["metrics"]["local"]["strict"]>r["metrics"]["edges"]["strict"])))
        times.update(dict(align=q["align_s"],map_local=q["map_s"]["local"],dp_local=q["dp_s"]["local"],
                     action_bytes=q["bytes"],whole_file_bytes=q["full_source_bytes"]))
        for col,v in (("align",q["align_s"]),("map",q["map_s"]["local"]),("dp",q["dp_s"]["local"]),
                      ("action_bytes",q["bytes"]),("full_bytes",q["full_source_bytes"])):
            latency[col].append(v)
    groups=[(k,grouped[k]) for k in sorted(grouped)]
    counts=np.array([len(rec) for k,rec in groups])
    rng=np.random.default_rng(4241071);W=np.stack([np.bincount(x,minlength=len(groups)) for x in
                            rng.integers(len(groups),size=(10000,len(groups)))])
    stats={}
    for m,b in PAIRS:
        d={k:rows[k]["metrics"][m]["strict"]-rows[k]["metrics"][b]["strict"] for k in ids}
        a=np.array([sum(d[k] for k in rec) for _,rec in groups]);macro=a/counts
        stats[m+"_minus_"+b]=dict(delta=sum(d.values())/len(d),macro=float(macro.mean()),
                 ci=np.quantile(W@a/(W@counts),[.025,.975]).tolist(),
                 macro_ci=np.quantile(W@macro/len(groups),[.025,.975]).tolist(),
                 wins=sum(x>0 for x in d.values()),losses=sum(x<0 for x in d.values()),
                 by_repo={repo:dict(events=len(items),net=sum(d[k] for k in items)) for repo,items in repos.items()})
    return dict(events=len(ids),issues=len(groups),repos=len(repos),methods=totals,paired=stats,operations=ops,
                resources=times,median={s:median(v) for s,v in latency.items()})


def main():
    rows=read(D/"audit.json.gz");p=read(D/"predictions.json.gz");assert set(p)==set(rows)
    assert sha(D/"audit.json.gz")==read(D/"audit-seal.json")["audit"]
    reports={}
    for name,check in (("held1071",lambda r:r["held"]),("all2696",lambda r:True),
                       ("main676",lambda r:r["group"]=="main"),("held_target",lambda r:r["held"] and r["old_target"])):
        ids=[k for k in rows if check(rows[k])];reports[name]=measure(ids,rows,p)
    save("results.json",dict(panels=reports,primary="held1071/local_minus_range/strict/issue_macro",
        secondary="held1071/local_minus_content/strict/issue_macro following primary",
        bootstrap=dict(unit="issue",replicates=10000,seed=4241071),audit=sha(D/"audit-seal.json"),
        exhaustive=sha(D/"exhaustive.json")))
    for n,tab in reports.items():
        print(n,{k:v["strict"] for k,v in tab["methods"].items()})
if __name__=="__main__":main()

