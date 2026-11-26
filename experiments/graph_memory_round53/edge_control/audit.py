"""Portable replay of the primary and link-imitation decisions from numeric candidate features."""
from bisect import bisect_left
from itertools import combinations
from math import comb,log1p
from setup import *
def audit(export=False):
    from grade import marginal,main as grade
    from diagnose import main as diagnostic
    seal=read(D/"prediction-seal.json");model=read(D/"model.json");z={}
    for p in ("2wiki","hotpot"):
        rows=read(D/(p+"-choices.json.gz"));src=SPLITS[p][0];old=read(src/"predictions.json.gz");arms=read(src/"prediction-seal.json")["arms"]
        archive=D/(p+"-eligible.json.gz")
        if export:
            from decide import stream
            assert sha(WORK/(p+".tsv.gz"))==seal["dump_hash"][p]
            feature={q:rs for q,rs in stream(p) if not rows[q]["direct"] and rows[q]["sizes"][2]>0};save(archive,feature)
        raw=read(archive);count=0
        for q,r in rows.items():
            nh,nl,k,overlap=r["sizes"];assert k==min(nh,nl) and nh<=nl
            ph,pl=[old[q]["choices"][arms.index(k)] for k in ("primary_href","primary_text")]
            assert r["fixed"][-2:]==[ph,pl]
            if r["direct"] or not k:
                expected=ph if r["direct"] else r["base"]
                assert r["fixed"][:5]==[expected]*5 and r["random"]==[[expected],[expected]]
                continue
            count+=1;items=sorted(raw[q],key=lambda a:(-a[2],a[1],a[0]));li=[a for a in items if a[5]];h=[a for a in items if a[6]]
            assert len(h)==nh==k and len(li)==nl and overlap==sum(x[6] for x in li)
            assert [[a[0] for a in g] for g in (h,li)]==r["random"]
            pos=sorted(x[3] for x in li);length=sorted(-x[4] for x in li)
            rank=sorted(range(nl),key=lambda j: (-(1/(1+min(j,4))+1/(1+bisect_left(pos,li[j][3]))+1/(1+bisect_left(length,-li[j][4]))),j))
            expected=li[min(rank[:k])][0]
            scores=[]
            for j,(_,_,b,t,w,n,_) in enumerate(li):
                f=[16/(16+t),min(w,8)/8,n/(n+1),log1p(max(b,0))/6,1/(1+j)]
                scores.append(model["intercept"]+sum(v*x for v,x in zip(model["coef"],f)))
            proxy=li[min(sorted(range(nl),key=lambda j:(-scores[j],j))[:k])][0]
            assert [h[0][0],expected,h[0][0],li[0][0],proxy]==r["fixed"][:5]
        assert count==len(raw);z[p]={"verified_questions":len(rows),"replayed_candidate_sets":count,"sha":sha(archive)}
    for n in range(1,11):
        for k in range(1,n+1):
            for j in range(n):
                a=marginal(list(range(n)),k,lambda i:(float(i==j),0))[0]
                b=sum(sub[0]==j for sub in combinations(range(n),k))/comb(n,k)
                assert abs(a-b)<1e-12
    grade(True);diagnostic(True)
    receipt=dict(panels=z,weighted_rank_closed_form_small_cases="all ranks in every subset size for n=1..10",
         pred_seal=sha(D/"prediction-seal.json"),grading=sha(D/"grading-seal.json"),code=sha(Path(__file__)))
    if export:save(D/"audit.json",receipt)
    else:assert read(D/"audit.json")==receipt
    print("VERIFIED",z)
if __name__=="__main__":
    import sys
    audit("--export" in sys.argv)
