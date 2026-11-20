"""Select segments from prefix-only memory. Methods share all selectable line intervals and the true tokenizer."""
import gzip,itertools,sys,time
from concurrent.futures import ProcessPoolExecutor
from functools import lru_cache
from context import D,F,e,rows,stream,prev,read,save,h,np,feats,lenkey,fitted_line_probs,wordset,cost,render,atomic_line
BUDGETS=(512,)
ARMS=("recent","r2f","fixed","flat","start","typed")
def at_cut(obj,t,rr,idx,meta,hist,last,model,origin):
    if not idx:return {B:{a:[[],0,0] for a in ARMS} for B in BUDGETS}
    w,flat,offset=origin
    p,W,L=prev.probs(rr,idx,meta,hist,last,t,obj,w,flat,offset)
    text=[render(rr[i]) for i in idx];prices=np.array([cost(s) for s in text]);comb,edges,tri=prev.calc_sets(len(idx),idx,rr,L)
    ks=(comb<len(idx)).sum(1);cs=np.r_[prices,0][comb].sum(1)+np.maximum(0,ks-1)
    val=prev.values(p[:,None]*W["typed"],comb,edges,tri)
    # Within each group, absolute line numbers form one uninterrupted run from observed candidate pages.
    ordered=sorted(range(len(idx)),key=lambda j:(rr[idx[j]][0],rr[idx[j]][1]));groups=[];start={}
    for j in ordered:
        r=rr[idx[j]];path,a,b,age,body=r
        if not groups or groups[-1]["path"]!=path or groups[-1]["origin"]+len(groups[-1]["lines"])!=a:
            groups.append({"path":path,"origin":a,"lines":[],"flat":[],"structured":[],"keys":[]})
        g=len(groups)-1;c=groups[g];j0=len(c["lines"]);start[j]=(g,j0,j0+b-a)
        letters=body.split("\n");c["lines"].extend(letters);ff=feats(r,wordset(obj["issue"][:9000]))
        q=fitted_line_probs(ff,model,"typed");c["flat"].extend([p[j]/len(ff)]*len(ff));c["structured"].extend(p[j]*q)
        for f in ff:
            parts=lenkey(f);key="|".join(parts)
            if key not in model["length_dist"]:key="|".join(parts[:2])
            if key not in model["length_dist"]:key=parts[0]
            if key not in model["length_dist"]:key="*"
            c["keys"].append(model["lookup"][key])
    for c in groups:
        c["flat"]=np.asarray(c["flat"]);c["structured"]=np.asarray(c["structured"]);c["keys"]=np.asarray(c["keys"])
    dists=model["cdfs"];global_cdf=dists[model["lookup"]["*"]]
    @lru_cache(None)
    def rendered(u):
        g,a,b=u;c=groups[g];return f"@@ {c['path']} {c['origin']+a}..{c['origin']+b} @@\n"+"\n".join(c["lines"][a:b+1])
    @lru_cache(None)
    def unit_cost(u):return cost(rendered(u))
    @lru_cache(None)
    def scores(u):
        g,a,b=u;c=groups[g];s=slice(a,b+1);ix=np.minimum(np.arange(b-a+1,0,-1),95)
        glob=global_cdf[ix];cond=dists[c["keys"][s],ix]
        w=c["structured"][s]
        return np.array([c["flat"][s]@glob,w@glob,w@cond])
    def collection_score(us):
        blocks=sorted(us);v=np.zeros(3);last=None
        for u in blocks:
            if last and u[0]==last[0] and u[1]<=last[2]+1:last=(u[0],last[1],max(last[2],u[2]))
            else:
                if last:v+=scores(last)
                last=u
        if last:v+=scores(last)
        return v
    def packet(js):return tuple(start[int(j)] for j in js)
    def dst(us):
        return [[groups[g]["path"],groups[g]["origin"]+a,groups[g]["origin"]+b] for g,a,b in us]
    def payload(us):
        return [dst(us),sum(unit_cost(u) for u in us)+max(0,len(us)-1),cost("\n".join(rendered(u) for u in us))]
    baselines={}
    for B in BUDGETS:
        old=packet(prev.choose(val,comb,cs<=B,text,B))
        recent=packet(prev.greedy(range(len(idx)),prices,B,text,1))
        baselines[B]=(old,recent)
    leaders=list(np.argsort(-p,kind="stable")[:5]);leaders+=list(range(min(2,len(idx))))
    mandatory=set(u for old,recent in baselines.values() for u in old)
    leaders=list(dict.fromkeys(leaders+[j for j in range(len(idx)) if start[j] in mandatory]))
    library=set()
    for j in leaders:
        g,a,b=start[j];c=groups[g];N=len(c["lines"]);peak=a+int(np.argmax(c["structured"][a:b+1]))
        for anchor in (a,(a+b)//2,peak):
            for delta in (0,-3,-8):
                lo=max(0,anchor+delta)
                for ln in (3,6,12,18,24,36,48,72):library.add((g,lo,min(N-1,lo+ln-1)))
    windows=sorted(library);wcost={u:unit_cost(u) for u in windows}
    answer={}
    for B in BUDGETS:
        old,recent=baselines[B]
        original=payload(old);charged_limit,wire_limit=original[1:]
        recent_selected=[]
        for j in range(len(idx)):
            u=start[j]
            trial=(*recent_selected,u)
            data=payload(trial)
            if data[1]<=charged_limit and data[2]<=wire_limit:recent_selected.append(u)
            if len(recent_selected)==3:break
        recent=tuple(recent_selected)
        best=[old,old,old];values=collection_score(old)
        def visit(us,v):
            nonlocal values
            improved=np.flatnonzero(v>values+1e-12)
            if len(improved) and cost("\n".join(rendered(u) for u in us))<=wire_limit:
                for j in improved:best[j]=us;values[j]=v[j]
        visit(recent,collection_score(recent))
        residues=[()] + [s for n in (1,2) for s in itertools.combinations(old,n)]
        bases=[(z,sum(unit_cost(x) for x in z)+len(z),collection_score(z)) for z in residues]
        for u in windows:
            g,lo,hi=u;c=wcost[u]
            if c>charged_limit:continue
            v0=scores(u)
            for z,zprice,zv in bases:
                if zprice+c>charged_limit:continue
                # Intersecting rows would duplicate readings. Adjacent windows can cover one event.
                if any(x[0]==g and max(lo,x[1])<=min(hi,x[2]) for x in z):continue
                pack=(u,*z)
                v=collection_score(pack) if any(x[0]==g and (hi+1==x[1] or x[2]+1==lo) for x in z) else v0+zv
                visit(pack,v)
        j=int(np.argmax(p));g,a,b=start[j];N=len(groups[g]["lines"]);fixed=()
        for ln in (24,18,12,6,3,1):
            u=(g,max(0,a-3),min(N-1,max(0,a-3)+ln-1))
            if unit_cost(u)<=min(charged_limit,wire_limit):fixed=(u,);break
        ans=dict(recent=recent,r2f=old,fixed=fixed,**dict(zip(("flat","start","typed"),best)))
        answer[B]={arm:payload(z) for arm,z in ans.items()}
        assert all(q<=charged_limit and v<=wire_limit and len(z)<=3 for z,q,v in answer[B].values())
    return answer
def one(k):
    M=read("fine_model.json");M["lookup"]={k:j for j,k in enumerate(M["length_dist"])};M["cdfs"]=np.asarray(list(M["length_dist"].values()))
    origin=prev.read("width_model.json"),e.read("model.json")["flat"],prev.read("offset.json")["intercept"]
    p=D/f"matched_pred_{k}.jsonl.gz";n=0
    with gzip.open(p,"wt",encoding="utf8",compresslevel=3) as out:
        for o in rows(D/f"source_{k}.jsonl.gz"):
            for t,rr,idx,meta,hist,last in stream(o):
                result=at_cut(o,t,rr,idx,meta,hist,last,M,origin)
                atomic_line(out,[o["instance"],t,result]);n+=1
    return (k,n)
def main():
    import os
    S=[D/"PROTOCOL_RU.md",D/"acquire.py",D/"context.py",D/"predict.py",D/"matched_policy.py",D/"MATCHED_PROTOCOL.md",D/"fine_model.json",D/"source_receipt.json",D/"selection.json",*sorted(D.glob("source_*.gz")),F/"budget.py",F/"run.py",F/"width_model.json",F/"offset.json",e.HERE/"model.json"]
    save("matched_method_lock.json",dict(files={str(f):h(f) for f in S},scope="before test scoring"))
    start=time.monotonic();os.environ["OPENBLAS_NUM_THREADS"]="1"
    with ProcessPoolExecutor(5) as ex:
        a=list(ex.map(one,range(8)));print(a)
    save("matched_prediction_lock.json",dict(shards=a,seconds=time.monotonic()-start,files={p.name:h(p) for p in [D/"matched_method_lock.json",*sorted(D.glob("matched_pred_*.gz"))]}))
if __name__=="__main__":main()
