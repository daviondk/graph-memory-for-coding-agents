"""Recompute the two designs via separate stratified order statistics and verify interval scores."""
from experiment import *
from collections import Counter
def main():
    out=load(D/"outcomes.json.gz");report=load(D/"results.json");assert report["source"]==sha(D/"outcomes.json.gz")
    ar=up.W/"graph_memory_round34/interval_witness";ats=load(ar/"test-atoms.json.gz");source=Path("D:/CodexResearch/x20-r33-budget-loss/test.json.gz");cs={r["q"]:r["c"] for r in load(source)}
    ngeom=nscore=ncontrol=0;histL=0;histK=0
    for i in range(8):
        for t,a in load(D/f"edges-{i}.json.gz").items():
            arc=a["extra_edges"];H=set(a["H"]);addr=a["hashes"];histL+=len(arc);histK+=len(H)
            def degrees(items):return Counter(arc[z][0] for z in items),Counter(arc[z][1] for z in items)
            group=defaultdict(list)
            for j,(_,b) in enumerate(arc):group[b].append(j)
            dout,din=degrees(H);assert degrees(a["swapped"])==(dout,din)
            for s in SALTS:
                keys=[hashlib.sha256("|".join([PRE,s,t,addr[x],addr[y]]).encode()).hexdigest() for x,y in arc]
                keep=lambda indices,k:set(sorted(indices,key=lambda j:(keys[j],j))[:k])
                g=keep(range(len(arc)),len(H));sub=set()
                for target,opts in group.items():sub.update(keep(opts,din[target]))
                assert g==set(a["draws"]["G_"+s]) and sub==set(a["draws"]["T_"+s]) and degrees(sub)[1]==din and len(g)==len(sub)==len(H)
                ngeom+=2
        for q,r in load(D/f"selected-{i}.json.gz").items():
            atoms=ats[q];length=np.array([b-a for _,a,b,g in atoms]);assert r["full_sha"]["M"]==r["full_sha"]["swap"];ncontrol+=1
            y=out[q]["arms"]
            for m,ix in r["picks"].items():
                pool=set(ix);ok=np.array([any(i in pool for i in g) for *_,g in atoms]);assert np.allclose(y[m],[ok.all(),length[ok].sum()/length.sum(),sum(cs[q][j] for j in ix)],atol=1e-12,rtol=0);nscore+=1
    assert ncontrol==2000 and nscore==40000 and ngeom==19312 and histL==66920 and histK==4768
    for fam in ("G","T"):
        ref=report["panels"]["eligible"];a=ref["compared"][fam];assert np.allclose(a["M_minus_random"],np.mean(list(a["per_salt_delta"].values()),axis=0))
    put(D/"audit.json",dict(target_and_global_draws_independently_verified=ngeom,order_equality_M_vs_double_degree=ncontrol,case_methods=nscore,outcome_components=nscore*3,full_pool_extra_edges=histL,K=histK,results=sha(D/"results.json")))
    print("checked",ngeom,nscore,ncontrol)
if __name__=="__main__":main()