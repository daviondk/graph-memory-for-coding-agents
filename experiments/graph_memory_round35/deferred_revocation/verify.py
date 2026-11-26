"""Replay independent state by full set differences and evaluate three-budget historical controls."""
from replay import *
def validate_history(rec):
    truth=set();ever=set();seen=set();last_step=-1;groups=0
    copies={m:set() for m in MODES};stats={m:Counter() for m in MODES};checks=0;seen_reads=[]
    for step,end,cuts,ups,downs in rec["log"]:
        assert step>last_step;last_step=step;up=set(ups);down=set(downs);assert not up&truth and down<=truth and not up&down
        truth=(truth-down)|up;ever|=up
        if end:groups+=1;assert groups==end
        for a,copy in copies.items():
            old=copy.copy();new=truth-copy;copy|=new;stale=copy-truth
            st=stats[a];st["inserts"]+=len(new);st["queued"]+=len(down);st["reactivated"]+=len(old&up);st["peak"]=max(st["peak"],len(stale))
            trigger={"exact":True,"append":False,"periodic4":bool(end and end%4==0),"lazy_read":bool(cuts),"pending4":len(stale)>=4}[a]
            if trigger and stale:
                st["batches"]+=1;st["removed"]+=len(stale);copy.intersection_update(truth)
            if a=="exact":assert copy==truth
            if a=="append":assert copy==ever
            if cuts:
                if a=="lazy_read":assert copy==truth
                for cut in cuts:
                    assert rec["cuts"][str(cut)]["pending"][a]==len(copy-truth)
                checks+=1
        seen_reads+=cuts
    assert seen_reads==list(CUTS) and groups==rec["groups"]
    for a,st in stats.items():
        ss=rec["states"][a];debt=len(copies[a]-truth)
        assert all(st[k]==ss[k] for k in ["inserts","queued","reactivated","peak","batches","removed"]) and debt==ss["pending_final"]
        assert st["batches"]+(debt>0)==ss["drained_batches"] and st["removed"]+debt==ss["drained_removed"]
    return checks
def main():
    r=read(D/"results.json");out={(o["q"],o["cut"]):o for o in read(D/"outcomes.json.gz")};arch=W/"graph_memory_round34/interval_witness";ats=read(arch/"test-atoms.json.gz")
    assert sha(arch/"test-atoms.json.gz")==read(arch/"test-geometry.json")["atoms"]
    scored=hist=readchecks=0;distinct_reactivation=0;replicated=0
    for sh in range(8):
        for t,v in read(D/f"operations-{sh}.json.gz").items():
            readchecks+=validate_history(v);hist+=1;distinct_reactivation+=int(v["states"]["lazy_read"]["reactivated"]>0)
        prev={(x["q"],x["cut"]):x["selected"] for x in read(R34/f"forecast-{sh}.json.gz")}
        for q,t,cut,orders in read(D/f"orders-{sh}.json.gz"):
            assert orders["exact"]==orders["lazy_read"]==prev[q,cut]["exact"] and orders["append"]==prev[q,cut]["append"];replicated+=6
            a=ats[q];lng=np.array([v[2]-v[1] for v in a])
            for name,d in orders.items():
                got=set(d[-1]);covered=np.array([any(i in got for i in g) for *_,g in a]);ex=out[q,cut]["arms"][name]
                assert np.allclose([covered.all(),lng[covered].sum()/lng.sum()],ex[:2],rtol=0,atol=1e-12);scored+=1
    assert hist==1207 and scored==40000 and replicated==48000
    z=dict(complete_trajectories=hist,algorithm_policy_read_state_checks=readchecks,
        mode_question_cut_checks=scored,binary_and_coverage_numbers=2*scored,historical_control_prefixes_three_budgets=replicated,
        trajectories_with_observed_reactivation_lazy=distinct_reactivation,results=sha(D/"results.json"));put(D/"audit.json",z);print(z)
if __name__=="__main__":main()