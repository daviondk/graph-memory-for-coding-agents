"""Use upstream span scoring after every reader output for all seeds has been frozen."""
import os
for key in ("OMP_NUM_THREADS","OPENBLAS_NUM_THREADS","MKL_NUM_THREADS"):os.environ[key]="1"
from pathlib import Path
import gzip,hashlib,json,sys
from collections import defaultdict
D=Path(__file__).resolve().parent;W=D.parents[1]
sys.path.insert(0,str(W/"graph_memory_round33/budget_loss"))
import data as src
read=src.load

def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def save(p,obj):
    raw=(json.dumps(obj,sort_keys=True,separators=(",",":"))+"\n").encode()
    p.write_bytes(gzip.compress(raw,mtime=0) if p.suffix==".gz" else raw)


def main():
    seeds=(13,17,29,37,41)
    seals={}
    for seed in seeds:
        for sh in range(8):
            key=f"pred-{seed}-{sh}"
            p=D/f"{key}.json.gz"
            j=read(D/f"{key}-seal.json")
            assert digest(p)==j["data"]
            seals[key]=j["data"]
    save(D/"forecast-seal.json",dict(packets=seals,protocol=digest(D/"PROTOCOL_RU.md")))
    prior=read(W/"graph_memory_round22/prefix_read/outcomes.json.gz")
    prior={(r["q"],r["cut"]):r for r in prior}
    atoms=read(W/"graph_memory_round34/interval_witness/test-atoms.json.gz")
    gold=read(src.nm.OFF/"gold-spans.json.gz")
    total=0;checks=0
    for sh,path in enumerate(src.sources("test")):
        records=read(path)
        by_seed={seed:{(q,cut):(t,pilot,arms) for q,t,cut,pilot,arms in read(D/f"pred-{seed}-{sh}.json.gz")} for seed in seeds}
        groups=[]
        for row in records:
            q=row["q"];t=row["t"];nodes=tuple(src.nm.pilot.RankedNodeRecord.model_validate(n) for n in row["rr"])
            valid=tuple(src.nm.pilot.SourceSpan.model_validate(sp) for sp in gold[q])
            atoms_q=[(stop-start,set(ix)) for _,start,stop,ix in atoms[q]]
            full=sum(n for n,_ in atoms_q)
            cached={}
            for cut in (25,50,75,100):
                r=prior[q,cut]
                outcomes={}
                for seed in seeds:
                    traj,pilot,arms=by_seed[seed][q,cut]
                    assert traj==r["t"]==t and pilot==r["pilot"]
                    by_arm={}
                    for k,ids in arms.items():
                        tup=tuple(ids)
                        if tup not in cached:
                            seq=tuple(nodes[i] for i in ids);n_tokens=sum(n.token_count for n in seq)
                            assert n_tokens<=2048
                            m=src.nm.pilot.span_metrics_under_token_budget(seq,valid,2048)
                            s=set(ids);a=sum(n for n,ix in atoms_q if not ix.isdisjoint(s))
                            assert abs(a/full-m.coverage)<1e-12 and int(a==full)==int(m.full_support)
                            cached[tup]=[int(m.full_support),float(m.coverage),n_tokens]
                            checks+=1
                        v=cached[tup]
                        assert v[1]<=r["visible"]+1e-12
                        by_arm[k]=v
                    outcomes[str(seed)]=by_arm
                old=r["arms"]["exact"]
                groups.append(dict(q=q,t=t,cut=cut,pilot=pilot,eligible=r["eligible"],old=[old["fs"],old["coverage"],old["tokens"]],arms=outcomes))
        target=D/f"outcomes-{sh}.json.gz"
        save(target,groups)
        total+=len(groups)
        print("graded",sh,len(groups),checks,flush=True)
    assert total==8000
    save(D/"scoring.json",dict(questions=2000,states=total,official_unique_lists=checks,
            source_seal=digest(D/"forecast-seal.json"),scores={str(i):digest(D/f"outcomes-{i}.json.gz") for i in range(8)}))


if __name__=="__main__":main()

