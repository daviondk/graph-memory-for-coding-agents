"""Complete the forecast boundary and qualify states shared with the previous schedule; no gold."""
from collections import Counter,defaultdict
from io43 import D,W,R41,R42,OFF,SEEDS,ARMS,read,save,sha


def main():
    outputs={};state_count=Counter();shared=defaultdict(Counter);checks=Counter()
    independent=read(D/"schedule-audit.json.gz")
    assert sha(D/"schedule-audit.json.gz")==read(D/"schedule-audit-seal.json")["data"]
    r42=read(R42/"forecast-seal.json")
    r41=read(R41/"forecast-seal.json")
    historical={q:o for q,t,o in read(R41/"forecast-packets.json.gz")}
    assert sha(R41/"forecast-packets.json.gz")==r41["predictions"]
    for sh in range(8):
        p=D/f"packets-{sh}.json.gz";st=D/f"traces-{sh}.json.gz";r=read(D/f"forecast-{sh}-seal.json")
        assert [sha(p),sha(st),sha(D/"registration.json")]==[r["packets"],r["traces"],r["registered"]]
        outputs[str(sh)]=[sha(p),sha(st)]
        prev={t:(step,h) for t,cut,step,nn,ne,h in read(R41/f"forecast-{sh}-seal.json")["traces"] if cut==50}
        equal=set()
        for t,fired,groups,calls,n,events,nodes,h in read(st):
            assert independent.pop(t)==[n,groups,calls]
            state_count["graphs"]+=1;state_count["triggered"]+=int(fired)
            if not fired:assert groups<8;continue
            assert groups==8
            if events-1==prev[t][0]:
                assert h==prev[t][1];equal.add(t)
            else:assert h!=prev[t][1]
        state_count["same_time_graphs"]+=len(equal)
        prior=R42/f"packets-{sh}.json.gz";assert sha(prior)==r42["packets"][str(sh)]
        before=read(prior)
        for q,(t,fired,available,o) in read(p).items():
            state_count["questions"]+=1;state_count["fired_questions"]+=int(fired)
            if not fired:
                assert not o and not available;continue
            assert set(o)==set(map(str,SEEDS)) and available and len(set(available))==len(available)
            if t not in equal:continue
            state_count["same_time_queries"]+=1
            for s in SEEDS:
                mapped=before[q][1][str(s)];assert before[q][0]==t
                for arm in ARMS:
                    ref=(historical[q][f"{s}/wo_chunk_adjacency"][1] if arm=="native_wo" else
                        mapped[arm] if arm in ("R35","dense") else mapped["hgb/"+arm])
                    proposed=o[str(s)][arm]
                    shared[arm].update(records=1,ordered=int(ref==proposed),same_set=int(set(ref)==set(proposed)))
    assert not independent and state_count["questions"]==2000 and state_count["graphs"]==1207
    save(D/"forecast-seal.json",dict(outputs=outputs,registration=sha(D/"registration.json"),counts=state_count,
         shared_states=shared,source_seals=[sha(R41/"forecast-seal.json"),sha(R42/"forecast-seal.json")],
         schedule=sha(D/"schedule-audit-seal.json"),code=sha(D/"seal43.py")))
    print("sealed",state_count,"shared",dict(shared),flush=True)


if __name__=="__main__":main()
