"""Score the frozen cohort + blinded cards + controlled records; all primary denominators retained."""
import gzip,json,hashlib,statistics,collections
from pathlib import Path
import numpy as np
from receipt_policy import policies,terminal
D=Path(__file__).resolve().parent
def get(name):
    b=(D/name).read_bytes();return json.loads(gzip.decompress(b) if name.endswith(".gz") else b)
def put(name,x):
    b=json.dumps(x,sort_keys=True,ensure_ascii=False,indent=None if name.endswith(".gz") else 2).encode()
    (D/name).write_bytes(gzip.compress(b,mtime=0) if name.endswith(".gz") else b)
def checked(d):
    for n,h in d.items():assert hashlib.sha256((D/n).read_bytes()).hexdigest()==h,n
def cm(rows, truth_key,methods):
    out={}
    for m in methods:
        t=collections.Counter((r[truth_key],r["policies"][m]) for r in rows)
        pred=lambda s:sum(v for (y,h),v in t.items() if h==s)
        out[m]={"n":len(rows),"issued_pass":pred("pass"),"issued_fail":pred("fail"),"abstain":pred("abstain"),
                "known_true_pass":t["pass","pass"],"known_false_pass":t["fail","pass"],"pass_without_positive_test":t["skip_or_empty","pass"],
                "pass_without_evidence":t["no_evidence","pass"],"known_true_fail":t["fail","fail"],"known_false_fail":t["pass","fail"],
                "fail_without_evidence":t["no_evidence","fail"]+t["skip_or_empty","fail"],
                "matrix":{k:dict((h,n) for (z,h),n in t.items() if z==k) for k in sorted(set(y for y,h in t))}}
    return out
def group(rows):
    def keys(r):
        z=r["rc"]==0;y=r["visible_state"];return [1,int(z),int(z and y=="fail"),int(z and y in ("fail","pass")),int(z and y=="no_evidence"),int(z and y=="skip_or_empty"),int(y in ("fail","pass"))]
    clusters=collections.defaultdict(lambda:np.zeros(7,dtype=int))
    for r in rows:clusters[(r["repo"],r["iid"])]+=keys(r)
    if not clusters:return {"n":0}
    vec=np.stack(list(clusters.values()));s=vec.sum(axis=0);rng=np.random.default_rng(1536)
    ratios=[];known=[]
    for j in range(50):
        b=vec[rng.integers(0,len(vec),(100,len(vec)))].sum(axis=1)
        for l,id_ in ((ratios,1),(known,3)):
            ok=b[:,id_]>0;l.extend((b[ok,2]/b[ok,id_]).tolist())
    def rate(n,d,boots):return [None,None,None] if not d or not boots else [float(n/d),*map(float,np.quantile(boots,[.025,.975]))]
    out=dict(zip(("n","zero","zero_visible_fail","zero_known","zero_no_evidence","zero_no_tests","known"),map(int,s)))
    out.update(issues=len(vec),repos=len(set(r["repo"] for r in rows)),zero_contradiction_rate=rate(s[2],s[1],ratios),zero_known_contradiction_rate=rate(s[2],s[3],known),
           policies=cm(rows,"visible_state",("exit_only","summary","summary_rc","strict")))
    return out

def main():
    checked(get("input-lock.json"));raw=get("calls.gz");forecasts=[];proof=[]
    rows={}
    for r in raw:
        vis,line=terminal(r["visible"]); rs,_=terminal(r["raw"]);k=r["kind"]
        row={a:r[a] for a in ("id","repo","iid","panel","step","rc")}
        row.update(visible_state=vis,raw_state=rs,summary=line[-600:],kind=k["shape"],policies=policies(r["rc"],vis,k["direct"],k["pipefail"]))
        forecasts.append(row);rows[r["id"]]=row
        if vis=="fail" and r["rc"]==0:
            proof.append({**row,"command":r["cmd"],"visible_tail":r["visible"].splitlines()[-4:]})
    put("predictions.gz",forecasts);put("visible-conflicts.gz",proof)
    groups={"all":group(forecasts)}
    for field in ("panel","kind"):
        for k in sorted(set(r[field] for r in forecasts)):groups[k]=group([r for r in forecasts if r[field]==k])
    for panel in ("science","other"):
        for kind in ("direct","pipeline","compound","pipefail"):
            groups[panel+"_"+kind]=group([r for r in forecasts if r["panel"]==panel and r["kind"]==kind])
    observers=get("audit-labels.json")["labels"];key=get("audit-key.json")
    audit=[dict(rows[m["id"]],observed=observers[c],card=c,stratum=m["stratum"]) for c,m in key.items()]
    aud={s:cm([r for r in audit if r["stratum"]==s],"observed",("exit_only","summary","summary_rc","strict")) for s in ("uniform","pipe")}
    control=get("controlled.gz")
    cc={"grid":cm(control[:40],"fixture_truth",control[0]["policies"].keys()),"shapes":{k:cm([r for r in control[:40] if r["shape"]==k],"fixture_truth",control[0]["policies"].keys()) for k in sorted(set(r["shape"] for r in control[:40]))},
        "placebo":[dict(shape=r["shape"],truth=r["fixture_truth"],policies=r["policies"]) for r in control[40:]],
        "size_median":{key:statistics.median(r["sizes"][key] for r in control[:40]) for key in control[0]["sizes"]}}
    extras={"raw_visible_matrix":{"|".join(k):v for k,v in collections.Counter((r["visible_state"],r["raw_state"]) for r in forecasts).items()},
            "conflicting_issues":len(set((r["repo"],r["iid"]) for r in proof)),"conflicting_repos":sorted(set(r["repo"] for r in proof)),
            "sizes_median":{"shell_rc":statistics.median(len(str(r["rc"])) for r in raw),
            "visible_stdout":statistics.median(len(r["visible"].encode()) for r in raw),
            "positive_summary_line":statistics.median(len(terminal(r["visible"])[1].encode()) for r in raw if rows[r["id"]]["visible_state"]=="pass")}}
    put("audit-scored.json",audit);put("results.json",dict(group=groups,audit=aud,controlled=cc,extras=extras))
    print(json.dumps({k:{kk:v for kk,v in val.items() if kk!="policies"} for k,val in groups.items()},indent=2))
if __name__=="__main__":main()
