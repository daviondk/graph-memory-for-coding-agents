"""Run the unchanged before/after-anchor experiment on the final previously unused-for-this-policy C traces."""
import sys,gzip
from pathlib import Path
from collections import Counter,defaultdict
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime,timezone
import run_anchor as e
from run_anchor import HERE,D,read,save,sha,rows,write,paired

def run(task):
    mode,k=task
    e.B=D
    return e.predict(("C",k)) if mode=="predict" else e.grade(("C",k))
def main():
    mode=sys.argv[1];dst=HERE/"C";dst.mkdir(exist_ok=True)
    if mode=="predict":
        assert not (dst/"checkpoint_lock.json").exists()
        files=[HERE/"run_anchor.py",HERE/"PROTOCOL_RU.md",HERE/"C_PROTOCOL.md",HERE/"holdout_anchor.py",HERE/"method_lock.json",HERE/"results.json",HERE/"independent_targets.json",
               D/"experiment.py",D/"shared.py",D/"selection_receipt.json",D/"freeze.json",*sorted(D.glob("source_*.jsonl.gz"))]
        save(dst/"method_lock.json",dict(utc=datetime.now(timezone.utc).isoformat(),files={str(p):sha(p) for p in files}))
        with ProcessPoolExecutor(3) as pool:parts=list(pool.map(run,[("predict",k) for k in range(8)]))
        save(dst/"transports.json",dict(sum((Counter(p) for p in parts),Counter())))
        save(dst/"checkpoint_lock.json",{p.name:sha(p) for p in dst.glob("*.gz")})
    else:
        assert all(sha(Path(n))==h for n,h in read(dst/"method_lock.json")["files"].items())
        assert all(sha(dst/n)==h for n,h in read(dst/"checkpoint_lock.json").items())
        with ProcessPoolExecutor(3) as pool:parts=list(pool.map(run,[("grade",k) for k in range(8)]))
        rr=[r for section,au in parts for r in section];audit=sum((au for sec,au in parts),Counter());checks=defaultdict(list)
        with gzip.open(dst/"scored.jsonl.gz","wt",encoding="utf8") as out:
            for r in rr:write(out,r)
        for path in sorted(dst.glob("verifications_*.gz")):
            for size,*r in rows(path):checks[size].append(r)
        result=dict(n=len(rr),issues=len({r[0] for r in rr}),audit=audit,full={a:sum(r[-1][a][0] for r in rr) for a in e.ARMS},
                    contrasts={s:paired(rr,s+"_anchor",s+"_original") for s in ("flat","cap")},
                    validation={s:dict(n=len(li),equal=sum(r[5] for r in li),conflicts=sum(not r[5] for r in li),issues=len({r[0] for r in li})) for s,li in checks.items()})
        save(dst/"results.json",result);print(result["n"],result["full"],result["audit"],result["validation"])
if __name__=="__main__":main()
