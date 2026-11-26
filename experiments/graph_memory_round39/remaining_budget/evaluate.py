"""Score only already sealed packets. Compare exact native source-span and atomic-union metrics."""
import argparse
import importlib.util
from pathlib import Path
import sys
spec=importlib.util.spec_from_file_location('residual_packet_reader',Path(__file__).with_name('reader.py'))
reader=importlib.util.module_from_spec(spec);spec.loader.exec_module(reader)
ARMS,BUDGET,CAL,D,W,read,sha,save,np=(getattr(reader,k) for k in ('ARMS','BUDGET','CAL','D','W','read','sha','save','np'))

def grade(stage,seed):
    pref=f"{stage}-{seed}";p=D/(pref+"-pred.json.gz");receipt=read(D/(pref+"-seal.json"))
    assert receipt["prediction"]==sha(p) and receipt["model"]==sha(D/"models.json")
    rows=read(p);sys.path.insert(0,str(W/"graph_memory_round33/budget_loss"));import data as upstream
    atomfile=W/f"graph_memory_round34/interval_witness/{stage}-atoms.json.gz";atoms=read(atomfile)
    ref=(upstream.R19/"write_transfer" if stage=="dev" else upstream.nm.OFF)/"gold-spans.json.gz"
    refs=read(ref);out={};count=0;tot=0
    for source in upstream.sources(stage):
        for record in read(source):
            q=record["q"];t,readers=rows[q];assert t==record["t"]
            node=tuple(upstream.nm.pilot.RankedNodeRecord.model_validate(j) for j in record["rr"])
            gold=tuple(upstream.nm.pilot.SourceSpan.model_validate(j) for j in refs[q])
            cost=[j.token_count for j in node];memo={};rr={}
            axis=[(hi-lo,set(ids)) for _,lo,hi,ids in atoms[q]]
            for name,item in readers.items():
                result={};head=item["head"];assert BUDGET-sum(cost[i] for i in head)==item["slack"]
                for arm in ARMS:
                    ids=head+item["extra"][arm]
                    key=frozenset(ids);assert len(key)==len(ids)
                    if key not in memo:
                        spent=sum(cost[i] for i in ids);assert spent<=BUDGET
                        v=upstream.nm.pilot.span_metrics_under_token_budget(tuple(node[i] for i in ids),gold,BUDGET)
                        length=sum(n for n,_ in axis);cover=sum(n for n,s in axis if not key.isdisjoint(s))
                        assert v.full_support==int(cover==length) and abs(v.coverage-cover/length)<1e-12
                        memo[key]=[int(v.full_support),v.coverage,spent,len(ids)]
                    result[arm]=memo[key];tot+=1
                rr[name]=result
            assert q not in out;out[q]=[t,rr];count+=len(memo)
    assert out.keys()==rows.keys() and len(out)==receipt["rows"]
    save(D/(pref+"-outcomes.json.gz"),out)
    means={rd:{a:np.mean([r[1][rd][a] for r in out.values()],axis=0).tolist() for a in ARMS} for rd in next(iter(out.values()))[1]}
    save(D/(pref+"-scores.json"),dict(means=means,n=len(out),unique_native_checks=count,packets=tot,source_spans=sha(ref),
         atoms=sha(atomfile),pred_receipt=sha(D/(pref+"-seal.json")),outcomes=sha(D/(pref+"-outcomes.json.gz")),evaluation=sha(D/"evaluate.py")))
    print(pref,"native",count,[(k,round(v["strict"][0]*100,3),round(v["firstfit"][0]*100,3),round(v["reachdp"][0]*100,3)) for k,v in means.items()],flush=True)

if __name__=="__main__":
    parser=argparse.ArgumentParser();parser.add_argument("stage",choices=["dev","test"]);parser.add_argument("seeds",type=int,nargs="+");args=parser.parse_args()
    for seed in args.seeds:grade(args.stage,seed)

