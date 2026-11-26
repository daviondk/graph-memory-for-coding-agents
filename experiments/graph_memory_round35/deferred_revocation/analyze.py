from replay import *
def precision():
    cert=read(D/"forecast-seal.json");assert cert["plan"]==sha(D/"source-lock.json")
    prev={(r["q"],r["cut"]):r for r in read(R34/"outcomes.json.gz")};refs=read(l.ref.OFF/"gold-spans.json.gz")
    out=[];traj={};verify=0
    for i in range(8):
        op=D/f"operations-{i}.json.gz";rk=D/f"orders-{i}.json.gz";assert sha(op)==cert["files"][op.name] and sha(rk)==cert["files"][rk.name]
        ops=read(op);assert not set(traj)&set(ops);traj.update(ops)
        base={r["q"]:tuple(l.RankedNodeRecord.model_validate(v) for v in r["rr"]) for r in read(l.ref.TR/f"forecasts-main-{i}.json.gz")}
        for q,t,cut,orders in read(rk):
            h=prev[q,cut];assert h["t"]==t;arms={};diff={};g=tuple(l.SourceSpan.model_validate(s) for s in refs[q]);memo={}
            for name,tri in orders.items():
                ix=tuple(tri[2]);assert len(ix)==len(set(ix))
                if ix not in memo:
                    nd=tuple(base[q][j] for j in ix);used=sum(n.token_count for n in nd);assert used<=2048
                    s=l.span_metrics_under_token_budget(nd,g,2048);memo[ix]=[int(s.full_support),s.coverage,used]
                arms[name]=memo[ix];diff[name]=[ix!=tuple(orders["exact"][2]),set(ix)!=set(orders["exact"][2])]
            for tag in ("exact","append"):
                expect=h["arms"][tag];assert arms[tag]==[expect[0],expect[1],expect[4]];verify+=1
            assert arms["lazy_read"]==arms["exact"];out.append(dict(t=t,q=q,cut=cut,eligible=h["eligible"],pilot=h["pilot"],arms=arms,diff=diff))
    assert len(traj)==1207 and len(out)==8000 and len({r["q"] for r in out})==2000 and verify==16000
    pp=D/"outcomes.json.gz";put(pp,out)
    rng=np.random.default_rng(35591);panels={}
    for cut in CUTS:
        for condition in ("eligible","all_nonpilot","all2000"):
            group=[r for r in out if r["cut"]==cut and (condition=="all2000" or not r["pilot"]) and (condition!="eligible" or r["eligible"])]
            ts=sorted({r["t"] for r in group});kt={t:j for j,t in enumerate(ts)};ix=np.array([kt[r["t"]] for r in group]);sz=np.bincount(ix)
            arr=np.array([[r["arms"][name][:2] for name in MODES] for r in group]);delta=arr-arr[:,0:1];acc=np.zeros((len(ts),len(MODES),2));np.add.at(acc,ix,delta);boot=[]
            for _ in range(100):
                take=rng.integers(len(ts),size=(100,len(ts)));counts=np.stack([np.bincount(a,minlength=len(ts)) for a in take])
                v=(counts@acc.reshape(len(ts),-1)).reshape(100,len(MODES),2)/(counts@sz)[:,None,None];boot.append(v)
            ci=100*np.quantile(np.concatenate(boot),[.025,.975],axis=0);info={}
            for a,tag in enumerate(MODES):
                info[tag]=dict(success=int(arr[:,a,0].sum()),means=arr[:,a].mean(0).tolist(),delta_pp=(100*delta[:,a].mean(0)).tolist(),
                    ci95_pp=ci[:, :, :][:,a].tolist(),better=(delta[:,a]>1e-12).sum(0).tolist(),worse=(delta[:,a]<-1e-12).sum(0).tolist(),
                    changed2048=sum(r["diff"][tag][0] for r in group),changed_membership=sum(r["diff"][tag][1] for r in group),
                    affected_graph=sum(traj[r["t"]]["cuts"][str(cut)]["pending"][tag]>0 for r in group))
            panels[str(cut)+"."+condition]=dict(n=len(group),t=len(ts),methods=info)
    assert panels["50.eligible"]["n"]==901 and panels["50.all_nonpilot"]["n"]==1845
    persons=sorted(traj);keys=("batches","removed","inserts","queued","reactivated","peak","pending_final","drained_batches","drained_removed")
    arr=np.array([[[traj[t]["states"][a][k] for k in keys] for a in MODES] for t in persons]);total=arr.sum(0);peak=arr.max(0)
    bindex=keys.index("batches");di=keys.index("drained_batches");db=[]
    # Paired bootstraps of aggregate ratios, and differences per trajectory for raw and debt-neutralized metrics.
    for _ in range(100):
        take=rng.integers(len(persons),size=(100,len(persons)));counts=np.stack([np.bincount(z,minlength=len(persons)) for z in take])
        raw=(counts@arr.reshape(len(persons),-1)).reshape(100,len(MODES),len(keys))
        ratio=raw[:,:,[bindex,di]]/raw[:,[0],:][:,:,[bindex,di]];diff=(raw-raw[:,0:1])/len(persons)
        db.append(np.concatenate([ratio,diff],axis=2))
    cis=np.quantile(np.concatenate(db),[.025,.975],axis=0);stats={}
    for j,name in enumerate(MODES):
        a=arr[:,j];stats[name]=dict(total=dict(zip(keys,total[j].tolist())),largest_pending=int(peak[j,keys.index("peak")]),
            pending_peak_p50_p95_p99=np.quantile(a[:,keys.index("peak")],[.5,.95,.99]).tolist(),
            traces_with_pending_before_terminal=int((a[:,keys.index("pending_final")]>0).sum()),
            traces_with_any_batch=int((a[:,bindex]>0).sum()),batch_ratio=float(total[j,bindex]/total[0,bindex]),drained_batch_ratio=float(total[j,di]/total[0,di]),
            batch_ratio_CI=cis[:,j,0].tolist(),drained_batch_ratio_CI=cis[:,j,1].tolist(),
            per_trace_diff_CI={k:cis[:,j,2+h].tolist() for h,k in enumerate(keys)})
    op=dict(trajectories=len(persons),groups=sum(r["groups"] for r in traj.values()),distinct_read_states=sum(len({z["step"] for z in r["cuts"].values()}) for r in traj.values()),
        events_with_support_delta=sum(bool(up or down) for r in traj.values() for _,_,_,up,down in r["log"]),metrics=stats)
    put(D/"results.json",dict(operations=op,panels=panels,paired_control_rows=verify,outcomes=sha(pp),seal=sha(D/"forecast-seal.json")))
    print("half",[(k,v["success"]) for k,v in panels["50.eligible"]["methods"].items()],"batches",[(k,v["total"]["batches"]) for k,v in stats.items()])
if __name__=="__main__":precision()