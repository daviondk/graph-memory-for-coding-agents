"""Apply the already sealed original scoring rules to strict unseen Java repositories, without target columns."""
from experiment import *
from data_io import panel_name
from native_run import load_module
def extract_strict(p):
    load_module("common","publisher_common.py");load_module("arms","publisher_arms.py");pub=load_module("repobench","publisher_repobench.py")
    selected=dict(read("strict_roster.json").get(p.stem,[]))
    meta=[];xx={3:[],10:[]};off=[0]
    for j,row in enumerate(rows(p,["code","context","repo_name"])):
        if j not in selected:continue
        ctx=row["context"];n=len(ctx);state=encode(ctx);code=row["code"];hs=hashstr(code)
        base={};shift=1+int(hashstr(f"shift|{code.splitlines()[-3:]}")[:10],16)%max(1,n-1)
        for k in (3,10):
            z=features(code,state,k);xx[k].append(np.column_stack([z,np.roll(z[:,OWNER:],shift,axis=0)]))
            base[k]=pub.bm25_rank(pub.crop(code,k),ctx)
        off.append(off[-1]+n);meta.append([panel_name(p.stem),selected[j],row["repo_name"],[nt(s) for s in ctx],hs,base])
    return meta,np.concatenate(xx[3]),np.concatenate(xx[10]),np.array(off)
def main():
    assert read("fit.json")["sha256"]==sha(D/"models.pkl")
    with (D/"models.pkl").open("rb") as f:m=pickle.load(f)
    cache=D/"strict_cache";cache.mkdir(exist_ok=True)
    paths=files("java","test");dest=D/"strict_java.pred.jsonl.gz"
    with ProcessPoolExecutor(3) as pool,gzip.open(dest,"wt",encoding="utf8") as out:
        for p,(meta,f3,f10,off) in zip(paths,pool.map(extract_strict,paths)):
            (cache/(p.stem+".json")).write_text(json.dumps(meta),encoding="utf8")
            np.savez_compressed(cache/(p.stem+".npz"),f3=f3,f10=f10,offset=off)
            for k,f in [(3,f3),(10,f10)]:
                pr={a:m[k,a].predict_proba(f[:,ARMS[a]])[:,1] for a in ARMS}
                for rec,lo,hi in zip(meta,off,off[1:]):
                    panel,i,repo,sz,h,bm=rec
                    ranks={a:np.argsort(-s[lo:hi],kind="stable").tolist() for a,s in pr.items()};ranks["publisher_bm25"]=bm[k]
                    n=int((f[lo:hi,OWNER]>0).sum())
                    out.write(json.dumps([panel,i,k,repo,sz,h,n,ranks],separators=(",",":"))+"\n")
    write("strict_graph_lock.json",{"utc":datetime.now(timezone.utc).isoformat(),"sha256":sha(dest),"models_sha256":sha(D/"models.pkl")})
if __name__=="__main__":main()
