"""One-sided cardinality bounds for exact capped inverse projection."""
from bisect import bisect_left,bisect_right
from collections import Counter
import hashlib,random,statistics,sys,tempfile
from pathlib import Path
D=Path(__file__).resolve().parent
sys.path.insert(0,str(D.parent/"range_read"))
from query import STORE,build,read
from inputs import get,put,sha,cap
CAPS=(16,32,64,128)
GUARDS=("sum","b1","b4","b8","exact")

def synopsis(keys,count):
    sorted_keys=sorted(keys)
    m=min(len(keys),count)
    blocks=[]
    for i in range(m):
        start=i*len(keys)//m
        stop=(i+1)*len(keys)//m
        blocks.append((sorted_keys[start],sorted_keys[stop-1],stop-start))
    return blocks

def byte_size(blocks):
    # Nonnegative unsigned LEB128: block count, then gap from previous end, width, cardinality.
    words=[len(blocks)]
    last=0
    for lo,hi,n in blocks:
        words.extend((lo-last,hi-lo,n));last=hi
    return sum(max(1,(v.bit_length()+6)//7) for v in words)

def bound(blocks,receipt,start,end,delta):
    if start is None:return len(receipt)
    addresses=sorted(receipt)
    total=len(receipt)
    for low,high,n in blocks:
        allowed=0
        for left,right,shift in ((low,min(high,start-1),0),(max(low,end+1),high,delta)):
            if right>=left:
                shadow=bisect_right(addresses,right+shift)-bisect_left(addresses,left+shift)
                allowed+=right-left+1-shadow
        total+=min(n,allowed)
    return total

def exact(base,seen,start,end,delta):
    if start is None:return len(seen)
    count=len(seen)
    for n in base:
        if start<=n<=end:continue
        dest=n if n<start else n+delta
        count+=int(dest not in seen)
    return count

def compare(item,limit):
    base=cap(item["path"],dict(item["base"]),limit)
    seen=cap(item["path"],dict(item["receipt"]),limit)
    k,z,d=(item[a] for a in ("start","end","delta"))
    truth=exact(base,seen,k,z,d)
    limits={"sum":len(base)+len(seen) if k is not None else len(seen),"exact":truth}
    sizes={}
    for n in (1,4,8):
        blocks=synopsis(base,n)
        limits["b"+str(n)]=bound(blocks,seen,k,z,d)
        sizes["b"+str(n)]=byte_size(blocks)
    assert limits["sum"]>=limits["b1"]>=limits["b4"]>=limits["b8"]>=truth
    return limits,sizes

def fixtures():
    rng=random.Random(37393)
    for _ in range(5000):
        vals=sorted(rng.sample(range(1,320),rng.randint(0,128)))
        seen=rng.sample(range(1,320),rng.randint(0,128))
        k=rng.randint(1,180);w=rng.randint(1,100)
        item=dict(path="fixture",base=[(i,i) for i in vals],receipt=[(i,i) for i in seen],
                  start=k if rng.randrange(10) else None,end=k+w-1,delta=rng.randint(1,80)-w)
        compare(item,rng.choice(CAPS))

def main():
    fixtures()
    source=get(STORE/"prefix_inputs.json.gz")
    original=get(D.parent/"range_read/forecasts.json.gz")
    prior=sha(D.parent/"range_read/manifest.json")
    inputs={i:dict(v,q=q,base=[(n,bytes.fromhex(h)) for n,h in v["base"]],
               receipt={n:bytes.fromhex(h) for n,h in v["receipt"]}) for i,(q,v) in enumerate(sorted(source.items()))}
    stats={};per={};budgets={}
    for limit in CAPS:
        counts=Counter();sizes={k:[] for k in ("b1","b4","b8")}
        for i,item in inputs.items():
            estimates,meta=compare(item,limit)
            for k,v in estimates.items():counts[k]+=int(v>limit)
            for k,value in meta.items():sizes[k].append(value)
            if limit==128:per[item["q"]]=dict(bound=estimates,bytes=meta)
        budgets[str(limit)]=dict(fallback=dict(counts),mean_summary_bytes={k:statistics.mean(v) for k,v in sizes.items()})
    # Publish fixed guard decisions before evaluating reference outputs or issuing any range.
    put(D/"decisions.json.gz",per)
    put(D/"seal.json",dict(decisions=sha(D/"decisions.json.gz"),inputs=sha(STORE/"prefix_inputs.json.gz"),
        parent=prior,code=sha(Path(__file__)),protocol=sha(D/"PROTOCOL_RU.md")))
    reference=get(STORE/"reference.json.gz");returned=Counter();equal=Counter();answer_rows=0
    with tempfile.TemporaryDirectory(dir="D:/CodexResearch") as tmp:
        dbs=build([Path(tmp)/"eager",Path(tmp)/"lazy"],inputs)
        try:
            for i,item in inputs.items():
                q=item["q"];lo,hi=original[q]["range"]
                target=[(n,bytes.fromhex(sig)) for n,sig in reference[q] if lo<=n<=hi]
                answer_rows+=len(target)
                per[q]["rows"]={}
                for method,v in per[q]["bound"].items():
                    dbs[1].execute("UPDATE v SET overflow=? WHERE e=?",(int(v>128),i))
                    got,rows=read(dbs,"inverse",i,item,lo,hi)
                    assert got==target,(q,method)
                    returned[method]+=rows;equal[method]+=1;per[q]["rows"][method]=rows
                assert per[q]["rows"]["sum"]==original[q]["arms"]["inverse"]["returned"]
        finally:
            for db in dbs:db.close()
    put(D/"measured.json.gz",per)
    result=dict(episodes=len(source),capacities=budgets,sqlite_returned=dict(returned),exact_outputs=dict(equal),
               answer_rows=answer_rows,fixtures=5000,seal=sha(D/"seal.json"),measurements=sha(D/"measured.json.gz"))
    put(D/"results.json",result)
    print(budgets,dict(returned))
if __name__=="__main__":
    main()

