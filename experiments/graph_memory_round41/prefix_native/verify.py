"""Portable replay of native packet membership, external budgets, final controls and primary rates."""
from collections import Counter, defaultdict
from shared import D,W,OFF,C,ARMS,SEEDS,read,sha,panel


def check():
    m = read(D / "manifest.json")["files"]
    assert m == {p.name:sha(p) for p in D.iterdir() if p.is_file() and p.name != "manifest.json"}
    split=read(OFF/"split.json.gz")["test"]
    registered=read(D/"registration.json")
    assert registered["protocol"]==sha(D/"PROTOCOL_RU.md") and registered["terminal_panel"]==panel({r["t"] for r in split})
    seal=read(D/"forecast-seal.json")
    assert seal["predictions"]==sha(D/"forecast-packets.json.gz")
    packets={q:(t,o) for q,t,o in read(D/"forecast-packets.json.gz")}
    assert sha(D/"outcomes.json.gz")==read(D/"scoring.json")["scores"]
    obs={r["q"]:r for r in read(D/"outcomes.json.gz")}
    assert set(packets)==set(obs)=={r["q"] for r in split}
    hybrid_reg=read(D/"hybrid-registration.json")
    assert hybrid_reg["protocol"]==sha(D/"HYBRID_PROTOCOL_RU.md") and hybrid_reg["implementation"]==sha(D/"hybrids.py")
    hybrid_rows={}
    for s in SEEDS:
        hs=read(D/f"hybrids-{s}-seal.json")
        f=D/f"hybrids-{s}.json.gz"
        assert hs["data"]==sha(f) and hs["native"]==sha(D/"forecast-seal.json")
        assert hs["counts"]["r35_causal_dp_lists"]==2077 and hs["counts"]["terminal_published_orders"]==77
        hybrid_rows[str(s)]={q:(t,dp,value) for q,t,dp,value in read(f)}
        assert set(hybrid_rows[str(s)])==set(packets)
    terminal=defaultdict(Counter)
    totals=Counter()
    raw_audit=read(D/"prefix-audit-seal.json")
    assert raw_audit["graphs"]==sha(D/"prefix-audit.json.gz")
    raw_graphs={(t,cut):[step,n,e,dig] for t,cut,step,n,e,dig in read(D/"prefix-audit.json.gz")}
    for sh in range(8):
        p=D/f"forecast-{sh}.json.gz"
        assert sha(p)==seal["shards"][str(sh)]==read(D/f"forecast-{sh}-seal.json")["data"]
        for t,cut,step,n,e,dig in read(D/f"forecast-{sh}-seal.json")["traces"]:
            assert raw_graphs.pop((t,cut))==[step,n,e,dig]
        quick={(q,t,pct):rank for q,t,pct,rank in read(D/f"quick-{sh}.json.gz")}
        states={(q,pct):(t,set(av)) for q,t,pct,step,av,*other in read(C/f"state-{sh}.json.gz") if pct in (50,100)}
        tr=W/"graph_memory_round19/trained_rank"/f"forecasts-main-{sh}.json.gz"
        costs={r["q"]:[n["token_count"] for n in r["rr"]] for r in read(tr)}
        refs={}
        for s in SEEDS:
            for arm in ARMS:
                pub=OFF/f"seed-{s}"/arm
                ref=pub/f"picks-{sh}.json.gz"
                lock=read(pub/"forecast-seal.json")
                assert sha(ref)==next(v["sha"] for v in lock["receipts"] if v["file"]==ref.name)
                assert registered["checkpoints"][f"{s}/{arm}"]==[lock["checkpoint"],lock["ft"],sha(pub/"forecast-seal.json")]
                refs[f"{s}/{arm}"]={r["q"]:r["graph"] for r in read(ref)}
        for q,t,pct,orders in read(p):
            if (q,t,pct) in quick:
                assert orders==quick.pop((q,t,pct))
                totals["quick_native_orders_replayed"]+=len(orders)
            expected_t,avail=states[q,pct]
            assert expected_t==t and len(orders)==10
            assert (pct==50) or t in registered["terminal_panel"]
            def pack(it):
                total=0
                prefix=[]
                fitted=[]
                blocking=False
                for i in it:
                    weight=costs[q][i]
                    if total+weight<=2048:
                        total+=weight
                        fitted.append(i)
                        if not blocking:prefix.append(i)
                    else:
                        blocking=True
                return prefix,fitted
            for k,r in orders.items():
                assert len(r)==len(avail) and set(r)==avail
                ref=[i for i in refs[k][q] if i in avail]
                st,ff=pack(r);rs,rf=pack(ref)
                if pct==100:
                    terminal[k].update(dict(questions=1,order=int(ref==r),top1=int(ref[0]==r[0]),
                         top5=int(ref[:5]==r[:5]), strict=int(st==rs),firstfit=int(ff==rf)))
                else:
                    assert packets[q][0]==t and packets[q][1][k]==[st,ff,rs,rf]
                    s,arm=k.split("/")
                    for key,ids in zip(("strict","firstfit","final_restricted_strict","final_restricted_firstfit"),(st,ff,rs,rf)):
                        assert sum(costs[q][i] for i in ids)==obs[q]["arms"][s][f"{arm}/{key}"][2]
                    if arm=="wo_chunk_adjacency":
                        t0,dp,value=hybrid_rows[s][q]
                        assert t0==t
                        prefix=[]
                        used=0
                        for i in r:
                            if used+costs[q][i]>1024:
                                break
                            prefix.append(i)
                            used+=costs[q][i]
                        for name,ids in [("hybrid_dp",dp),("hybrid_value",value)]:
                            assert ids[:len(prefix)]==prefix and len(set(ids))==len(ids) and set(ids)<=avail
                            assert sum(costs[q][i] for i in ids)==obs[q]["arms"][s][name][2]<=2048
                    totals["half_native_orders"]+=1
        assert not quick
    assert dict(terminal)==seal["terminal"]
    assert not raw_graphs and raw_audit["raw_prefix_models"]==1207
    eligible=[r for r in obs.values() if r["eligible"] and not r["pilot"]]
    assert len(eligible)==901 and len({r["t"] for r in eligible})==657
    report=read(D/"results.json")["panels"]["eligible"]
    diff=0
    for r in eligible:
        for s in SEEDS:
            arms=r["arms"][str(s)]
            diff+=arms["wo_chunk_adjacency/firstfit"][0]-arms["graph_firstfit"][0]
    assert abs(diff/(5*901)-report["paired"][0]["mean"][0])<1e-12
    assert totals["half_native_orders"]==20000
    print(dict(totals),"terminal orders",sum(v["questions"] for v in terminal.values()),"primary records",len(eligible))


if __name__=="__main__":
    check()
