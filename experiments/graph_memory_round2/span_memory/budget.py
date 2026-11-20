"""Frozen R2-F with simultaneous constraints on independently encoded tokens and page count."""
import gzip,itertools,json,sys,time
from collections import Counter,defaultdict
from concurrent.futures import ProcessPoolExecutor
from functools import lru_cache
from pathlib import Path
from run import D,E,e,stream,sx,read,save,rows,np
from policy import cost,render

BUDGETS=(256,512)
ARMS=("recent","pointwise","global","history","typed","placebo")
def h(f):return e.sha(Path(f).read_bytes())
@lru_cache(maxsize=55)
def subsets(n):
    tuples=[()]
    for k in (1,2,3):tuples.extend(itertools.combinations(range(n),k))
    return np.array([list(t)+[n]*(3-len(t)) for t in tuples],dtype=np.int16)
def greedy(rank,C,B,text,sep):
    out=[];used=0
    for i in rank:
        j=int(i);add=C[j]+(sep if out else 0)
        if used+add>B or cost("\n".join(text[x] for x in out+[j]))>B:continue
        out.append(j);used+=add
        if len(out)==3:break
    return out
def calc_sets(n,idx,seq,links):
    combos=subsets(n)
    # A repeated sentinel denotes absent pages; pair/triple masses are zero for sentinel.
    nxt={};inv={i:j for j,i in enumerate(idx)}
    for j,i in enumerate(idx):
        path,lo,hi,t,code=seq[i];k=links.get((path,hi+1))
        if k in inv:nxt[j]=inv[k]
    end3=[]
    for j,k in nxt.items():
        if k in nxt:
            a,b,c=sorted((j,k,nxt[k]))
            import math
            rank=1+n+math.comb(n,2)+math.comb(n,3)-math.comb(n-a,3)+math.comb(n-a-1,2)-math.comb(n-b,2)+(c-b-1)
            assert tuple(combos[rank])==(a,b,c)
            end3.append((j,rank))
    return combos,nxt,end3
def values(weights,combo,nxt,chains):
    n=len(weights);a,b,c=combo.T
    node=np.r_[weights[:,0],0.]
    adj=np.zeros((n+1,n+1))
    for j,k in nxt.items(): adj[j,k]=adj[k,j]=weights[j,1]
    out=node[a]+node[b]+node[c]+adj[a,b]+adj[a,c]+adj[b,c]
    for j,k in chains:out[k]+=weights[j,2]
    return out
def choose(v,comb,ok,txt,B):
    candidates=np.flatnonzero(ok)
    while len(candidates):
        best=int(np.argmax(v[candidates]));row=comb[candidates[best]]
        ids=[int(q) for q in row if q<len(txt)]
        if cost("\n".join(txt[i] for i in ids))<=B:return ids
        candidates=np.delete(candidates,best)
    raise AssertionError("empty set should be admissible")
def probs(r,idx,meta,hist,last,t,obj,w,flat,offset):
    F,X,links=sx(r,idx,meta,hist,last,t,obj)
    p=1/(1+np.exp(-np.clip(sum(np.take(v,F[:,c]) for c,v in enumerate(flat))+offset,-25,25)))
    Ws={"global":np.tile(w["global"],(len(idx),1))}
    for name in ["history","typed","placebo"]:
        field="typed" if name=="placebo" else name
        b,ws=w[field];m=X.copy()
        if name=="placebo" and len(idx)>1:
            shift=1+int(e.sha(obj["instance"]+str(t))[:8],16)%(len(idx)-1)
            m[:,3:]=np.roll(m[:,3:],shift,axis=0)
        z=b+sum(np.asarray(v)[m[:,c]] for c,v in enumerate(ws));z-=z.max(1,keepdims=True)
        Z=np.exp(z);Ws[name]=Z/Z.sum(1,keepdims=True)
    return p,Ws,links
def brute():
    rng=np.random.default_rng(261118);checked=0
    for n in range(1,11):
        for rep in range(5):
            ix=rng.permutation(n).tolist();s=[("a",i*12+1,(i+1)*12,0,"") for i in range(n)]
            lookup={(q[0],q[1]):i for i,q in enumerate(s)}
            combo,edges,triples=calc_sets(n,ix,s,lookup);w=rng.uniform(size=(n,4));o=values(w,combo,edges,triples)
            cc=rng.integers(1,50,n);costs=np.r_[cc,0][combo].sum(1)+(combo<n).sum(1).clip(min=1)-1
            set_cost=[sum(cc[i] for i in row if i<n)+max(0,sum(i<n for i in row)-1) for row in combo]
            assert np.array_equal(costs,set_cost)
            obj=[]
            for row in combo:
                S={ix[j] for j in row if j<n}
                obj.append(sum(w[j,k-1] for j,i in enumerate(ix) for k in (1,2,3) if set(range(i,i+k))<=S))
            assert np.allclose(o,obj)
            for B in (25,55,82):
                ok=costs<=B
                assert np.isclose(max(o[ok]),max(v for v,c in zip(obj,set_cost) if c<=B))
            checked+=len(combo)
    return checked
def predict(k):
    w=read("width_model.json");flat=e.read("model.json")["flat"];offset=read("offset.json")["intercept"]
    sep=cost("\n");assert sep==1
    with gzip.open(D/f"budget_pred_{k}.jsonl.gz","wt",encoding="utf8",compresslevel=3) as out:
        for obj in rows(D/f"fresh_{k}.jsonl.gz"):
            for t,r,idx,meta,hist,last in stream(obj):
                n=len(idx); text=[render(r[i]) for i in idx];C=np.array([cost(s) for s in text],int)
                choices={B:{} for B in BUDGETS}
                if n:
                    p,W,L=probs(r,idx,meta,hist,last,t,obj,w,flat,offset)
                    combo,nxt,chains=calc_sets(n,idx,r,L);ks=(combo<n).sum(1)
                    price=np.r_[C,0][combo].sum(1)+np.maximum(0,ks-1)*sep
                    scores={a:values(v*p[:,None],combo,nxt,chains) for a,v in W.items()}
                for B in BUDGETS:
                    selected={}
                    if n:
                        selected["recent"]=greedy(range(n),C,B,text,sep)
                        selected["pointwise"]=greedy(np.argsort(-p,kind="stable"),C,B,text,sep)
                        for a,v in scores.items():selected[a]=choose(v,combo,price<=B,text,B)
                    else:selected={a:[] for a in ARMS}
                    for a,js in selected.items():
                        ids=[idx[i] for i in js];total=int(sum(C[j] for j in js)+max(0,len(js)-1)*sep)
                        wire=cost("\n".join(text[i] for i in js))
                        assert total<=B and wire<=B and len(ids)==len(set(ids))<=3
                        choices[B][a]=[ids,total,wire]
                e.packed(out,[obj["instance"],t,list(zip(idx,C.tolist())),choices])
def grade_shard(k):
    # Rebuild prefix independently for native encoding, verifying every decision and its denominator.
    from tokenizers import Tokenizer
    enc=Tokenizer.from_file(str(e.PACK/"qwen_tokenizer.json"));enc.no_truncation();enc.no_padding()
    def tokens(s):return len(enc.encode(s,add_special_tokens=False).ids)
    tokens=lru_cache(maxsize=80000)(tokens)
    sep=tokens("\n")
    pred={(i,t):(cc,aa) for i,t,cc,aa in rows(D/f"budget_pred_{k}.jsonl.gz")}
    natives={(i,t):a for i,t,a,cs in rows(D/f"pred_{k}.jsonl.gz")}
    gold={(i,t):(sp,up) for i,t,sp,up in rows(D/f"gold_{k}.jsonl.gz")}
    allrows=[];seen=0;cost_checks=0
    for obj in rows(D/f"fresh_{k}.jsonl.gz"):
        i=obj["instance"]
        for t,r,idx,meta,hist,last in stream(obj):
            seen+=1;cc,aa=pred[i,t]
            assert [z[0] for z in cc]==idx
            texts={j:f"@@ {r[j][0]} {r[j][1]}..{r[j][2]} @@\n"+r[j][4] for j in idx}
            C={j:tokens(s) for j,s in texts.items()};assert C==dict(cc)
            for B in BUDGETS:
                for a,(sel,ind,wire) in aa[str(B)].items():
                    assert len(sel)==len(set(sel))<=3 and set(sel)<=set(idx)
                    assert sum(C[v] for v in sel)+max(0,len(sel)-1)*sep==ind<=B
                    assert tokens("\n".join(texts[v] for v in sel))==wire<=B
                    cost_checks+=1
            if (i,t) not in gold:continue
            span,up=gold[i,t];sp=set(span)
            assert up==int(bool(sp) and len(sp)<=3 and sp<=set(idx))
            old={a:int(bool(sp) and sp<=set(js)) for a,js in natives[i,t].items()}
            for B in BUDGETS:
                oracle=0
                if up and sum(C[v] for v in sp)+max(0,len(sp)-1)*sep<=B:
                    # Feasible under some order; all arms satisfy this ceiling.
                    oracle=int(any(tokens("\n".join(texts[v] for v in perm))<=B for perm in itertools.permutations(sp)))
                hits={a:int(bool(sp) and sp<=set(z[0])) for a,z in aa[str(B)].items()}
                assert all(v<=oracle for v in hits.values())
                allrows.append([i,t,B,span,oracle,hits,old,{a:[len(z[0]),z[1],z[2]] for a,z in aa[str(B)].items()}])
    assert len(pred)==seen==len(natives)
    return allrows,seen,cost_checks,len({i for i,t in pred})
def paired(d,ii):
    sub,inv=np.unique(ii,return_inverse=True);s=np.bincount(inv,weights=d);c=np.bincount(inv)
    rng=np.random.default_rng(261118);bs=rng.integers(len(c),size=(10000,len(c)))
    d=np.asarray(d);return {"delta":float(d.mean()),"wins":int((d>0).sum()),"losses":int((d<0).sum()),
                        "ci":np.quantile(s[bs].sum(1)/c[bs].sum(1),[.025,.975]).tolist(),
                        "repo_macro":float((s/c).mean()),"by_repo":{k:[int(v),int(n)] for k,v,n in zip(sub,s,c)}}
def grade():
    lock=read("budget_lock.json")
    for s,v in lock["sha256"].items():assert h(s)==v
    with ProcessPoolExecutor(4) as pool:shards=list(pool.map(grade_shard,range(8)))
    sc=[r for rr,*_ in shards for r in rr]
    with gzip.open(D/"budget_scored.jsonl.gz","wt",encoding="utf8") as out:
        for r in sc:e.packed(out,r)
    results={"prediction_cuts":sum(r[1] for r in shards),"token_checks":sum(r[2] for r in shards),"instances_streamed":sum(r[3] for r in shards),"budget":{}}
    base=read("results.json");assert results["prediction_cuts"]==base["all_cuts"] and results["instances_streamed"]==base["seen_instances"]
    for B in BUDGETS:
        rr=[r for r in sc if r[2]==B];ii=[r[0].split(".")[0] for r in rr]
        assert len(rr)==base["n"] and len({r[0] for r in rr})==base["included_instances"]
        count=lambda col,a:sum(r[col][a] for r in rr)
        assert {a:count(6,a) for a in ARMS}==base["hits"]
        per={"n":len(rr),"repos":len(set(ii)),"instances":len(set(r[0] for r in rr)),"hits":{a:count(5,a) for a in ARMS},
             "upper_bound":sum(r[4] for r in rr),"costs":{},"typed_minus":{},"vs_no_token_cap":{}}
        for a in ARMS:
            p=np.array([r[7][a] for r in rr]);per["costs"][a]={"mean_pages":p[:,0].mean(),"mean_charged":p[:,1].mean(),"mean_joint":p[:,2].mean(),
              "max_charged":int(p[:,1].max()),"max_joint":int(p[:,2].max()),"empty":int((p[:,0]==0).sum())}
            per["typed_minus"][a]=paired([r[5]["typed"]-r[5][a] for r in rr],ii)
            per["vs_no_token_cap"][a]=paired([r[5][a]-r[6][a] for r in rr],ii)
        results["budget"][B]=per
        print(B,per["hits"],per["upper_bound"],flush=True)
    save("budget_results.json",results)
def main():
    mode=sys.argv[1] if len(sys.argv)>1 else "all"
    if mode in ("all","predict"):
        start=time.perf_counter();checks=brute()
        for n,sha in read("decision_lock.json").items():assert h(D/n)==sha
        with ProcessPoolExecutor(4) as pool:list(pool.map(predict,range(8)))
        paths=[D/"BUDGET_PROTOCOL.md",D/"budget.py",D/"decision_lock.json",D/"run.py",E/"model.json",D/"width_model.json",D/"offset.json",
               e.PACK/"policy.py",e.PACK/"qwen_tokenizer.json",*sorted(D.glob("fresh_*.gz")),*sorted(D.glob("budget_pred_*.gz"))]
        save("budget_lock.json",{"sha256":{str(p):h(p) for p in paths},"brute_force_sets":checks,"prediction_seconds":time.perf_counter()-start})
    if mode in ("all","grade"):grade()
if __name__=="__main__":main()
