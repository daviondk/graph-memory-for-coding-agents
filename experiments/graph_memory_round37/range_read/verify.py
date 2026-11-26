"""Check signed ranges, actual timing block counts and capacity semantics on adversarial fixtures."""
import hashlib,random,tempfile
from pathlib import Path
from query import D,ARMS,build,read
from inputs import get,sha

def virtual_goal(item):
    newer=item["receipt"]
    carried={}
    if item["start"] is not None:
        for old,sig in item["base"]:
            if old<item["start"]:
                dest=old
            elif old>item["end"]:
                dest=old+item["delta"]
            else:
                continue
            if dest not in newer:
                carried[dest]=sig
    rank=lambda n:hashlib.sha256(("R37-128|"+item["path"]+"|"+str(n)).encode()).digest()
    chosen=sorted(carried,key=rank)[:128-len(newer)]
    return {n:carried[n] for n in chosen}|newer

def fixtures():
    rng=random.Random(37391)
    cases={}
    for i in range(48):
        start=None if i%7==0 else rng.randint(9,75)
        width=rng.randint(1,16)
        delta=rng.randint(1,width+12)-width
        path="fictional/module.py"
        sample=rng.sample(range(1,160),[0,8,64,120,128,20][i%6])
        base=[(n,hashlib.sha256(("old"+str(n)).encode()).digest()) for n in sorted(sample)]
        nums=rng.sample(range(1,160),[128,48,6,20,1,0][i%6])
        receipt={n:hashlib.sha256(("new"+str(n)).encode()).digest() for n in nums}
        cases[i]=dict(path=path,base=base,receipt=receipt,start=start,end=None if start is None else start+width-1,delta=delta)
    with tempfile.TemporaryDirectory() as temp:
        dbs=build([Path(temp)/"eager",Path(temp)/"lazy"],cases)
        try:
            count=0
            for e,item in cases.items():
                goal=virtual_goal(item)
                pivots=[1,9,32,64,100,165,200]
                if item["start"] is not None:
                    pivots+=list(range(item["start"]-1,item["start"]+2))+[item["end"],item["end"]+1,item["end"]+item["delta"]+1]
                for lo in sorted(set(pivots)):
                    for hi in (lo,lo+3,lo+31,lo+200):
                        wanted=sorted((n,s) for n,s in goal.items() if lo<=n<=hi)
                        for a in ARMS:
                            assert read(dbs,a,e,item,lo,hi)[0]==wanted
                        count+=1
            return count
        finally:
            for db in dbs:db.close()

def verify():
    res=get(D/"results.json");seal=get(D/"seal.json")
    assert seal["outputs"]==sha(D/"forecasts.json.gz") and seal["timings"]==sha(D/"timings.json.gz")
    raw=get(D/"forecasts.json.gz");times=get(D/"timings.json.gz")
    assert len(raw)==res["episodes"]==1282 and len(times)==128
    assert all(len(row[a])==24 and min(row[a])>0 for row in times.values() for a in ARMS)
    for a in ARMS:
        assert all(v["arms"][a]["answer"]==v["arms"]["eager_index"]["answer"] for v in raw.values())
        assert sum(v["arms"][a]["returned"] for v in raw.values())==res["db_returned"][a]
    print(len(raw),"real transitions,",fixtures(),"synthetic ranges checked against all four arms")

if __name__=="__main__":
    verify()

