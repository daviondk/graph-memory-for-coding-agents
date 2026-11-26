"""Seal receipt-only conflict signals before consulting later observed file contents."""
import gzip,hashlib,json
from pathlib import Path
D=Path(__file__).resolve().parent
W=D.parents[1]
STORE=W/"graph_memory_round37"/"code_store"
VIS=W/"graph_memory_round37"/"code_visibility"
ARMS=("side","local","side_equal","local_equal")
def sha(value):
    return hashlib.sha256(value).hexdigest()
def load(path):
    data=path.read_bytes()
    return json.loads(gzip.decompress(data) if path.suffix==".gz" else data)
def put(name,data):
    binary=(json.dumps(data,sort_keys=True,ensure_ascii=False,separators=(",",":"))+"\n").encode()
    if name.endswith(".gz"):
        binary=gzip.compress(binary,mtime=0)
    (D/name).write_bytes(binary)
    return sha(binary)
def top(path,candidates,limit):
    return sorted(candidates,key=lambda n:(sha(f"R37-128|{path}|{n}".encode()),n))[:limit]
def memory(q,r):
    receipt=dict(r["receipt"])
    old={}
    seen={"left":[],"right":[]}
    start,end,delta=r["start"],r["end"],r["delta"]
    if start is not None:
        for n,hash_before in r["base"]:
            if start<=n<=end:continue
            side="left" if n<start else "right"
            new=n if side=="left" else n+delta
            if new in receipt:
                seen[side].append([new,hash_before==receipt[new]])
            else:
                old[new]=[hash_before,side]
    retain=top(r["path"],old,128-len(receipt))
    old={n:old[n] for n in retain}
    conflict={s:any(not match for _,match in evidence) for s,evidence in seen.items()}
    drop_side=sorted(n for n,(_,s) in old.items() if conflict[s])
    drop_local=[]
    for n in drop_side:
        evidence=seen[old[n][1]]
        nearest=min(abs(n-i) for i,_ in evidence)
        if nearest<=8 and not any(match for i,match in evidence if abs(n-i)==nearest):
            drop_local.append(n)
    priority=sorted(old,key=lambda n:(sha(f"receipt-v1|{q}|{n}".encode()),n))
    arms=dict(side=drop_side,local=drop_local,side_equal=sorted(priority[:len(drop_side)]),
              local_equal=sorted(priority[:len(drop_local)]))
    return dict(issue=r["issue"],zone=r["zone"],receipt=sorted(receipt.items()),
                old=sorted([n,h,s] for n,(h,s) in old.items()),
                witness={s:sorted(v) for s,v in seen.items()},drop=arms)
def fixtures():
    for delta in (-4,0,3):
        row=dict(issue="",zone="",path="p",start=14,end=21,delta=delta,
                 base=[[3,"a"],[5,"b"],[7,"c"],[9,"d"],[13,"e"],[15,"f"],[32,"g"],[33,"h"],[48,"i"]],
                 receipt=[[5,"m"],[9,"d"],[32+delta,"n"]])
        out=memory("q",row)
        assert out["witness"]=={"left":[[5,False],[9,True]],"right":[[32+delta,False]]}
        assert out["drop"]["side"]==[3,7,13,33+delta,48+delta]
        assert out["drop"]["local"]==[3,33+delta]
        assert 15 not in {n for n,_,_ in out["old"]}
        for name in ("side","local"):
            assert len(out["drop"][name])==len(out["drop"][name+"_equal"])
        no=memory("q",dict(row,start=None,end=None))
        assert not no["old"] and dict(no["receipt"])==dict(row["receipt"])
def main():
    fixtures()
    p=STORE/"prefix_inputs.json.gz"
    assert sha((STORE/"manifest.json").read_bytes())=="20caf717a4076477487d4b870c9a20d35bbdf48c5e562e4fff6422506d90aaeb"
    assert sha(p.read_bytes())==load(STORE/"manifest.json")["files"][p.name]
    inputs=load(p)
    out={q:memory(q,r) for q,r in inputs.items()}
    result=put("predictions.json.gz",out)
    put("seal.json",dict(input=sha(p.read_bytes()),result=result,episodes=len(out),
                         protocol=sha((D/"PROTOCOL_RU.md").read_bytes()),code=sha(Path(__file__).read_bytes())))
    print("frozen",len(out),result)
if __name__=="__main__":main()

