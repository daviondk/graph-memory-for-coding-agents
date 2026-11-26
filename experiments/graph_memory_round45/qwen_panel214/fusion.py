"""Additional preregistered RRF experiment, separate from the primary matched-reader contrast."""
from common import *
from matched import extract, certify, union_value, utility, rank, order, dev_scores, best, GRID, labels, estimate
from fractions import Fraction


def prepare():
    panel=read(OUT/"panel.json");qs=set(panel["order"]);raw=read(R34/"features.json.gz")
    fields=extract(raw)
    base=read(R34/"models.json")[read(R34/"selection.json")["modes"]["union_cost"]]
    train={q for q,r in raw.items() if r["split"]=="train"};dev={q for q,r in raw.items() if r["split"]=="dev"}
    y=labels(train|dev)
    assert not (train|dev)&qs
    dc=certify(raw,{q:y[q] for q in dev});rows={}
    for q,r in raw.items():
        u=union_value(r,base)
        x=fields[q];x[:,3]=np.log1p(rank(u));x[:,4]=u
        rows[q]={"ids":r["ids"],"x":x,"u":u}
    model=estimate(rows,{q:y[q] for q in train},"one_distance_no_seen")
    cs={}
    for q in dev|qs:
        xx=rows[q]["x"].copy();xx[:,11]=0
        cs[q]=(utility(rows[q]["u"]),utility(model.decision_function(xx)))
    def val(q,a):
        u,v=cs[q]
        return (1-a)*u+a*v
    grid={a:dev_scores(raw,dc,{q:order(val(q,a))[:8] for q in dev}) for a in GRID}
    a=best(grid)
    prior=read(OUT/"control-ranks.json.gz")
    all_rows={}
    for q in qs:
        r=raw[q];ids=r["ids"]
        rr={"r39":rank(val(q,a)).tolist(),"bge":r["ranks"]["dense_state"],"union":rank(rows[q]["u"]).tolist()}
        obs=(rows[q]["x"][:,11]!=0).tolist()
        for name,path in (("r39","r39_no_observed"),("bge","bge"),("union","union")):
            index=sorted(range(len(ids)),key=lambda j:rr[name][j])
            assert [ids[j] for j in index[:8]]==prior[q][path]
            compact=sorted(index,key=lambda j:obs[j])
            assert [ids[j] for j in compact[:8]]==prior[q][path+"_seen"]
        all_rows[q]={"ids":ids,"ranks":rr,"seen":obs}
    save("fusion-local-full.json.gz",all_rows)
    save("fusion-local-seal.json",dict(forecasts=sha(OUT/"fusion-local-full.json.gz"),code=sha(Path(__file__)),
                                      protocol=sha(OUT/"FUSION_PROTOCOL_RU.md"),alpha=a,dev=grid))
    print("Frozen and verified three full control orders on 214 states.")


def fuse():
    seal=read(OUT/"fusion-local-seal.json");g=read(OUT/"gpu-seal.json")
    assert sha(OUT/"fusion-local-full.json.gz")==seal["forecasts"] and sha(OUT/"qwen-scores.json.gz")==g["forecasts"]
    local=read(OUT/"fusion-local-full.json.gz");qw=read(OUT/"qwen-scores.json.gz")
    all_rows={};ties=0;checks=0
    for q,r in local.items():
        ids=r["ids"];n=len(ids);qc=qw[q]["scores"];qrank=rank([qc[i] for i in ids]);seen=r["seen"]
        out={"qwen":qw[q]["ranks"]["qwen"],"qwen_seen":qw[q]["ranks"]["qwen_seen"]}
        for name,scores in r["ranks"].items():
            other=np.asarray(scores,int)
            f=1.0/(60+qrank)+1.0/(60+other)
            # Canonical exact order makes true rational ties explicit even when floats round differently.
            exact=[Fraction(1,60+int(qrank[j]))+Fraction(1,60+int(other[j])) for j in range(n)]
            solution=sorted(range(n),key=lambda j:(-exact[j],ids[j]))
            approximate=sorted(range(n),key=lambda j:(-f[j],ids[j]))
            assert all(exact[j]==exact[k] for j,k in zip(solution,approximate) if j!=k)
            # Check rational arithmetic independently with cross multiplication of numerators and denominators.
            num=120+qrank+other;den=(60+qrank)*(60+other)
            for j,k in zip(solution,solution[1:]):
                diff=int(num[j])*int(den[k])-int(num[k])*int(den[j])
                assert diff>0 or (diff==0 and ids[j]<ids[k])
                ties+=int(diff==0);checks+=1
            out[name]=[ids[j] for j in solution[:8]]
            out[name+"_seen"]=[ids[j] for j in sorted(solution,key=lambda j:seen[j])[:8]]
        all_rows[q]=out
    save("fusion-predictions.json.gz",all_rows)
    save("fusion-seal.json",dict(local=sha(OUT/"fusion-local-seal.json"),gpu=sha(OUT/"gpu-seal.json"),
                                forecasts=sha(OUT/"fusion-predictions.json.gz"),adjacent_checks=checks,exact_ties=ties))
    print("Frozen",len(all_rows),"fusion outputs.")


if __name__=="__main__":
    if sys.argv[1]=="prepare":prepare()
    else:fuse()
