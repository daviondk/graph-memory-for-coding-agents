"""Independent visibility and official span scoring after the whole forecast is immutable."""
import os,sys
for k in ("OPENBLAS_NUM_THREADS","MKL_NUM_THREADS","OMP_NUM_THREADS"):os.environ[k]="1"
from io43 import D,W,SEEDS,ARMS,read,save,sha
sys.path.insert(0,str(W/"graph_memory_round33/budget_loss"))
import data as src


def main():
    forecast=read(D/"forecast-seal.json")
    assert forecast["counts"]["questions"]==2000
    gold=read(src.nm.OFF/"gold-spans.json.gz")
    atoms_path=W/"graph_memory_round34/interval_witness/test-atoms.json.gz"
    atoms=read(atoms_path)
    oldplan=W/"graph_memory_round22/prefix_read/forecast-plan.json";pilots=set(read(oldplan)["pilots"])
    rows=[];checks=0;visible_checks=0
    for sh,path in enumerate(src.sources("test")):
        p=D/f"packets-{sh}.json.gz";assert sha(p)==forecast["outputs"][str(sh)][0]
        data=read(p)
        for item in read(path):
            q,t=item["q"],item["t"]
            tt,fired,visible,packets=data[q]
            assert tt==t
            if not fired:
                assert visible==[] and packets=={}
                rows.append(dict(q=q,t=t,fired=False,pilot=t in pilots,eligible=False,visibility=0,arms={}))
                continue
            nodes=tuple(src.nm.pilot.RankedNodeRecord.model_validate(v) for v in item["rr"])
            ref=tuple(src.nm.pilot.SourceSpan.model_validate(v) for v in gold[q])
            partition=[(b-a,set(ids)) for _,a,b,ids in atoms[q]];total=sum(w for w,_ in partition)
            available=set(visible)
            def exact(ids):
                return sum(w for w,choices in partition if not ids.isdisjoint(choices))
            all_nodes=tuple(nodes[i] for i in visible)
            all_cost=sum(v.token_count for v in all_nodes)
            coverage=src.nm.pilot.span_metrics_under_token_budget(all_nodes,ref,max(all_cost,1))
            maximum=exact(available)
            assert abs(maximum/total-coverage.coverage)<1e-12 and (maximum==total)==bool(coverage.full_support)
            visible_checks+=1
            cache={};obs={}
            for s in SEEDS:
                rr={}
                for arm in ARMS:
                    ids=packets[str(s)][arm];key=tuple(ids)
                    if key not in cache:
                        selected=set(ids)
                        assert len(selected)==len(ids) and selected<=available
                        seq=tuple(nodes[i] for i in ids);cost=sum(v.token_count for v in seq)
                        assert cost<=2048
                        result=src.nm.pilot.span_metrics_under_token_budget(seq,ref,2048)
                        mass=exact(selected)
                        assert mass<=maximum and abs(mass/total-result.coverage)<1e-12 and (mass==total)==bool(result.full_support)
                        cache[key]=[int(result.full_support),float(result.coverage),cost]
                    rr[arm]=cache[key]
                obs[str(s)]=rr
            checks+=len(cache)
            rows.append(dict(q=q,t=t,fired=True,pilot=t in pilots,eligible=maximum==total,visibility=maximum/total,arms=obs))
        print("graded",sh,len(rows),flush=True)
    assert len(rows)==len({r["q"] for r in rows})==2000
    dst=D/"outcomes.json.gz";save(dst,rows)
    save(D/"scoring.json",dict(rows=2000,forecasts=sha(D/"forecast-seal.json"),outcomes=sha(dst),
        visibility_checks=visible_checks,author_lists_checked=checks,atoms=sha(atoms_path),
        gold=sha(src.nm.OFF/"gold-spans.json.gz"),pilot=sha(oldplan),grader=sha(D/"grade43.py")))
    print("official intervals",checks,visible_checks,flush=True)


if __name__=="__main__":main()
