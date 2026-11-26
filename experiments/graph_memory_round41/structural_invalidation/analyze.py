from collections import Counter,defaultdict
import numpy as np

from shared import D,sha,read,save
from audit import METHODS

PAIRS=(("range","ast"),("range","content"),("content","ast"),("ast","file"))


def summarize(keys,per,pred):
    totals={a:Counter() for a in METHODS};by_issue=defaultdict(list)
    for k in keys:
        r=per[k];by_issue[r["issue"]].append(k)
        for a in METHODS:totals[a].update(r["metrics"][a])
    order=sorted(by_issue);n=np.array([len(by_issue[i]) for i in order])
    rr={};rng=np.random.default_rng(415501)
    W=np.stack([np.bincount(d,minlength=len(order)) for d in rng.integers(len(order),size=(10000,len(order)))])
    for a,b in PAIRS:
        dv={k:per[k]["metrics"][a]["strict"]-per[k]["metrics"][b]["strict"] for k in keys}
        raw=np.array([sum(dv[k] for k in by_issue[i]) for i in order])
        d=raw/n
        rr[a+"_minus_"+b]=dict(delta=float(raw.sum()/n.sum()),macro=float(d.mean()),
            ci=np.quantile((W@raw)/(W@n),[.025,.975]).tolist(),
            macro_ci=np.quantile((W@d)/len(d),[.025,.975]).tolist(),
            wins=sum(v>0 for v in dv.values()),losses=sum(v<0 for v in dv.values()))
    flags=Counter();struct=Counter();full=Counter();times=Counter();times2=Counter();roots={}
    for k in keys:
        p=pred[k];f=p["flags"];c=p["cost"]
        flags.update(dict(has_pre_post=f["has_source"],python=f["python"],parsed=f["parsed"],
                          edited_blocks=f["edited_blocks"],owner_blocks=f["owner_blocks"],
                          parse_failure=f["python"] and not f["parsed"],empty_old=not p["old"],
                          old_target=per[k]["old_target"]))
        struct.update(p["ast_reasons"].values());full.update(p["content_reasons"].values())
        for x in ("bytes","ast_cold_s","ast_lookup_s","range_lookup_s","content_s","full_hash_s"):times[x]+=c[x]
        times2.update(c["solver_s"])
        roots[c["old"]]=c["old_bytes"];roots[c["new"]]=c["new_bytes"]
    return dict(events=len(keys),issues=len(order),methods=totals,paired=rr,access=flags,
                ast_rejected=struct,content_rejected=full,resources=times,
                solver_seconds=times2,distinct_versions=len(roots),distinct_version_bytes=sum(roots.values()))


def main():
    p=read(D/"predictions.json.gz");a=read(D/"audit.json.gz");s=read(D/"audit-seal.json")
    assert sha(D/"audit.json.gz")==s["sha"] and set(a)==set(p)
    panels={}
    for name,ok in (("held1071",lambda x:x["held"]),("all2696",lambda x:True),
                 ("main676",lambda x:x["group"]=="main"),("held_parsed",lambda x:x["held"] and x["parsed"]),
                 ("held_target",lambda x:x["held"] and x["old_target"]),
                 ("held_nonempty",lambda x:x["held"] and not x["old_empty"])):
        subset=[k for k,v in a.items() if ok(v)]
        if subset:panels[name]=summarize(subset,a,p)
    save("results.json",dict(panels=panels,native_component=read(D/"forecast-seal.json")["external_rules"],
        primary="held1071/range_minus_ast/strict",audit=sha(D/"audit-seal.json"),
        bootstrap={"unit":"issue","replicates":10000,"seed":415501}))
    for name,z in panels.items():
        print(name,z["events"],{k:[r["whole_same"],r["strict"],r.get("bad_new",0)] for k,r in z["methods"].items()})


if __name__=="__main__":main()

