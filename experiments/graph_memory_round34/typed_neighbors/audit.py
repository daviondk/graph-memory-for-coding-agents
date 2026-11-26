"""Finite-population enumeration and descriptive support of the additional regressor."""
from itertools import combinations
from channels import D,CACHE,load,np,sha,save
def check_moments():
    count=0;eps=0.
    for n in range(1,10):
        for h in (1/np.log2(1+np.arange(1,n+1)),np.array([1.+(i%3)/5 for i in range(n)]),np.ones(n)):
            for d in range(1,n+1):
                samples=np.array([sum(h[j] for j in indices) for indices in combinations(range(n),d)])
                var=d*h.var()*(n-d)/(n-1) if n>1 else 0
                eps=max(eps,abs(d*h.mean()-samples.mean()),abs(var-samples.var()))
                count+=1
    assert eps<1e-12
    return dict(enumerations=count,max_error=eps)
def audit():
    result={"finite_population":check_moments(),"selection":sha(D/"selection.json"),"stages":{}}
    weights=load(D/"models.json")["models"]["agreement"]
    result["agreement_coefficient_standardized"]=weights["w"][-1];result["agreement_coefficient_raw_units"]=weights["w"][-1]/weights["sd"][-1]
    for stage in ("train","dev","test"):
        f=CACHE/(stage+".json.gz")
        if not f.exists():continue
        src=load(D/(stage+"-inputs.json"));r=load(f);assert sha(f)==src["rows_file"]
        info={"changed_original_arcs":src["changed_arcs"],"original_arcs":src["arcs"]};result["stages"][stage]=info
        if stage=="train":
            yes=hit=tot=positive=0
            for v in r:
                x=np.array(v["x"])[:,17]>0;ids=v["y"];yes+=int(x.sum());hit+=int(x[ids].sum());positive+=len(ids);tot+=len(x)
            info["positive_pu_with_concordance"]=hit;info["total_positive_pu"]=positive;info["concordant_pu"]=yes;info["pu"]=tot
        else:
            rr=load(D/(stage+"-ranks.json.gz"));cells=load(D/(stage+"-outcomes.json.gz"))
            for ctrl in ("additive","rewired","frozen","transplant"):
                ch=win=loss=0
                for q,v in rr.items():
                    a=v["ranks"]["agreement"];b=v["ranks"][ctrl];ch+=int(a!=b)
                    fs=cells[q]["arms"];win+=int(fs["agreement"][0]>fs[ctrl][0]);loss+=int(fs["agreement"][0]<fs[ctrl][0])
                info[ctrl]={"changed_complete_order":ch,"won_full_support":win,"lost_full_support":loss}
    save(D/"mechanism-audit.json",result)
if __name__=="__main__":audit()