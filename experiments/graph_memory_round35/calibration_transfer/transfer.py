"""Transfer one frozen four-parameter score correction to four pre-existing E5-FT seeds."""
from pathlib import Path
import sys,hashlib,json
D=Path(__file__).resolve().parent;S=D.parent/"calibration_scale";sys.path.insert(0,str(S))
from prepare_scale import W,B,b,f,np,load,sha,save
from score_scale import native,METRICS
from collections import defaultdict
SEEDS=(17,29,37,41);NAMES=("original_R33","oof_3894")
SOURCE="75c562b1ea3f028731c5e653c20a3698b917fb22f1d0ea15f05fe332fd541cfe"
def check_source():
    assert sha(S/"manifest.json")==SOURCE
    m=load(S/"manifest.json")["files"]
    for path in ("models.json","test-results.json","test-outcomes.json.gz","selection.json"):
        assert m[path]==sha(S/path)
def forecast():
    check_source();m=load(S/"models.json")["models"];fp=b.PRIVATE/"test.json.gz"
    assert sha(fp)==load(B/"test-input.json")["features"];rows={r["q"]:r for r in load(fp)}
    seals={};up={}
    for i in range(8):
        hist=load(B/f"transfer-ranks-{i}.json.gz");out={}
        for seed in SEEDS:
            sd=W/f"graph_memory_round21/five_seed/seed-{seed}";source=sd/f"picks-{i}.json.gz";receipt=load(sd/"forecast-seal.json")
            key=str(seed);rankpath=sd/"calibration.json";assert sha(rankpath)==receipt["rank_weights"] and sha(source)==next(v["sha"] for v in receipt["receipts"] if v["file"]==source.name)
            upstream_seed=up.setdefault(key,{})
            upstream_seed[rankpath.name]=sha(rankpath);upstream_seed[source.name]=sha(source);rank=load(rankpath)["rank"]
            for rec in load(source):
                q=rec["q"];raw=rows[q];dx=np.asarray(rec["dense"]);n=len(dx);assert sorted(dx.tolist())==list(range(n))
                z=np.asarray(raw["x"])[dx];z[:,0]=np.log1p(np.arange(1,n+1));rx=f.rank_x(n)
                off=(np.asarray(raw["o"])-f.lin(b.RANK,rx))[dx]+f.lin(rank,rx);arms={}
                for name in NAMES:
                    v=m[name];s=off+(z-v["center"])/v["scale"]@v["weights"];arms[name]=dx[np.argsort(-s,kind="stable")].tolist()
                assert arms["original_R33"]==hist[q][key]["cost_worst_0.03"]
                out.setdefault(q,{})[key]=arms
        p=D/f"orders-{i}.json.gz";save(p,out);seals[p.name]=sha(p)
    save(D/"forecast-seal.json",dict(orders=seals,source_manifest=SOURCE,seeds=SEEDS,arms=NAMES,parents=up,protocol=sha(D/"PROTOCOL_RU.md"),code=sha(Path(__file__))))
def measure():
    check_source();seal=load(D/"forecast-seal.json");assert seal["source_manifest"]==SOURCE and seal["code"]==sha(Path(__file__));refs=load(b.nm.OFF/"gold-spans.json.gz");baseline_13=load(S/"test-outcomes.json.gz")
    out={};checks=0
    for i,path in enumerate(b.sources("test")):
        rp=D/f"orders-{i}.json.gz";assert sha(rp)==seal["orders"][rp.name];orders=load(rp)
        auc=load(W/f"graph_memory_round34/strong_reader_controls/auc-outcomes-{i}.json.gz")
        history=load(B/f"transfer-outcomes-{i}.json.gz")
        for rec in load(path):
            q=rec["q"];t=rec["t"];assert baseline_13[q]["t"]==t
            nd=tuple(b.nm.pilot.RankedNodeRecord.model_validate(v) for v in rec["rr"]);g=tuple(b.nm.pilot.SourceSpan.model_validate(v) for v in refs[q]);memo={}
            seeds={"13":{n:baseline_13[q]["arms"][n] for n in NAMES}}
            for seed in SEEDS:
                key=str(seed);arms={}
                for name,order in orders[q][key].items():
                    k=tuple(order)
                    if k not in memo:memo[k]=native(nd,g,k);checks+=1
                    arms[name]=memo[k]
                orig=arms["original_R33"];arch=history[q]["seeds"][key]["cost_worst_0.03"]
                assert np.allclose(orig, [arch[0],*auc[q]["seeds"][key]["cost"][:2],arch[5],arch[3]],atol=1e-12)
                seeds[key]=arms
            assert q not in out;out[q]=dict(t=t,seeds=seeds)
    pp=D/"outcomes.json.gz";save(pp,out);save(D/"measure-seal.json",dict(rows=len(out),unique_orders=checks,outcomes=sha(pp),forecasts=sha(D/"forecast-seal.json")))
def compare():
    pp=D/"outcomes.json.gz";assert sha(pp)==load(D/"measure-seal.json")["outcomes"];out=load(pp)
    seeds=[13,*SEEDS];q=sorted(out);ts=sorted({out[k]["t"] for k in q});index={t:i for i,t in enumerate(ts)};ids=np.asarray([index[out[k]["t"]] for k in q]);cnt=np.bincount(ids);assert len(q)==2000 and len(ts)==1207
    mats={n:np.array([[out[k]["seeds"][str(s)][n] for s in seeds] for k in q]) for n in NAMES};d=mats[NAMES[1]]-mats[NAMES[0]]
    cluster=np.zeros((len(ts),len(seeds),len(METRICS)));np.add.at(cluster,ids,d);report={}
    for tag,ix in [*((str(s),[k]) for k,s in enumerate(seeds)),("transfer4",[1,2,3,4]),("all5",list(range(5)))]:
        n=len(ix);part=cluster[:,ix];means={name:v[:,ix].mean(axis=(0,1)).tolist() for name,v in mats.items()};series=d[:,ix].mean(axis=1)
        fixed=[];cross=[];rng=np.random.default_rng(35513)
        for _ in range(100):
            res=rng.integers(len(ts),size=(100,len(ts)));counts=np.stack([np.bincount(z,minlength=len(ts)) for z in res])
            val=(counts@part.reshape(len(ts),-1)).reshape(100,n,len(METRICS))/(counts@cnt)[:,None,None]
            fixed.append(val.mean(1));si=rng.integers(n,size=(100,n));cross.append(val[np.arange(100)[:,None],si].mean(1))
        lower=lambda arr:(100*np.quantile(np.concatenate(arr),[.025,.975],axis=0)).tolist()
        report[tag]=dict(means=means,delta_pp=(100*series.mean(0)).tolist(),ci95_fixed=lower(fixed),ci95_crossed=lower(cross),
            win_question=(series>1e-12).sum(0).tolist(),loss_question=(series< -1e-12).sum(0).tolist(),win_query_seed=(d[:,ix]>1e-12).sum(axis=(0,1)).tolist(),loss_query_seed=(d[:,ix]<-1e-12).sum(axis=(0,1)).tolist())
    save(D/"results.json",dict(n=len(q),t=len(ts),metrics=METRICS,groups=report,observations=sha(pp),measure=sha(D/"measure-seal.json"),primary="transfer4",protocol=sha(D/"PROTOCOL_RU.md")))
    print({k:(round(v["means"]["oof_3894"][0]*100,3),[round(x,3) for x in v["delta_pp"]]) for k,v in report.items()})
if __name__=="__main__":
    if sys.argv[1]=="run":forecast();measure();compare()
    else:{"forecast":forecast,"measure":measure,"compare":compare}[sys.argv[1]]()