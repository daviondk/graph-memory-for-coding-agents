"""Use a single independent inverted gold to test a 2 by 2 of sealed eviction and rebasing components."""
import sys,gzip,hashlib,time
from collections import Counter
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor
from run_anchor import HERE,D,rows,save,sha,read,write,prior,core,invert,BASE_ADVANCE,anchored_advance,future_check,success,rel,paired
from memory import transition,initial,unpack,pack
PANELS={"C":D,"Kimi":D/"source_kimi"}
def shard(job):
    panel,k,phase=job;source=PANELS[panel];dest=HERE/"factorial"/panel
    if phase=="predict":
        w=core.weights();steps=0
        with gzip.open(dest/f"cuts_{k}.gz","wt",encoding="utf8",compresslevel=2) as fp:
            for task in rows(source/f"source_{k}.jsonl.gz"):
                states={a:initial("cal_neighbor") for a in ("cal_original","cal_anchor")};iid=task["instance"]
                static=dict(instance=iid,issue=task["issue"])
                for t,event in enumerate(task["events"],1):
                    rec={}
                    for a,old in states.items():
                        prior.advance=anchored_advance if a=="cal_anchor" else BASE_ADVANCE
                        try:states[a],_=transition("cal_neighbor",old,event,static,w,4096)
                        finally:prior.advance=BASE_ADVANCE
                        assert len(states[a])<=4096;steps+=1
                        if t%4==0 and t<len(task["events"]):
                            x=unpack(states[a],True);assert pack(x,True)==states[a];rec[a]=x
                    if rec:write(fp,[iid,t,rec])
        return steps
    out=[];cuts=iter(rows(dest/f"cuts_{k}.gz"))
    for task in rows(source/f"source_{k}.jsonl.gz"):
        iid=task["instance"];ev=task["events"]
        for t in range(4,len(ev),4):
            i,j,states=next(cuts);assert (i,j)==(iid,t)
            args,obs=future_check(ev,t)
            if not args or not success(args.get("command"),rel(args.get("path")),obs):continue
            gt=invert(args,obs)
            if not gt:continue
            lo,lines=gt;p=rel(args["path"]);scores={}
            for a,x in states.items():
                mem=prior.materialize(x)[1]["rebase"].get(p,{})
                ok=[mem.get(lo+i,[None])[0]==s for i,s in enumerate(lines)]
                scores[a]=[int(all(ok)),sum(ok)/len(ok),int(ok[0])]
            out.append([iid,task["official_repo"],t,len(lines),"inverted",scores])
    assert next(cuts,None) is None
    return out
def main():
    base=HERE/"factorial";which=sys.argv[1]
    for n in PANELS:(base/n).mkdir(parents=True,exist_ok=True)
    jobs=[(n,k,which) for n in PANELS for k in range(8)]
    if which=="predict":
        assert not (base/"checkpoint_lock.json").exists()
        inputs=[HERE/"FACTORIAL.md",HERE/"factorial.py",HERE/"run_anchor.py",D/"freeze.json",HERE/"C/method_lock.json",D/"source_kimi/method_lock.json"]
        save(base/"method_lock.json",{str(p):sha(p) for p in inputs})
        with ProcessPoolExecutor(3) as pool:v=list(pool.map(shard,jobs))
        save(base/"byte_checks.json",{n:sum(x for x,j in zip(v,jobs) if j[0]==n) for n in PANELS})
        save(base/"checkpoint_lock.json",{str(p.relative_to(base)):sha(p) for n in PANELS for p in (base/n).glob("*.gz")})
    else:
        assert all(sha(base/k)==v for k,v in read(base/"checkpoint_lock.json").items())
        with ProcessPoolExecutor(3) as pool:data=list(pool.map(shard,jobs))
        out={}
        for panel in PANELS:
            archive=(HERE/"C" if panel=="C" else D/"source_kimi/anchor")/"scored.jsonl.gz"
            r=[q for section,j in zip(data,jobs) if j[0]==panel for q in section]
            for a,b in zip(rows(archive),r,strict=True):
                assert a[:5]==b[:5];b[-1].update({k:a[-1][k] for k in ("cap_original","cap_anchor")})
            with gzip.open(base/panel/"scored.jsonl.gz","wt",encoding="utf8") as fp:
                for rec in r:write(fp,rec)
            counts={a:sum(q[-1][a][0] for q in r) for a in r[0][-1]}
            # Difference of differences is descriptive; exact paired intervals are reported for each contrast.
            out[panel]=dict(n=len(r),counts=counts,interaction_hits=(counts["cal_anchor"]-counts["cal_original"])-(counts["cap_anchor"]-counts["cap_original"]),
                pairs={f"{a}-{b}":paired(r,a,b) for a,b in [("cal_anchor","cap_original"),("cal_original","cap_original"),("cal_anchor","cal_original"),("cal_anchor","cap_anchor")]})
        save(base/"results.json",out);print({k:v["counts"] for k,v in out.items()})
if __name__=="__main__":main()
