"""Hold selected page addresses constant; vary only serialization, then apply dual-cost monotone growth."""
import gzip,json,sys,itertools
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor
from context import D,rows,stream,atomic_line,cost,save,h,np
import grade
def run_shard(args):
    cohort,k=args;root=D if cohort=="discovery" else D/"replication"
    olds=iter(rows(root/f"pred_{k}.jsonl.gz"));total=0
    with gzip.open(root/f"serializer_pred_{k}.jsonl.gz","wt",encoding="utf8",compresslevel=3) as f:
        for obj in rows(root/f"source_{k}.jsonl.gz"):
            for t,rr,idx,meta,hist,last in stream(obj):
                i,step,ans=next(olds);assert (i,step)==(obj["instance"],t);total+=1
                raw=sorted(tuple(u) for u in ans["512"]["r2f"][0])
                mem={(rr[j][0],rr[j][1]+z):s for j in idx for z,s in enumerate(rr[j][4].split("\n"))}
                def enc(us,style):
                    blocks=[];seen=set()
                    for p,l,r in sorted(us):
                        body="\n".join(mem[p,z] for z in range(l,r+1))
                        if style=="shared":
                            if p not in seen:blocks.append(p);seen.add(p)
                            blocks.append(f"[{l},{r}]\n"+body)
                        else:blocks.append(body)
                    return sum(cost(s) for s in blocks)+max(0,len(blocks)-1),cost("\n".join(blocks))
                def compact(us):
                    out=[]
                    for p,l,r in sorted(us):
                        if out and out[-1][0]==p and l<=out[-1][2]+1:out[-1]=(p,out[-1][1],max(r,out[-1][2]))
                        else:out.append((p,l,r))
                    return out
                output={}
                for style in ("shared","body"):
                    c,w=enc(raw,style);out=compact(raw)
                    legal=lambda a:all(m<=q for m,q in zip(enc(a,style),(c,w)))
                    if not legal(out):out=raw
                    while True:
                        candidates=[]
                        for j,(p,l,r) in enumerate(out):
                            for right,z in [(0,r+1),(1,l-1)]:
                                if (p,z) not in mem or any(q==p and lo<=z<=hi for q,lo,hi in out):continue
                                d=min(max(lo-z,0,z-hi) for q,lo,hi in raw if q==p)
                                candidates.append(((d,right,j),j,(p,min(l,z),max(r,z))))
                        for _,j,triple in sorted(candidates):
                            possible=compact(out[:j]+[triple]+out[j+1:])
                            if legal(possible):out=possible;break
                        else:break
                    oc,ow=enc(out,style)
                    assert { (p,z) for p,l,r in raw for z in range(l,r+1)}<={ (p,z) for p,l,r in out for z in range(l,r+1)} and oc<=c and ow<=w
                    output[style]=[out,c,w,oc,ow]
                atomic_line(f,[i,t,raw,output])
    assert next(olds,None) is None
    return total
def main():
    cohort=sys.argv[1];root=D if cohort=="discovery" else D/"replication";result={}
    with ProcessPoolExecutor(4) as pool:cuts=list(pool.map(run_shard,[(cohort,j) for j in range(8)]))
    (root/"serializer_lock.json").write_text(json.dumps({p.name:h(p) for p in [D/"SERIALIZER_PROTOCOL.md",D/"serializers.py",*sorted(root.glob("serializer_pred_*.gz"))]},indent=1))
    # Read the hidden gold for the evaluation only after all choices are written and locked.
    from context import line_target,future
    out=[];seq=iter([])
    for k in range(8):
        predicted=iter(rows(root/f"serializer_pred_{k}.jsonl.gz"))
        for obj in rows(root/f"source_{k}.jsonl.gz"):
            for t,rr,idx,meta,hist,last in stream(obj):
                i,tt,base,chosen=next(predicted);assert (obj["instance"],t)==(i,tt)
                q=future(obj["events"],t)
                if not q or not q[2]:continue
                g=line_target(rr,q[0],q[1]);length=q[1].count("\n")+1
                def counts(sel,wire):
                    covered=0 if not g else sum(max(0,min(g[2],r)-max(g[1],l)+1) for p,l,r in sel if p==g[0])
                    actual=sum(r-l+1 for p,l,r in sel);return [int(covered==length),covered/length,int(bool(g) and any(p==g[0] and l<=g[1]<=r for p,l,r in sel)),covered/max(actual,1),wire,len(sel),actual,covered]
                scores={}
                for style,(sel,cc,w,oc,ow) in chosen.items():
                    scores["old_"+style]=counts(base,w);scores[style]=counts(sel,ow)
                out.append([i,t,512,length,bool(g),False,None,scores])
    with gzip.open(root/"serializer_scores.jsonl.gz","wt",encoding="utf8",compresslevel=3) as f:
        for r in out:atomic_line(f,r)
    for style in ["shared","body"]:
        temp=[[*r[:-1],{"r2f":r[-1]["old_"+style],"typed":r[-1][style]}] for r in out]
        grade.A=("r2f","typed");result[style]=grade.metrics(temp)
    (root/"serializer_results.json").write_text(json.dumps(dict(cuts=sum(cuts),results=result),indent=1))
if __name__=="__main__":main()
