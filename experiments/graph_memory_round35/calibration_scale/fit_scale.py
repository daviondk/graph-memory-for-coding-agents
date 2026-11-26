"""Fold-specific structural and rank calibration; common fixed offset at inference."""
from prepare_scale import *
from scipy.optimize import minimize
from scipy.special import expit
MODES=("oof","full","rotated")
def correction(z,off,c,y,starts,reg=.03):
    ends=np.r_[starts[1:],len(y)];nq=len(starts);qn=np.repeat(np.arange(nq),ends-starts)
    center=np.mean(np.add.reduceat(z,starts,axis=0)/(ends-starts)[:,None],axis=0)
    scale=np.sqrt(np.mean(np.add.reduceat((z-center)**2,starts,axis=0)/(ends-starts)[:,None],axis=0));scale[scale<1e-9]=1
    zz=(z-center)/scale;xp=zz[y];xn=zz[~y];op=off[y];on=off[~y];gpos=qn[y];gneg=qn[~y]
    npers=np.bincount(gpos,minlength=nq);nn=np.bincount(gneg,minlength=nq)
    assert npers.min()>=1 and nn.min()>=1
    ip=np.r_[0,np.cumsum(npers)[:-1]];ineg=np.r_[0,np.cumsum(nn)[:-1]]
    qwt=c[~y].astype(float);tot=np.add.reduceat(qwt,ineg);assert min(tot)>0;qwt=qwt/tot[gneg]/nq
    def obj(v):
        s=op+xp@v;lo=np.minimum.reduceat(s,ip);a=np.exp(-(s-lo[gpos])/.25);mass=np.add.reduceat(a,ip)
        h=lo-.25*np.log(mass/npers);d=on+xn@v-h[gneg];e=qwt*expit(d)
        return qwt@np.logaddexp(0.,d)+.5*reg*(v@v),xn.T@e-xp.T@(a/mass[gpos]*np.add.reduceat(e,ineg)[gpos])+reg*v
    zero=np.zeros(4);check=np.array([(obj(zero+v*1e-5)[0]-obj(zero-v*1e-5)[0])/2e-5 for v in np.eye(4)])
    assert np.allclose(check,obj(zero)[1],atol=1e-7)
    r=minimize(obj,zero,jac=True,method="L-BFGS-B",options=dict(ftol=1e-14,gtol=1e-8,maxiter=300));v=r.x;assert r.success and np.linalg.norm(obj(v)[1])<1e-6
    return dict(weights=v.tolist(),center=center.tolist(),scale=scale.tolist(),risk=float(obj(v)[0]),gradient_norm=float(np.linalg.norm(obj(v)[1])),iterations=r.nit)
def fit():
    meta=load(D/"train-inventory.json");fp=D/"numeric-train.npz";assert meta["npz"]==sha(fp)
    a=np.load(fp);gx,y,z,c=a["g"],a["y"],a["z"],a["c"];order=meta["order"];R=meta["records"];rr=[R[q] for q in order]
    n=np.array([r["n"] for r in rr]);qrow=np.repeat(np.arange(len(n)),n);lo=np.r_[0,np.cumsum(n)[:-1]]
    pos=np.add.reduceat(y.astype(int),lo);neg=n-pos;graph=np.array([r["prior"] for r in rr]);rfit=np.array([r["rank_fit"] for r in rr])
    ff=np.array([r["fold"] for r in rr]);w=np.where(y,.5/pos[qrow],.5/neg[qrow]);rx=np.vstack([f.rank_x(int(k)) for k in n])
    def get(features,mask):
        use=mask[qrow];return f.lr(features[use],y[use],w[use])
    frozen_g=f.lin(b.MODEL,gx);frozen_r=f.lin(b.RANK,rx)
    g0=get(gx,graph);r0=get(rx,rfit);grdiff=np.abs(f.lin(g0,gx)-frozen_g);radiff=np.abs(f.lin(r0,rx)-frozen_r)
    assert grdiff.max()<.002 and radiff.max()<.002,(grdiff.max(),radiff.max())
    offsets={m:np.empty(len(y)) for m in MODES};cache={};fold_sign={}
    for k in range(5):
        gg=graph&(ff!=k);rg=rfit&(ff!=k);gm=get(gx,gg);rm=get(rx,rg);cache[k]=(gm,rm)
        fold_sign[k]=dict(graph_questions=int(gg.sum()),graph_t=len({r["t"] for i,r in enumerate(rr) if gg[i]}),rank_questions=int(rg.sum()),rank_t=len({r["t"] for i,r in enumerate(rr) if rg[i]}),
            holdout_questions=int((ff==k).sum()),held_t=len({r["t"] for i,r in enumerate(rr) if ff[i]==k}),
            graph_trajectory_sha=digest("\n".join(sorted({r["t"] for i,r in enumerate(rr) if gg[i]}))),rank_query_sha=digest("\n".join(sorted(q for i,q in enumerate(order) if rg[i]))),
            graph_model=gm,rank_model=rm)
        assert not {r["t"] for i,r in enumerate(rr) if gg[i] or rg[i]}&{r["t"] for i,r in enumerate(rr) if ff[i]==k}
    for k in range(5):
        use=(ff==k)[qrow];rank=f.lin(cache[k][1],rx[use])
        offsets["full"][use]=frozen_g[use]+rank
        offsets["oof"][use]=f.lin(cache[k][0],gx[use])+rank
        offsets["rotated"][use]=f.lin(cache[(k+1)%5][0],gx[use])+rank
    fp=D/"fold-models.json";save(fp,dict(folds=fold_sign,full_refit_max_abs=[float(grdiff.max()),float(radiff.max())],inventory=sha(D/"train-inventory.json"),features=meta["npz"]))
    original=[q for q in order if R[q]["small"]];expanded=sorted(set(order)-set(original),key=lambda q:(digest("scale-add-v1|"+R[q]["t"]),digest("scale-add-v1|"+q)))
    nested=original+expanded;panels={k:set(nested[:k]) for k in (196,1024,3894)};assert panels[196]==set(original)
    m={};diagnostics={}
    for size,qs in panels.items():
        keep=np.array([q in qs for q in order]);u=keep[qrow];st=np.r_[0,np.cumsum(n[keep])[:-1]]
        diagnostics[size]=dict(trajectories=len({R[q]["t"] for q in qs}),questions=len(qs),labels=int(y[u].sum()),candidates=int(u.sum()),in_full_structural=int((keep&graph).sum()),in_full_rank=int((keep&rfit).sum()),
            oof_vs_full_offset_rms=float(np.sqrt(np.mean((offsets["oof"][u]-offsets["full"][u])**2))),panel_sha=digest("\n".join(sorted(qs))))
        for mode in MODES:m[f"{mode}_{size}"]=correction(z[u],offsets[mode][u],c[u],y[u],st)
        if size==196:
            m["original_recomputed"]=correction(z[u],(frozen_g+frozen_r)[u],c[u],y[u],st)
            orig=load(B/"models.json")["models"]["cost_worst_0.03"];assert np.allclose(m["original_recomputed"]["weights"],orig["weights"],atol=1e-5)
            m["original_R33"]=orig
        print("second stage",size,diagnostics[size]["candidates"],flush=True)
    p=D/"models.json";save(p,dict(models=m,panels=diagnostics,folds=sha(fp),code=sha(Path(__file__)),protocol=sha(D/"PROTOCOL_RU.md"),train=meta["npz"]))
    save(D/"selection.json",dict(models=sha(p),primary=["oof_3894","original_R33"],secondary=["oof_196","oof_1024","rotated_3894","full_3894"],fixed_reg=.03,dev_tuning=False))
def forecast(stage):
    model=load(D/"models.json")["models"];file=b.PRIVATE/(stage+".json.gz");assert sha(file)==load(B/(stage+"-input.json"))["features"]
    out={}
    for r in load(file):
        x=np.array(r["x"]);o=np.array(r["o"]);out[r["q"]]={}
        for k,p in model.items():out[r["q"]][k]=np.argsort(-(o+(x-p["center"])/p["scale"]@p["weights"]),kind="stable").tolist()
    p=D/(stage+"-orders.json.gz");save(p,out);save(D/(stage+"-seal.json"),dict(orders=sha(p),selection=sha(D/"selection.json"),input=sha(file),fit=sha(D/"models.json")))
if __name__=="__main__":
    if sys.argv[1]=="fit":fit()
    else:forecast(sys.argv[1])