"""Only after forecast seal, join test predictions to the independent evidence certificates."""
from experiment import *
from collections import defaultdict
from serbench import _reference_scorer as ref

def main():
    ranked=HERE/"test-ranks.json.gz";seal=read(HERE/"seal.json")
    assert sha(ranked)==seal["forecasts"] and sha(HERE/"selection.json")==seal["selection"]
    preds=read(ranked);data=read(HERE/"features.json.gz");gold=split_gold(set(preds));assert preds.keys()==gold.keys()
    out={}; ingroups=Counter(); official_checks=0
    for q,methods in preds.items():
        row=data[q]; g=gold[q];ids=row["ids"];n=len(ids);c=np.array(row["qw"]);wp=np.array(row["wp"])
        assert row["split"]=="test" and g["state_id"]==q
        # The ideal depends only on groups, weights and k; cache it locally per state.
        original=ref.ideal_group_dcg; memo={}
        def ideal(gs,w,k):
            if k not in memo:memo[k]=original(gs,w,k)
            return memo[k]
        ref.ideal_group_dcg=ideal
        try:
            native={}
            def run(ix,k):
                key=tuple(ix[:k]),k
                if key not in native:native[key]=ref.score_prediction([ids[j] for j in ix],g,k)
                return native[key]
            res={}
            for m,v in methods.items():
                order=np.array(v);assert sorted(v)==list(range(n));scores=score(row,order,g)
                for lens,budget,loc in ((c,6144,0),(wp,2048,4)):
                    length=int(np.sum(np.cumsum(lens[order[:8]])<=budget));assert scores[loc]==run(order[:length],8)["mss_complete@8"]
                assert scores[1]==run(order,5)["mss_complete@5"]
                assert scores[2]==run(order,8)["mss_complete@8"] and abs(scores[3]-run(order,8)["group_recall@8"])<1e-12
                official_checks+=5;res[m]=scores
        finally:ref.ideal_group_dcg=original
        out[q]={"repo":row["repo"],"task":row["task"],"n":n,"edge_present":bool(np.sum(np.array(row["x"])[:,2])>0),"arms":res}
    op=HERE/"test-outcomes.json.gz";save(op,out)
    qs=sorted(out);mnames=sorted(out[qs[0]]["arms"]);vals=np.array([[out[q]["arms"][m] for m in mnames] for q in qs])
    cs=[("frozen_role1","rrf"),("group","group_no_edges"),("group","point"),("group","length_penalty"),("group","union_cost"),("group","rrf"),("point","rrf"),("length_penalty","rrf"),("frozen_role0","rrf"),("dense_addresses","dense_state")]
    deltas=np.array([vals[:,mnames.index(a)]-vals[:,mnames.index(b)] for a,b in cs]).transpose((1,0,2))
    repos=sorted({out[q]["repo"] for q in qs});clusters=[[i for i,q in enumerate(qs) if out[q]["repo"]==t] for t in repos];n=len(repos)
    size=np.array(list(map(len,clusters)));sums=np.array([deltas[g].sum(0).ravel() for g in clusters])
    rng=np.random.default_rng(34);sims=[]
    for _ in range(100):
        take=rng.integers(n,size=(100,n))+n*np.arange(100)[:,None]
        w=np.bincount(take.ravel(),minlength=100*n).reshape(100,n);sims.append(w@sums/(w@size)[:,None])
    low,high=np.quantile(np.concatenate(sims),[.025,.975],axis=0).reshape(2,len(cs),len(METRICS))
    effects={}
    for i,(a,b) in enumerate(cs):
        v=deltas[:,i];effects[a+" minus "+b]={"delta":v.mean(0).tolist(),"ci95":[low[i].tolist(),high[i].tolist()],"wins_losses":[int(np.sum(v[:,0]>0)),int(np.sum(v[:,0]<0))]}
    means={m:vals[:,i].mean(axis=0).tolist() for i,m in enumerate(mnames)}; splits={}
    for k in ("train","dev","test"):
        t=[r for r in data.values() if r["split"]==k];splits[k]={"states":len(t),"repos":len({r["repo"] for r in t}),"tasks":len({r["task"] for r in t}),"candidates":sum(len(r["ids"]) for r in t),"edges":sum(np.sum(np.array(r["x"])[:,2])>0 for r in t).item()}
    sectors={str(k):{m:np.mean([r["arms"][m][0] for r in out.values() if r["edge_present"]==k]).item() for m in mnames} for k in (False,True)}
    save(HERE/"results.json",{"metrics":METRICS,"splits":splits,"means":means,"effects":effects,"edge_subgroup_primary":sectors,"native_checks":official_checks,"seal":sha(HERE/"seal.json"),"outcomes":sha(op),"gold":sha(PUB/"labels.jsonl.gz"),"scorer":sha(Path(ref.__file__))})
    print(splits,[(k,round(v[0],3)) for k,v in means.items()])
if __name__=="__main__":main()
