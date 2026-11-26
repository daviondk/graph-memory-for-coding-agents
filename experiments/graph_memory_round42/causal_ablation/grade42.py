"""Score only after all packets have been frozen."""
from collections import Counter
import os,sys
for k in ("OPENBLAS_NUM_THREADS","MKL_NUM_THREADS","OMP_NUM_THREADS"):os.environ[k]="1"
from core42 import D,W,R41,SEEDS,read,signed,save,sha
sys.path.insert(0,str(W/"graph_memory_round33/budget_loss"))
import data as src


def main():
    seal=read(D/"forecast-seal.json")
    assert seal["questions"]==2000 and seal["models"]==sha(D/"models.json")
    previous={r["q"]:r for r in signed(R41,"outcomes.json.gz")}
    gold=read(src.nm.OFF/"gold-spans.json.gz")
    atoms=read(W/"graph_memory_round34/interval_witness/test-atoms.json.gz")
    checks=0;records=[]
    for sh,path in enumerate(src.sources("test")):
        fp=D/f"packets-{sh}.json.gz";assert sha(fp)==seal["packets"][str(sh)]
        packets=read(fp)
        for raw in read(path):
            q,t=raw["q"],raw["t"];old=previous[q]
            trajectory,by_seed=packets[q];assert trajectory==t==old["t"]
            valid=tuple(src.nm.pilot.SourceSpan.model_validate(sp) for sp in gold[q])
            candidates=tuple(src.nm.pilot.RankedNodeRecord.model_validate(n) for n in raw["rr"])
            partition=[(b-a,set(v)) for _,a,b,v in atoms[q]];size=sum(w for w,_ in partition)
            cache={};out={}
            for s in SEEDS:
                row={}
                for name,ids in by_seed[str(s)].items():
                    key=tuple(ids)
                    if key not in cache:
                        seq=tuple(candidates[i] for i in ids);cost=sum(z.token_count for z in seq)
                        assert cost<=2048 and len(set(ids))==len(ids)
                        measure=src.nm.pilot.span_metrics_under_token_budget(seq,valid,2048)
                        picked=set(ids);covered=sum(w for w,n in partition if not picked.isdisjoint(n))
                        assert abs(covered/size-measure.coverage)<1e-12 and (covered==size)==bool(measure.full_support)
                        cache[key]=[int(measure.full_support),float(measure.coverage),cost]
                    row[name]=cache[key]
                prior=old["arms"][str(s)]
                assert row["R35"]==prior["graph_firstfit"] and row["dense"]==prior["dense_firstfit"]
                row["native_wo"]=prior["wo_chunk_adjacency/firstfit"]
                row["native_full"]=prior["full_rgcn/firstfit"]
                out[str(s)]=row
            records.append(dict(q=q,t=t,pilot=old["pilot"],eligible=old["eligible"],arms=out));checks+=len(cache)
        print("graded",sh,checks,flush=True)
    assert len(records)==2000
    p=D/"scores.json.gz";save(p,records)
    save(D/"grade-seal.json",dict(scores=sha(p),registration=sha(D/"forecast-seal.json"),checks=checks,
        native=sha(R41/"outcomes.json.gz"),atoms=sha(W/"graph_memory_round34/interval_witness/test-atoms.json.gz"),
        gold=sha(src.nm.OFF/"gold-spans.json.gz"),code=sha(D/"grade42.py")))


if __name__=="__main__":main()
