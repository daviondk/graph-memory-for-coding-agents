"""Rebuild hidden target coordinates, rendered token prices and per-action metrics independently of the choice policy."""
import gzip,json,hashlib,itertools,time
from collections import Counter,defaultdict
from concurrent.futures import ProcessPoolExecutor
from context import D,F,e,stream,rows,read,save,h,np,cost,atomic_line,line_target,future
from policy import unique_span
from tokenizers import Tokenizer
from functools import lru_cache
A=("recent","r2f","fixed","flat","start","typed")
BUDGETS=(256,512)
def case(k):
    tokenizer=Tokenizer.from_file(str(e.PACK/"qwen_tokenizer.json"))
    @lru_cache(80000)
    def count(s):return len(tokenizer.encode(s,add_special_tokens=False).ids)
    keylines=iter(rows(D/f"pred_{k}.jsonl.gz"));out=[];checks=0;cuts=0
    for obj in rows(D/f"source_{k}.jsonl.gz"):
        for t,rr,idx,meta,hist,last in stream(obj):
            i,st,ans=next(keylines);assert (i,st)==(obj["instance"],t);cuts+=1
            m={}
            for j in idx:
                p,lo,hi,_,body=rr[j]
                for q,s in enumerate(body.split("\n"),lo):
                    assert (p,q) not in m;m[p,q]=s
            def render(p,lo,hi):
                assert hi>=lo
                return f"@@ {p} {lo}..{hi} @@\n"+"\n".join(m[p,z] for z in range(lo,hi+1))
            for B in BUDGETS:
                for a,(sel,both,wire) in ans[str(B)].items():
                    txt=[render(*u) for u in sel];assert len(sel)<=3 and sum(count(s) for s in txt)+max(len(txt)-1,0)==both<=B and count("\n".join(txt))==wire<=B
                    total=sum(hi-lo+1 for p,lo,hi in sel)
                    assert total==len({(p,z) for p,lo,hi in sel for z in range(lo,hi+1)})
                    checks+=1
            q=future(obj["events"],t)
            if not q or not q[2]:continue
            x=line_target(rr,q[0],q[1]);sp=unique_span(rr,q[0],q[1])
            assert (sp is not None)==(x is not None)
            if x:assert x[3]==sp[0] and rr[sp[-1]][1]<=x[2]<=rr[sp[-1]][2]
            length=q[1].count("\n")+1
            p,lo,hi=(x[:3] if x else ("",-1,-1))
            if x:assert length==hi-lo+1
            reach=bool(x) and all((p,z) in m for z in range(lo,hi+1))
            oprice=count(render(p,lo,hi)) if reach else None
            for B in BUDGETS:
                scores={}
                for a,(sel,both,wire) in ans[str(B)].items():
                    overlap=sum(max(0,min(r,hi)-max(l,lo)+1) for path,l,r in sel if path==p)
                    chosen=sum(r-l+1 for path,l,r in sel)
                    start=int(any(path==p and l<=lo<=r for path,l,r in sel))
                    fraction=overlap/length;precision=overlap/max(chosen,1)
                    scores[a]=[int(overlap==length),fraction,start,precision,wire,len(sel),chosen,overlap]
                out.append([i,t,B,length,bool(x),reach,oprice,scores])
    assert next(keylines,None) is None
    return out,cuts,checks
def metrics(rs):
    projects=sorted({r[0].split(".")[0] for r in rs});index={q:i for i,q in enumerate(projects)}
    rep=np.array([index[r[0].split(".")[0]] for r in rs]);num=np.bincount(rep)
    boot=np.random.default_rng(183100).integers(len(projects),size=(10000,len(projects)));N=len(rs)
    vals={a:np.array([r[-1][a] for r in rs]) for a in A};effects={}
    for a in A:
        diff=vals['typed'][:,:4]-vals[a][:,:4]
        cl=np.array([diff[rep==j].sum(axis=0) for j in range(len(projects))])
        bs=cl[boot].sum(axis=1)/num[boot].sum(1)[:,None];macro=(cl/num[:,None])
        effects[a]=dict(delta=diff.mean(axis=0).tolist(),ci=np.quantile(bs,[.025,.975],axis=0).tolist(),wins=(diff>0).sum(axis=0).tolist(),losses=(diff<0).sum(axis=0).tolist(),macro=macro.mean(axis=0).tolist(),macro_ci=np.quantile(macro[boot].mean(axis=1),[.025,.975],axis=0).tolist(),
          per_project={q:[int(num[j]),int(cl[j,0]),float(cl[j,1])] for j,q in enumerate(projects)})
    return dict(n=N,projects=len(projects),instances=len({r[0] for r in rs}),reachable=sum(r[5] for r in rs),unique=sum(r[4] for r in rs),exact_target_within_budget=sum(r[6] is not None and r[6]<=r[2] for r in rs),
         arms={a:dict(hits=int(x[:,0].sum()),line_recall=float(x[:,1].mean()),starts=int(x[:,2].sum()),line_precision=float(x[:,3].mean()),mean_tokens=float(x[:,4].mean()),mean_blocks=float(x[:,5].mean()),complete_per_1000_tokens=float(1000*x[:,0].sum()/max(1,x[:,4].sum()))) for a,x in vals.items()},typed_minus=effects)
def main():
    lock=read("prediction_lock.json");assert all(h(D/n)==v for n,v in lock["files"].items())
    assert all(h(n)==v for n,v in read("method_lock.json")["files"].items())
    with ProcessPoolExecutor(5) as pool:result=list(pool.map(case,range(8)))
    rr=[r for records,n,c in result for r in records];summ={"prediction_cuts":sum(n for records,n,c in result),"token_price_checks":sum(c for records,n,c in result),"metrics_order":["exact_full","line_fraction","hit_start","line_precision"],"budget":{}}
    with gzip.open(D/"action_scores.jsonl.gz","wt",encoding="utf8",compresslevel=3) as f:
        for row in rr:atomic_line(f,row)
    for B in BUDGETS:
        sub=[r for r in rr if r[2]==B]
        z=metrics(sub);z["length_strata"]={}
        for name,condition in [("1-12",lambda x:x[3]<=12),("13-24",lambda x:13<=x[3]<=24),("25+",lambda x:x[3]>=25),("unlocated",lambda x:not x[4])]:
            s=[r for r in sub if condition(r)];z["length_strata"][name]=metrics(s) if s else {}
        summ["budget"][B]=z;print(B,z["n"],z["projects"],[(a,r["hits"],round(r["line_recall"],3)) for a,r in z["arms"].items()],flush=True)
    save("results.json",summ)
if __name__=="__main__":main()
