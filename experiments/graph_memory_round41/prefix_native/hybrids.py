"""Transfer fixed R39 packing onto the newly inferred prefix-native order before grading."""
import os
for name in ("OPENBLAS_NUM_THREADS","MKL_NUM_THREADS","OMP_NUM_THREADS"):
    os.environ[name]="1"
import sys
from pathlib import Path
from collections import Counter
from shared import D,W,C,OFF,SEEDS,read,save,sha
GP=W/"graph_memory_round39/global_packet"
CONTROL=W/"graph_memory_round39/hybrid_controls"
sys.path.insert(0,str(GP))
import packet
import numpy as np


def hybrid(order,c,u,solve):
    dp=packet.select(order,c,u,1024,"dp",solve)
    cumulative=np.cumsum(c[order])
    k=int(cumulative.searchsorted(1024,side="right"))
    head=order[:k].tolist()
    cap=2048-(int(cumulative[k-1]) if k else 0)
    tail=order[k:]
    allowed=tail[c[tail]<=cap]
    greedy=head+allowed[packet.base.fill(c[allowed],np.argsort(-u[allowed],kind="stable"),cap)].tolist()
    assert dp[:k]==greedy[:k]==head and c[dp].sum()<=2048 and c[greedy].sum()<=2048
    return dp,greedy


def run(s):
    initial=read(D/"hybrid-registration.json")
    assert initial["protocol"]==sha(D/"HYBRID_PROTOCOL_RU.md") and initial["implementation"]==sha(D/"hybrids.py")
    seal=read(D/"forecast-seal.json")
    assert seal["questions"]==2000
    raw={r["q"]:r for r in read(Path("D:/CodexResearch/x20-r33-budget-loss/test.json.gz"))}
    m=read(GP/"models.json")["models"]["graph"]
    rank_m=read(W/"graph_memory_round20/factor_reader/hash64-weights.json")["rank"] if s==13 else read(W/f"graph_memory_round21/five_seed/seed-{s}/calibration.json")["rank"]
    src=CONTROL/f"test-{s}-packets.json.gz"
    historical_lock=read(CONTROL/f"test-{s}-seal.json")
    assert sha(src)==historical_lock["packets"]
    hist=read(src)
    order_no=historical_lock["orders"].index("wo_chunk_adjacency")
    budget_no=historical_lock["budgets"].index(2048)
    rule_dp=historical_lock["rules"].index("graph_dp")
    rule_value=historical_lock["rules"].index("graph_value")
    counts=Counter()
    solve=packet.base.kernel()
    results=[]
    for sh in range(8):
        forecast=D/f"forecast-{sh}.json.gz"
        assert sha(forecast)==seal["shards"][str(sh)]
        new={(q,cut):v[f"{s}/wo_chunk_adjacency"] for q,t,cut,v in read(forecast)}
        canonical_file=OFF/f"seed-{s}/wo_chunk_adjacency"/f"picks-{sh}.json.gz"
        assert sha(canonical_file)==next(j["sha"] for j in read(canonical_file.parent/"forecast-seal.json")["receipts"] if j["file"]==canonical_file.name)
        terminal_orders={r["q"]:r["graph"] for r in read(canonical_file)}
        old_file=C/f"pred-{s}-{sh}.json.gz"
        assert sha(old_file)==read(C/f"pred-{s}-{sh}-seal.json")["data"]
        baseline={(q,cut):arms["graph_dp"] for q,t,cut,pilot,arms in read(old_file)}
        dense_src={} if s==13 else {v["q"]:v["dense"] for v in read(W/f"graph_memory_round21/five_seed/seed-{s}/picks-{sh}.json.gz")}
        xs=[];records=[]
        state=C/f"state-{sh}.json.gz"
        assert sha(state)==read(C/f"state-{sh}-seal.json")["data"]
        for q,t,cut,at,visible,graph,pilot in read(state):
            if (q,cut) not in new:
                continue
            v=np.asarray(visible,dtype=int)
            ix={j:i for i,j in enumerate(visible)}
            n=len(v)
            orig=raw[q]
            z=np.asarray(orig["x"])[v].copy()
            dense=np.arange(n) if s==13 else np.array([ix[j] for j in dense_src[q] if j in ix],dtype=int)
            assert len(dense)==n
            offset=np.empty(n)
            offset[dense]=packet.base.linear(rank_m,packet.base.rankx(n))
            z[dense,0]=np.log1p(np.arange(1,n+1))
            x,gr=packet.feature(z,np.array(graph),offset)
            xs.append(x)
            records.append((q,t,cut,v,ix,np.asarray(orig["c"],dtype=int)[v],gr))
        gain=np.logaddexp(0,packet.portable(m,np.vstack(xs)[:,m["cols"]]))
        cursor=0
        for q,t,cut,v,ix,c,gr in records:
            u=gain[cursor:cursor+len(v)]
            cursor+=len(v)
            assert v[packet.select(gr,c,u,1024,"dp",solve)].tolist()==baseline[q,cut]
            counts["r35_causal_dp_lists"]+=1
            order=np.array([ix[j] for j in new[q,cut]],dtype=int)
            dp,value=hybrid(order,c,u,solve)
            actual=[v[dp].tolist(),v[value].tolist()]
            if cut==50:
                results.append([q,t,*actual])
                continue
            ref_order=np.array([ix[j] for j in terminal_orders[q]],dtype=int)
            ref_dp,ref_value=hybrid(ref_order,c,u,solve)
            prev=hist[q][1][order_no][budget_no]
            reference=[prev[rule_dp],prev[rule_value]]
            assert [v[ref_dp].tolist(),v[ref_value].tolist()]==reference
            counts["terminal_published_orders"]+=1
            counts["terminal_cpu_dp_matches"]+=int(actual[0]==reference[0])
            counts["terminal_cpu_value_matches"]+=int(actual[1]==reference[1])
            if np.array_equal(ref_order,order):
                assert actual==reference
                counts["terminal_equal_orders"]+=1
        assert cursor==len(gain)
    assert len(results)==len({r[0] for r in results})==2000
    path=D/f"hybrids-{s}.json.gz"
    save(path,results)
    save(D/f"hybrids-{s}-seal.json",dict(data=sha(path), model=sha(GP/"models.json"),counts=counts,
        reference=sha(src),registration=sha(D/"hybrid-registration.json"),native=sha(D/"forecast-seal.json")))
    print("frozen hybrids",s,dict(counts),flush=True)


if __name__=="__main__":
    if sys.argv[1:]==["--register"]:
        path=D/"hybrid-registration.json"
        assert not path.exists() and not (D/"scoring.json").exists()
        save(path,dict(protocol=sha(D/"HYBRID_PROTOCOL_RU.md"),main=sha(D/"registration.json"),implementation=sha(D/"hybrids.py"),
                       model=sha(GP/"models.json"),reference=sha(CONTROL/"manifest.json")))
        print(sha(path))
    else:
        for s in map(int,sys.argv[1:] or SEEDS):
            run(s)
