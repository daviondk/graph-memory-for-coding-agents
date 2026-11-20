"""Classify differing independent target texts and re-score with the discordant example excluded."""
from pathlib import Path
import sys
from run_anchor import A,B,HERE,rows,save,prior,future_check,success,rel,invert,line_target,paired
import hashlib
def main():
    outcomes={};examples=[]
    for panel,src in [("A",A),("B",B)]:
        dropped=set()
        for k in range(8):
            cs=iter(rows(HERE/panel/f"cuts_{k}.gz"))
            for task in rows(src/f"source_{k}.jsonl.gz"):
                iid=task["instance"];ev=task["events"]
                for t in range(4,len(ev),4):
                    ii,tt,m=next(cs);assert (iid,t)==(ii,tt)
                    args,obs=future_check(ev,t)
                    if not args or not success(args.get("command"),rel(args.get("path")),obs):continue
                    gold=invert(args,obs)
                    if not gold:continue
                    lo,tx=gold;p=rel(args["path"])
                    table={n:s for path,n,s in m["flat_original"] if p==path}
                    rr=prior.pages({p:{n:(s,0) for n,s in table.items()}})
                    old=line_target(rr,p,args["old_str"])
                    if not old:continue
                    if old[1]==lo and old[2]==lo+len(tx)-1 and all(table.get(lo+i)==s for i,s in enumerate(tx)):continue
                    dropped.add((iid,t))
                    differences=[]
                    for i,s in enumerate(tx):
                        prior_row=table.get(lo+i)
                        if prior_row!=s:
                            differences.append(dict(n=lo+i,old_len=len(prior_row) if prior_row is not None else None,new_len=len(s),
                              strip_same=prior_row is not None and prior_row.strip()==s.strip(),old=prior_row,reverse=s))
                    examples.append(dict(panel=panel,issue=iid,t=t,path=p,before_span=list(old[1:3]),after_span=[lo,lo+len(tx)-1],different=differences))
        raw=[r for r in rows(HERE/panel/"scored.jsonl.gz") if (r[0],r[2]) not in dropped]
        outcomes[panel]=dict(n=len(raw),cap=paired(raw,"cap_anchor","cap_original"),full=paired(raw,"flat_anchor","flat_original"))
    save(HERE/"independent_targets.json",dict(mismatches=examples,drop_discordant=outcomes));print([(r["issue"],r["t"],r["different"]) for r in examples])
if __name__=="__main__":main()
