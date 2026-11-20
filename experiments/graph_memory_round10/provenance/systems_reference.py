"""Retrospective R9 exact-graph and external testmon reference, from selection masks only, unbounded model storage."""
from common import *
from score import stats
from statistics import median

def main():
    idx={r["key"]:{o["node"]:o["historical"] for o in r["answers"]} for r in get(ROOT/"history.gz")}
    target={r["key"]:{o["node"]:o["status"] for o in r["receipts"]} for r in get(ROOT/"current.gz")}
    rows=[]; source={};bytesizes={}
    for r in get(ROOT/"inputs.gz"):
        k=r["key"];past=idx[k];nodes=[o["node"] for o in r["items"]];direction=r["direction"];panel=r["panel"]
        side="gold" if direction=="fix" else "base";old="base" if direction=="fix" else "gold"
        folder=PANELS[panel]/"runs"/r["task"]
        p=folder/("testmon-"+side+"_select.json")
        selected=set(get(p)["reports"]);assert selected<=set(nodes)
        source[p.relative_to(WORK).as_posix()]=fh(p)
        b=folder/("testmon-"+old+"_build.json")
        bytesizes[k]=sum(get(b)["db_bytes"].values());source[b.relative_to(WORK).as_posix()]=fh(b)
        for pol,mask in (("exact_graph",r["expected_impact"]),("testmon_mask",[n in selected for n in nodes])):
            order=sorted(range(len(nodes)),key=lambda i:(not mask[i],past[nodes[i]]!="failed",sha(packed([r["task"],direction,nodes[i],"r10-priority"]))))
            paid=set(order[:len(nodes)//3])
            for i,n in enumerate(nodes):
                src="confirm" if i in paid else ("abstain" if mask[i] else "historical_prediction")
                gold=target[k][n]
                answer=gold if src=="confirm" else past[n] if src=="historical_prediction" else None
                rows.append(dict(key=k,panel=panel,task=r["task"],policy=pol,node=n,source=src,truth=gold,answer=answer,correct=answer==gold))
    put(ROOT/"systems-reference-outcomes.gz",rows)
    groups={panel:{pol:stats([r for r in rows if r["policy"]==pol and (panel=="both" or r["panel"]==panel)]) for pol in ("testmon_mask","exact_graph")}
            for panel in ("both","primary","holdout")}
    put(ROOT/"systems-reference.json",dict(groups=groups,source_files=source,db_bytes=bytesizes,median_build_db=median(bytesizes.values())))
    print(json.dumps(groups["both"]));print(median(bytesizes.values()))

if __name__=="__main__":main()
