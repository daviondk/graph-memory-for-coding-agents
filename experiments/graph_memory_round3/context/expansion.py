"""Monotone growth of observed, version-coherent memory ranges under a dual tokenizer cap."""
import gzip,json,sys,time,itertools,math
from functools import lru_cache
from collections import Counter,defaultdict
from concurrent.futures import ProcessPoolExecutor
import grade
from context import D,rows,stream,read,save,h,np,atomic_line,line_target,future,cost
ARMS=("r2f","typed","coalesce","old_balanced","old_forward","recent_balanced","typed_balanced","iso_balanced","iso_forward")
def select(source,mem,initial,kind,charged,wiremax):
    line_text=mem
    @lru_cache(None)
    def text(block):
        p,l,r=block
        return f"@@ {p} {l}..{r} @@\n"+"\n".join(line_text[p,z] for z in range(l,r+1))
    def price(us):
        ts=[text(b) for b in us]
        return sum(cost(s) for s in ts)+max(0,len(ts)-1),cost("\n".join(ts))
    def compact(us):
        out=[]
        for p,l,r in sorted(us):
            if out and out[-1][0]==p and l<=out[-1][2]+1:out[-1]=(p,out[-1][1],max(r,out[-1][2]))
            else:out.append((p,l,r))
        return tuple(out)
    def ok(us):
        a,b=price(us)
        return a<=charged and b<=wiremax
    src=tuple(tuple(u) for u in source);base=compact(src)
    if not ok(base):base=src
    if kind=="coalesce":
        a,b=price(base);return [base,a,b]
    if not base and initial and ok((initial,)):base=(initial,)
    if not base:return [[],0,0]
    axes=compact(base);old=set((p,z) for p,l,r in src for z in range(l,r+1))
    while True:
        c=[]
        for j,(p,l,r) in enumerate(base):
            for dr,z in ((0,r+1),(1,l-1)):
                if (p,z) not in mem:continue
                if any(q==p and lo<=z<=hi for q,lo,hi in base):continue
                closest=min((max(a-z,0,z-b) for q,a,b in axes if q==p),default=10**8)
                priority=(closest,dr,j) if kind=="balanced" else (dr,closest,j)
                c.append((priority,j,p,min(l,z),max(r,z)))
        found=False
        for _,j,p,lo,hi in sorted(c):
            choice=compact(base[:j]+((p,lo,hi),)+base[j+1:])
            if ok(choice):base=choice;found=True;break
        if not found:break
    assert old<=set((p,z) for p,l,r in base for z in range(l,r+1))
    a,b=price(base)
    return [base,a,b]
def evaluate_one(arg):
    cohort,k=arg;root=D if cohort=="discovery" else D/"replication"
    orig=iter(rows(root/f"pred_{k}.jsonl.gz"));n=0
    with gzip.open(root/f"expand_pred_{k}.jsonl.gz","wt",encoding="utf8",compresslevel=3) as fp:
        for obj in rows(root/f"source_{k}.jsonl.gz"):
            for t,rr,idx,meta,hist,last in stream(obj):
                n+=1;i,tt,all_=next(orig);assert (obj["instance"],t)==(i,tt)
                m={(rr[j][0],rr[j][1]+z):line for j in idx for z,line in enumerate(rr[j][4].split("\n"))}
                seed=(rr[idx[0]][0],rr[idx[0]][1],rr[idx[0]][1]) if idx else ()
                out={}
                for B in (256,512):
                    q=all_[str(B)]
                    out[B]={"r2f":q["r2f"],"typed":q["typed"]}
                    for name,arm,kind,tight in [
                       ("coalesce","r2f","coalesce",True),("old_balanced","r2f","balanced",False),
                       ("old_forward","r2f","forward",False),("recent_balanced","recent","balanced",False),
                       ("typed_balanced","typed","balanced",False),("iso_balanced","r2f","balanced",True),("iso_forward","r2f","forward",True)]:
                        source,mt,joint=q[arm]
                        out[B][name]=select(source,m,seed,kind,mt if tight else B,joint if tight else B)
                atomic_line(fp,[i,t,out])
    assert next(orig,None) is None
    return n
def score_one(args):
    cohort,k=args;root=D if cohort=="discovery" else D/"replication"
    import inspect
    source=inspect.getsource(grade.case).replace('D/f"pred_{k}.jsonl.gz"','D/f"expand_pred_{k}.jsonl.gz"')
    ns={**grade.__dict__,"D":root};exec(compile(source,"expand_scorer","exec"),ns)
    return ns["case"](k)
def main():
    phase,cohort=sys.argv[1:3];root=D if cohort=="discovery" else D/"replication"
    def emit(n,x):(root/n).write_text(json.dumps(x,indent=1))
    if phase=="predict":
        files=[D/"EXPANSION_PROTOCOL.md",D/"EXPANSION_AMENDMENT.md",D/"expansion.py",root/"prediction_lock.json",*sorted(root.glob("pred_*.gz"))]
        emit("expansion_method_lock.json",{str(p):h(p) for p in files})
        with ProcessPoolExecutor(5) as pool:n=list(pool.map(evaluate_one,[(cohort,j) for j in range(8)]))
        emit("expansion_lock.json",{"cuts":sum(n),"files":{p.name:h(p) for p in [root/"expansion_method_lock.json",*sorted(root.glob("expand_pred_*.gz"))]}})
    if phase=="grade":
        assert all(h(root/n)==s for n,s in json.loads((root/"expansion_lock.json").read_bytes())["files"].items())
        with ProcessPoolExecutor(5) as pool:data=list(pool.map(score_one,[(cohort,j) for j in range(8)]))
        rr=[r for rows_,_,_ in data for r in rows_]
        with gzip.open(root/"expansion_scores.jsonl.gz","wt",encoding="utf8",compresslevel=3) as f:
            for r in rr:atomic_line(f,r)
        grade.A=ARMS
        result={"token_checks":sum(x[2] for x in data),"roots_seen":sum(x[1] for x in data),"budget":{}}
        for B in (256,512):
            bb=[r for r in rr if r[2]==B];ss=grade.metrics(bb);ss["comparisons"]={}
            for new,base in [("old_balanced","r2f"),("iso_balanced","r2f"),("iso_forward","r2f"),("old_balanced","typed"),("typed_balanced","old_balanced"),("old_forward","old_balanced")]:
                temp=[[*r[:-1],dict(r[-1],typed=r[-1][new],r2f=r[-1][base])] for r in bb]
                ss["comparisons"][new+"_minus_"+base]=grade.metrics(temp)["typed_minus"]["r2f"]
            result["budget"][B]=ss
            assert ss["arms"]["coalesce"]["hits"]==ss["arms"]["r2f"]["hits"] and ss["comparisons"]["old_balanced_minus_r2f"]["losses"][0]==0
        emit("expansion_results.json",result)
if __name__=="__main__":main()
