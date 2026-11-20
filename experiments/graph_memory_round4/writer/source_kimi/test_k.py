"""Transfer both frozen policies to a different public SWE-agent submission with no outcome-based fitting."""
from pathlib import Path
import sys,gzip,time
from collections import Counter,defaultdict
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime,timezone
HERE=Path(__file__).resolve().parent;sys.path.insert(0,str(HERE.parent/"anchor"))
import run_anchor as anchor
from run_anchor import D,A,B,read,save,sha,rows,write,core,paired
WRITERS=["lru","point","typed","mixed","dict_lru","dict_mixed","cal_pages","cal_neighbor"]
def run(job):
    op,kind,k=job
    if kind=="anchor":
        anchor.B=HERE;anchor.HERE=HERE
        return anchor.predict(("anchor",k)) if op=="predict" else anchor.grade(("anchor",k))
    core.config=lambda unused:(HERE,HERE/"writer")
    return core.predict(("K",k,WRITERS)) if op=="predict" else core.evaluate_shard(("K",k,WRITERS))
def main():
    mode=sys.argv[1]
    jobs=[(mode,kind,k) for kind in ("writer","anchor") for k in range(8)]
    if mode=="predict":
        assert not (HERE/"checkpoint_lock.json").exists()
        for n in ("writer","anchor"):(HERE/n).mkdir(exist_ok=True)
        inputs=[HERE/n for n in ("PROTOCOL_RU.md","acquire_k.py","test_k.py","selection.json","receipts.json")]
        inputs += [D/"anchor/run_anchor.py",D/"anchor/C/method_lock.json",D/"freeze.json",D/"risk_model.json",D/"python_prior.bin",D/"experiment.py",D/"memory.py",A/"acquire.py",*sorted(HERE.glob("source_*.jsonl.gz"))]
        save(HERE/"method_lock.json",dict(utc=datetime.now(timezone.utc).isoformat(),inputs={str(p):sha(p) for p in inputs},writers=WRITERS))
        with ProcessPoolExecutor(4) as pool:out=list(pool.map(run,jobs))
        save(HERE/"timing_and_transports.json",out)
        save(HERE/"checkpoint_lock.json",{str(p.relative_to(HERE)):sha(p) for n in ("writer","anchor") for p in (HERE/n).glob("*.gz")})
    else:
        assert all(sha(Path(n))==v for n,v in read(HERE/"method_lock.json")["inputs"].items())
        assert all(sha(HERE/n)==v for n,v in read(HERE/"checkpoint_lock.json").items())
        with ProcessPoolExecutor(4) as pool:parts=list(pool.map(run,jobs))
        out={}
        for name in ("writer","anchor"):
            subsection=[parts[j] for j,(_,kind,_) in enumerate(jobs) if kind==name]
            r=[rec for ss in subsection for rec in ss[0]]
            with gzip.open(HERE/name/"scored.jsonl.gz","wt",encoding="utf8") as f:
                for rec in r:write(f,rec)
            if not r:out[name]=dict(n=0);continue
            arms=list(r[0][-1]);vs=([("cal_neighbor",a) for a in WRITERS if a!="cal_neighbor"] if name=="writer" else [(s+"_anchor",s+"_original") for s in ("cap","flat")])
            out[name]=dict(n=len(r),issues=len(set(z[0] for z in r)),repos=sorted(set(z[1] for z in r)),arms={a:dict(full=sum(z[-1][a][0] for z in r),fraction=sum(z[-1][a][1] for z in r)/len(r),start=sum(z[-1][a][2] for z in r)) for a in arms},
                pairs={f"{new}-{old}":paired(r,new,old) for new,old in vs},locations=Counter(z[4] for z in r),
                audit=sum((s[-1] for s in subsection),Counter()))
            if name=="anchor":
                per=defaultdict(list)
                for pf in sorted((HERE/name).glob("verifications*.gz")):
                    for typ,*rr in rows(pf):per[typ].append(rr)
                out[name]["line_validation"]={s:dict(n=len(li),right=sum(x[5] for x in li),issues=len(set(x[0] for x in li))) for s,li in per.items()}
        save(HERE/"results.json",out)
        print({k:(v["n"],{a:p["full"] for a,p in v.get("arms",{}).items()}) for k,v in out.items()})
if __name__=="__main__":main()
