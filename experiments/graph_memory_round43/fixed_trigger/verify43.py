"""Replay schedule joins, all budgets, direct interval sums and paired full-support counts."""
from collections import Counter,defaultdict
from io43 import D,W,R41,R42,OFF,SEEDS,ARMS,read,sha


def main():
    m=read(D/"manifest.json")["files"]
    assert m=={p.name:sha(p) for p in D.iterdir() if p.is_file() and p.name!="manifest.json"}
    r=read(D/"registration.json")
    assert r["protocol"]==sha(D/"PROTOCOL_RU.md") and r["gate"]==sha(D/"trigger43.py") and r["forecast"]==sha(D/"forecast43.py")
    assert r["r42"]==sha(R42/"manifest.json") and r["weights"]==sha(R42/"models.json") and r["r41"]==sha(R41/"manifest.json")
    st=read(D/"schedule-audit.json.gz");seals=read(D/"forecast-seal.json")
    obs={r["q"]:r for r in read(D/"outcomes.json.gz")}
    grade=read(D/"scoring.json")
    assert sha(D/"outcomes.json.gz")==grade["outcomes"] and sha(D/"forecast-seal.json")==grade["forecasts"]
    path=W/"graph_memory_round34/interval_witness/test-atoms.json.gz";assert sha(path)==grade["atoms"]
    partition=read(path);qa=Counter()
    for sh in range(8):
        p=D/f"packets-{sh}.json.gz";tfile=D/f"traces-{sh}.json.gz"
        assert seals["outputs"][str(sh)]==[sha(p),sha(tfile)]
        for t,fired,k,calls,n_msg,n_events,n_nodes,h in read(tfile):
            assert st[t]==[n_msg,k,calls] and (k==8)==fired
        costs={r["q"]:[n["token_count"] for n in r["rr"]] for r in read(W/"graph_memory_round19/trained_rank"/f"forecasts-main-{sh}.json.gz")}
        for q,(t,fire,avail,picks) in read(p).items():
            rr=obs[q];assert rr["t"]==t and fire==rr["fired"]
            qa["assigned"]+=1
            if not fire:
                assert not avail and not picks and rr["arms"]=={} and rr["visibility"]==0
                qa["nonfired"]+=1;continue
            available=set(avail);assert len(avail)==len(available)
            atoms=[(b-a,set(ids)) for _,a,b,ids in partition[q]];size=sum(k for k,_ in atoms)
            def mass(ids):return sum(k for k,nodes in atoms if not ids.isdisjoint(nodes))
            visible=mass(available)
            assert abs(visible/size-rr["visibility"])<1e-12 and (visible==size)==rr["eligible"]
            for s in SEEDS:
                for arm in ARMS:
                    selected=picks[str(s)][arm];d=set(selected)
                    assert len(d)==len(selected) and d<=available
                    cover=mass(d);cost=sum(costs[q][i] for i in selected)
                    score=rr["arms"][str(s)][arm]
                    assert int(cover==size)==score[0] and abs(cover/size-score[1])<1e-12 and cost==score[2]<=2048
                    qa["packets"]+=1
    result=read(D/"results.json")
    assert len(st)==1207 and qa["assigned"]==len(obs)==2000 and qa["nonfired"]==result["nonfired"]["questions"]
    for key,predicate in [
            ("primary",lambda v:v["fired"] and not v["pilot"] and v["eligible"]),
            ("fired_eligible",lambda v:v["fired"] and v["eligible"]),("fired",lambda v:v["fired"]),
            ("nonpilot_fired",lambda v:v["fired"] and not v["pilot"]),
            ("nonpilot_assigned",lambda v:not v["pilot"]),("all_assigned",lambda v:True)]:
        rows=[v for v in obs.values() if predicate(v)]
        group=result["groups"][key]
        assert group["n"]==len(rows) and group["trajectories"]==len({v["t"] for v in rows})
        for contrast in group["paired"]:
            diff=sum(v["arms"][str(s)][contrast["left"]][0]-v["arms"][str(s)][contrast["right"]][0]
                     for v in rows if v["fired"] for s in SEEDS)
            assert abs(contrast["mean"][0]-diff/(len(rows)*5))<1e-12
    same=read(D/"same-time-numeric.json");timing=read(D/"timing.json")
    assert same["seal"]==timing["seal"]==sha(D/"forecast-seal.json")
    assert all(c["ordered"]==c["total"]==570 for c in same["counts"].values())
    assert timing["categories"]["questions"]["equal"]==114
    print(dict(qa),"primary",result["groups"]["primary"]["n"],"trajectories",len(st))


if __name__=="__main__":main()
