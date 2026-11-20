"""Secondary matched-reward ablations using the already sealed conditional start model and identical width weights."""
import gzip,json,hashlib,sys,importlib.util
from collections import Counter,defaultdict
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor
import numpy as np

from shared import D,A,B,read,save,sha,write,rows,prior
import memory
from risk import features,collect,calibration

sp=importlib.util.spec_from_file_location("primary_round4",D/"experiment.py")
core=importlib.util.module_from_spec(sp);sp.loader.exec_module(core)
METHODS=["cal_add","cal_first"]
for arm in METHODS: memory.METHODS[arm]=("cal",True,None)

def ranking(pages,meta,last,issue,reward):
    z=features(pages,meta,last,issue)@memory.BETA;p=np.exp(z-z.max())
    if reward=="cal_first":values=p
    else:
        values=np.zeros(len(p));links={(q,a):i for i,(q,a,b,age,s) in enumerate(pages)}
        for i in range(len(pages)):
            group=[i]
            for k,w in enumerate(memory.WIDTH):
                if k:
                    q,a,b,age,s=pages[group[-1]]
                    next_=links.get((q,b+1))
                    if next_ is None:break
                    group.append(next_)
                for j in group:values[j]+=p[i]*w/len(group)
    rank={v:k for k,v in enumerate(prior.order(pages,meta))}
    costs=[len((f"@@ {q} {a}..{b} @@\n{s}\n").encode("utf8")) for q,a,b,age,s in pages]
    return sorted(range(len(pages)),key=lambda j:(values[j]/costs[j],-rank[j],j))

def policy(method,*args):
    base=memory.calibrated_order
    memory.calibrated_order=lambda *aa:ranking(*aa,method)
    try:return memory.transition(method,*args)
    finally:memory.calibrated_order=base

def where(panel):
    return {"A":A,"B":B,"C":D}[panel],D/("ablation_"+panel)
def worker(job):
    phase,panel,k=job
    core.config=where;core.transition=policy
    if phase=="predict":return core.predict((panel,k,METHODS))
    return core.evaluate_shard((panel,k,METHODS))

def main():
    todo=[(p,k) for p in ("A","B","C") for k in range(8)]
    for p in ("A","B","C"):where(p)[1].mkdir(exist_ok=True)
    assert not (D/"ablation_lock.json").exists()
    save(D/"ablation_method_lock.json",{str(p):sha(p) for p in [D/"ABLATION_PROTOCOL.md",D/"ablations.py",D/"freeze.json"]})
    with ProcessPoolExecutor(3) as pool:
        times=list(pool.map(worker,[("predict",*v) for v in todo]))
    save(D/"ablation_times.json",times)
    save(D/"ablation_lock.json",{str(path.relative_to(D)):sha(path) for p in ("A","B","C") for path in where(p)[1].glob("*.gz")})
    with ProcessPoolExecutor(3) as pool:raw=list(pool.map(worker,[("grade",*v) for v in todo]))
    out={}
    for p in ("A","B","C"):
        score=[r for z,(panel,k) in zip(raw,todo) if p==panel for r in z[0]]
        old=rows((D/("panel_"+p))/"scored.jsonl.gz")
        for nref,candidate in zip(old,score,strict=True):
            assert nref[:5]==candidate[:5]
            candidate[-1]["cal_pages"]=nref[-1]["cal_pages"]
        with gzip.open(where(p)[1]/"scored.jsonl.gz","wt",encoding="utf8") as f:
            for r in score:write(f,r)
        out[p]={"arms":{m:np.sum([r[-1][m] for r in score],axis=0).tolist() for m in [*METHODS,"cal_pages"]},
                "group_vs":{a:core.paired(score,"cal_pages",a) for a in METHODS}}
    save(D/"ablation_results.json",out)
    examples,_=collect(D);save(D/"calibration_C.json",calibration(examples,memory.BETA))
    print({p:{k:v[0] for k,v in q["arms"].items()} for p,q in out.items()})
if __name__=="__main__":main()
