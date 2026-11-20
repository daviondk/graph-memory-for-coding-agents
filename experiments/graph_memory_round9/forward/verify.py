"""Verify Git projections on actual unchanged source lines; sensitivity for multi-target annotations."""
from collections import defaultdict,Counter
from common import *
from predict import mapped
from score import ARMS,summarize,contrasts

def main():
    check(read("score-lock.json"));check(read("prediction-lock.json"));check(read("selection.json")["files"])
    records=read("sources.json.gz")
    files=unchanged=0
    for src in records.values():
        for f in src["files"].values():
            def get(side):
                if not f[side]:return []
                b=f[side+"_blob"]
                if "error" in b:return None
                raw=(CACHE/b["cache"]).read_bytes()
                assert sha(raw)==b["sha256"]
                return raw.split(b"\n")
            old,new=get("old"),get("new")
            if old is None or new is None or not f["old"] or not f["new"]:continue
            # split terminator is not a source line.
            if old and not old[-1]:old.pop()
            if new and not new[-1]:new.pop()
            files+=1
            hs=f["hunks"]
            for i,line in enumerate(old,1):
                if any(a<=i<a+n for a,n,_,_ in hs):continue
                j=mapped(i,hs)
                assert 0<j<=len(new) and line==new[j-1],(src["commit"],f["old"],i,j)
                unchanged+=1
    pred={x["case"]:x for x in read("predictions.json.gz")}
    groups=defaultdict(list)
    for x in read("outcomes.json"):
        k=x["project"],x["commit"],pack(pred[x["case"]]["origin"])
        groups[k].append(x)
    unique=[];conflicts=[]
    for key,rs in groups.items():
        if len({r["inline"] for r in rs})!=1:
            conflicts.append([r["case"] for r in rs]);continue
        rec=dict(rs[0]);rec["gold_count"]=int(any(x["gold_count"]==1 for x in rs))
        for field in ("address_hit","joint_hit"):
            rec[field]={k:any(r[field][k] for r in rs) for k in ARMS}
        assert all(r["predicted"]==rec["predicted"] for r in rs)
        unique.append(rec)
    out=dict(paired_java_files=files,mapped_unchanged_lines=unchanged,commits=len(records),unique=summarize(unique),
             duplicate_group_sizes=dict(Counter(len(rs) for rs in groups.values())),conflicts=conflicts,
             unique_edge_minus_lex=contrasts(unique,"lex_prior","edge"),verifier=sha((ROOT/"verify.py").read_bytes()))
    save("verification.json",out)
    print(files,unchanged, len(unique),out["unique"]["arms"]["edge"],out["unique"]["arms"]["lex_prior"])
if __name__=="__main__":main()
