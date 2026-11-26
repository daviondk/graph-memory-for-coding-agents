"""Fit the external calibration losses on train, select on dev and seal blind test forecasts."""
from prepare import *
from scipy.optimize import minimize
from scipy.special import expit,logsumexp
METRICS=["CompleteMSS@8_6144Qwen","CompleteMSS@5","CompleteMSS@8","GroupRecall@8","CompleteMSS@8_2048WordPiece","ReadQwenTokens","ReadUnits"]
FAMS=("point","group","group_no_edges","union_cost")
def split_gold(wanted):
    with gzip.open(PUB/"labels.jsonl.gz","rt",encoding="utf8") as f:
        return {r["state_id"]:r for r in map(json.loads,f) if r["state_id"] in wanted}
def encode(ids,gold):
    ix={k:j for j,k in enumerate(ids)}
    groups=[(np.array([ix[k] for k in g["acceptable_evidence_ids"] if k in ix],int),g["minimum_required"]) for g in gold["required_evidence_groups"]]
    alts=[np.array([ix[k] for k in a],int) for a in gold["alternative_minimal_sets"] if a and all(k in ix for k in a)]
    return groups,alts
def score(row,order,gold):
    groups,alts=encode(row["ids"],gold);lengths=np.array(row["qw"]);wp=np.array(row["wp"])
    def within(c,B):
        cum=np.cumsum(c[order[:8]]);return order[:int(np.sum(cum<=B))]
    def stats(ix):
        y=set(ix);g=[sum(v in y for v in c)>=m for c,m in groups]
        return int(all(g) or any(all(v in y for v in a) for a in alts)),np.mean(g) if g else 1
    budget=within(lengths,6144);big=stats(order[:8]);return [stats(budget)[0],stats(order[:5])[0],big[0],float(big[1]),stats(within(wp,2048))[0],sum(int(lengths[v]) for v in budget),len(budget)]
def variants(x,fam):
    a=x.copy()
    if fam=="group_no_edges":a[:,2:]=0
    return a
def prepare_train(data,labels,fam):
    values=[variants(np.array(r["x"]),fam) for r in data.values()]
    center=np.mean([v.mean(0) for v in values],axis=0);sc=np.sqrt(np.mean([((v-center)**2).mean(0) for v in values],axis=0))
    sc[sc<1e-8]=1;prep=[]
    for (q,r),v in zip(data.items(),values):
        gs,al=encode(r["ids"],labels[q]);n=len(v); indices=set(j for g,_ in gs for j in g)|set(j for a in al for j in a)
        y=np.array(sorted(indices),dtype=int); neg=np.array([j for j in range(n) if j not in indices])
        if not len(y) or not len(neg):continue
        gs=gs if gs and all(len(g)>=m for g,m in gs) else []
        if not gs and not al:continue
        prep.append(((v-center)/sc,np.array(r["off"]),np.array(r["wp"]),y,neg,gs,al))
    return center,sc,prep
def soft(v,X,sign):
    # Normalized log-mean-exp prevents group cardinalities from introducing a prior.
    u=sign*v/.25; l=logsumexp(u)
    return sign*.25*(l-np.log(len(u))),np.exp(u-l)@X
def optimize(data,labels,fam,reg):
    center,scale,prep=prepare_train(data,labels,fam);npar=5 if fam=="point" else 4
    def objective(b):
        loss=0.;g=np.zeros(npar)
        for X,off,c,y,neg,groups,alts in prep:
            s=off+X@b[:4]
            if fam=="point":
                s=s+b[-1]; mask=np.zeros(len(c));mask[y]=1; w=np.where(mask,.5/len(y),.5/len(neg))
                z=w*(expit(s)-mask);loss+=w@(np.logaddexp(0,s)-mask*s);g[:4]+=X.T@z;g[-1]+=z.sum();continue
            if fam=="union_cost":h,dh=soft(s[y],X[y],-1)
            else:
                routes=[]
                if groups:
                    chosen=[c[np.argsort(-s[c],kind="stable")[m-1]] for c,m in groups]
                    routes.append(soft(s[chosen],X[chosen],-1))
                for a in alts:routes.append(soft(s[a],X[a],-1))
                if len(routes)==1:h,dh=routes[0]
                else:h,dh=soft(np.array([z[0] for z in routes]),np.array([z[1] for z in routes]),1)
            w=c[neg]/c[neg].sum();diff=s[neg]-h
            loss+=w@np.logaddexp(0,diff);z=w*expit(diff);g+=z@X[neg]-z.sum()*dh
        loss/=len(prep);g/=len(prep);loss+=reg*.5*(b[:4]@b[:4]);g[:4]+=reg*b[:4]
        return loss,g
    b0=np.zeros(npar);res=minimize(objective,b0,method="L-BFGS-B",jac=True,options={"maxiter":130,"ftol":1e-10})
    if not res.success:res=minimize(lambda b:objective(b)[0],res.x,method="Powell",options={"maxiter":80,"ftol":1e-9})
    assert res.success
    return {"center":center.tolist(),"scale":scale.tolist(),"weights":res.x.tolist(),"family":fam,"reg":reg,"training":len(prep),"objective":float(res.fun),"iterations":res.nit}
def predictions(row,models,raw):
    off=np.array(row["off"]);X=np.array(row["x"]);n=len(X);r={m:np.argsort(v,kind="stable") for m,v in row["ranks"].items()}
    def sort(s):return np.argsort(-s,kind="stable")
    r["shortest"]=np.argsort(row["wp"],kind="stable")
    for beta in (0,.25,1):r[f"length_{beta}"]=sort(off-beta*X[:,1])
    for role in (0,1):
        z=np.column_stack((X[:,0],X[:,1],np.full(n,role),role*X[:,1]))
        r["frozen_role"+str(role)]=sort(off+(z-raw["center"])/raw["scale"]@raw["weights"])
    for m,model in models.items():
        z=variants(X,model["family"]);v=(z-model["center"])/model["scale"];r[m]=sort(off+v@model["weights"][:4])
    assert np.array_equal(r["rrf"],r["length_0"])
    return r
def main():
    path=HERE/"features.json.gz";assert sha(path)==read(HERE/"input.json")["features"]
    data=read(path); train={q:r for q,r in data.items() if r["split"]=="train"};dev={q:r for q,r in data.items() if r["split"]=="dev"}
    labels=split_gold(train.keys()|dev.keys());assert labels.keys()==train.keys()|dev.keys()
    models={f"{f}_{g}":optimize(train,labels,f,g) for f in FAMS for g in (.03,.3)};save(HERE/"models.json",models)
    raw=read(ISE/"models.json")["models"][read(ISE/"selection.json")["policy"]]
    devscores=defaultdict(list)
    for q,row in dev.items():
        for m,order in predictions(row,models,raw).items():devscores[m].append(score(row,order,labels[q]))
    av={m:np.mean(v,axis=0).tolist() for m,v in devscores.items()}
    modes={f:max((f"{f}_0.03",f"{f}_0.3"),key=lambda k:round(av[k][0],12)) for f in FAMS}
    modes["length_penalty"]=max(("length_0","length_0.25","length_1"),key=lambda k:round(av[k][0],12))
    for f in ("rrf","bm25","dense_state","dense_addresses","shortest","frozen_role0","frozen_role1"):modes[f]=f
    save(HERE/"selection.json",{"modes":modes,"dev":av,"models":sha(HERE/"models.json"),"features":sha(path),"protocol":sha(HERE/"PROTOCOL_RU.md")})
    ranks={}
    for q,row in data.items():
        if row["split"]!="test":continue
        full=predictions(row,models,raw);ranks[q]={k:full[v].tolist() for k,v in modes.items()}
    dst=HERE/"test-ranks.json.gz";save(dst,ranks)
    save(HERE/"seal.json",{"forecasts":sha(dst),"selection":sha(HERE/"selection.json"),"frozen":sha(ISE/"models.json"),"code":sha(Path(__file__))})
    print("frozen",len(ranks),modes)
if __name__=="__main__":
    from collections import defaultdict
    main()
