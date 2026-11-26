"""Independent cut-interval oracle and finite exhaustive write scheduler."""
from sensitivity import D,P,load,put,sha,SCHEDULES
from itertools import product
from bisect import bisect_left
def algebra(history,barriers):
    active=set();maybe=set();intervals=[];incoming=0;delta=0;last=0
    for point in barriers:
        for row in history[last:point+1]:
            _,_,_,u,v=row;incoming+=len(u);delta+=len(v);active.update(u);active.difference_update(v);maybe.update(u)
        intervals.append(len(maybe-active));maybe=active.copy();last=point+1
    assert not any(r[3] or r[4] for r in history[last:])
    return intervals
def finite():
    schedules=0;checks=0;nonmonotone=0
    for truth in product(range(4),repeat=4):
        for bits in product([False,True],repeat=3):
            reads=bits+(True,);last=0;history=[]
            for j,x in enumerate(truth):
                diff_plus=x&~last;diff_minus=last&~x
                history.append([j,0,[],[z for z in range(2) if diff_plus&(1<<z)],[z for z in range(2) if diff_minus&(1<<z)]]);last=x
            expected=algebra(history,[i for i,x in enumerate(reads) if x])
            # A legal algorithm may delete any subset of inactive materialized rows at any instant.
            dp={0:(0,0)};previous=0
            for i,tr in enumerate(truth):
                candidates={};added=tr&~previous
                for stored,(batches,rows) in dp.items():
                    base=stored|added
                    assert base&tr==tr
                    for drop in (0,1,2,3):
                        if drop&~base or drop&tr:continue
                        after=base&~drop
                        if reads[i] and after!=tr:continue
                        candidate=(batches+bool(drop),rows+drop.bit_count())
                        if after not in candidates or candidate<candidates[after]:candidates[after]=candidate
                        checks+=1
                dp=candidates;previous=tr
            assert dp[truth[-1]]==(sum(bool(z) for z in expected),sum(expected));schedules+=1
    return dict(two_edge_histories=256,read_schedules_per_history=8,history_schedule_combinations=schedules,legal_dp_transitions=checks)
def main():
    records=load(D/"per-trajectory.json.gz");r=load(D/"results.json");assert sha(D/"per-trajectory.json.gz")==r["read_log"]
    n=barrierchecks=0;diff={"actual_more_reads_fewer_batches":0,"actual_fewer_reads_more_batches":0,"actual_fewer_batches":0,"actual_more_batches":0,"actual_same_batches":0}
    for part in range(8):
        for t,trace in load(P/f"operations-{part}.json.gz").items():
            h=trace["log"];grp=[j for j,v in enumerate(h) if v[1]];end=grp[-1];candidate={}
            for name in SCHEDULES:
                if name=="terminal":schedule=[end]
                elif name=="actual":schedule=[i for i,v in enumerate(h) if v[2]]
                elif name=="each_change":schedule=sorted({end}|{i for i,v in enumerate(h) if v[3] or v[4]})
                else:schedule=sorted({end}|set(grp[int(name[1:])-1::int(name[1:])]))
                raw=algebra(h,schedule);s=records[t]["policies"][name]
                assert raw==s["read_batch_sizes"] and s["batches"]==sum(x>0 for x in raw) and s["deleted_rows"]==sum(raw)
                candidate[name]=(len(raw),s["batches"]);n+=1;barrierchecks+=len(raw)
            a,f=candidate["actual"],candidate["g8"]
            diff["actual_more_reads_fewer_batches"]+=a[0]>f[0] and a[1]<f[1];diff["actual_fewer_reads_more_batches"]+=a[0]<f[0] and a[1]>f[1]
            diff["actual_fewer_batches"]+=a[1]<f[1];diff["actual_more_batches"]+=a[1]>f[1];diff["actual_same_batches"]+=a[1]==f[1]
    z=dict(real_trajectory_schedule_cells=n,real_barriers=barrierchecks,actual_vs_g8=diff,finite=finite(),results=sha(D/"results.json"));put(D/"audit.json",z);print(z)
if __name__=="__main__":main()