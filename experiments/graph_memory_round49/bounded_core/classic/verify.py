"""Check every panel outcome from the frozen numerical input with standard Python."""
import gzip
import hashlib
import json
import statistics
from pathlib import Path

D=Path(__file__).resolve().parent

def load(p):
    raw=p.read_bytes()
    return json.loads(gzip.decompress(raw) if p.suffix==".gz" else raw)

def decide(cost,ids,profit):
    head=[]
    used=0
    for i in ids:
        if used+cost[i]>1024:
            break
        used+=cost[i]
        head.append(i)
    room=2048-used
    values=[0]*(room+1)
    decisions=[]
    for i,v in zip(ids[len(head):],profit[len(head):]):
        c=cost[i]
        row=bytearray(room+1)
        if c<=room:
            for b in range(room,c-1,-1):
                alt=values[b-c]+v
                if alt>values[b]:
                    row[b]=1
                    values[b]=alt
        decisions.append(row)
    tail=[]
    for i,row in zip(reversed(ids[len(head):]),reversed(decisions)):
        if row[room]:
            tail.append(i)
            room-=cost[i]
    return head+list(reversed(tail))

def main():
    s=load(D/"results.json")
    rowdata=load(D/"ledger.json.gz")
    src=D.parents[1]/"learned_stream"/"input-13.json.gz"
    assert hashlib.sha256(src.read_bytes()).hexdigest()=="3886b8ab29eb61728cc2d235d3fc7a1bc89cb645c9b06ddb2dd485a1c5bf6f36"
    raw=load(src)
    panel=sorted(raw,key=lambda q:hashlib.sha256(("classic-r49:"+q).encode()).digest())[:128]
    assert [(r["query"],r["step"]) for r in rowdata]==[(q,j) for q in panel for j in range(4)]
    assert s["queries"]==128 and s["trajectories"]==len({raw[q]["t"] for q in panel})
    counts={m:0 for m in s["ordered_matches"]}
    for row in rowdata:
        d=raw[row["query"]]
        cost=d["cost"]
        _,_,ids,values,_=d["states"][row["step"]]
        assert row["trajectory"]==d["t"]
        canonical=decide(cost,ids,values)
        value=dict(zip(ids,values))
        assert sum(value[i] for i in canonical)==row["objective"]
        for name,packet in row["packets"].items():
            subset=set(packet)
            assert packet==[i for i in ids if i in subset]
            assert sum(cost[i] for i in packet)<=2048
            assert sum(value[i] for i in packet)==row["objective"]
            pos=0
            for i in ids:
                if pos+cost[i]>1024:break
                assert i in subset
                pos+=cost[i]
            counts[name]+=packet==canonical
    assert counts==s["ordered_matches"]
    assert all(x==len(rowdata)==512 for x in s["objective_matches"].values())
    assert max(r["objective"] for r in rowdata)==s["max_objective"]
    assert sum(r["objective"]>2**31-1 for r in rowdata)==s["objectives_over_int32"]
    times=load(D/"timings.json.gz")
    assert len(times)==1536 and len({(q,r,m) for q,r,m,_ in times})==1536
    for mode in counts:
        totals=[sum(n for _,r,m,n in times if r==rep and m==mode)/1e6 for rep in (1,2,3)]
        assert totals==s["timed_total_ms_by_rep"][mode]
        assert statistics.median(totals)==s["median_total_ms"][mode]
    print("Verified 512 canonical packets, 2048 state-method solutions and 1536 timed query-method-replicates.")

if __name__=="__main__":
    main()
