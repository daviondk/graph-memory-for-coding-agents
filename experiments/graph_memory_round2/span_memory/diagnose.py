"""Exploratory mechanism checks. Extract only paths and line bounds, never program contents."""
import json
from collections import Counter,defaultdict
from run import D,e,stream,rows,save
def main():
    counts=defaultdict(Counter);groups=defaultdict(list)
    for i,t,span,oracle,hit,cost in rows(D/"scored.jsonl.gz"):
        w=str(len(span)) if len(span)<=3 else "4+"
        group=counts[w];group["n"]+=1;group["feasible"]+=oracle
        for a,v in hit.items():group[a]+=v
        diff=hit["typed"]-hit["global"]
        if diff:groups[diff].append((i,t,span))
    examples={}
    for direction,ls in groups.items():
        i,t,span=min(ls,key=lambda r:e.sha("illustration|"+str(r[:2])))
        for k in range(8):
            p=next((r for r in rows(D/f"pred_{k}.jsonl.gz") if r[0]==i and r[1]==t),None)
            if p is None:continue
            obj=next(o for o in rows(D/f"fresh_{k}.jsonl.gz") if o["instance"]==i)
            _,rr,*_=next(s for s in stream(obj) if s[0]==t)
            def coords(sel):return [(rr[j][0],rr[j][1],rr[j][2]) for j in sel]
            examples[str(direction)]={"instance":i,"cut":t,"selected":{a:coords(p[2][a]) for a in ["global","typed"]},"actual_interval":coords(span)}
            break
    save("mechanism_descriptive.json",dict(by_width={k:dict(v) for k,v in counts.items()},examples=examples))
if __name__=="__main__":main()
