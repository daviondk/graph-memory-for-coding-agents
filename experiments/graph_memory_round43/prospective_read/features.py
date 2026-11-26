"""Generate features without loading future reads. Freeze held repositories by public identity."""
import math
from common import *

def distance(n,start,end):return max(start-n,n-end,0)

def main():
    assert sha(D/"PROTOCOL_RU.md")=="f2decb1a6eebd974860811a42a8d618b9ca4da5087ac5dc3893e051df6f76fbe"
    gs=bind(G,"selections.json.gz");plans=bind(G,"guarded-plans.json.gz")
    earlier=bind(F,"packets.json.gz");local=bind(C,"predictions.json.gz");visible=bind(V,"visible.json.gz")
    req={}
    for j in gs:req.setdefault(j["run"],set()).add(j["view"])
    timeline=bind(H,"events.json.gz")
    views={r:{e[0]:dict(e[3]) for e in timeline[r]["events"] if e[0] in ids and e[1]=="read"} for r,ids in req.items()}
    del timeline
    rows={}
    for raw in gs:
        rid=raw["run"];key=h(rid+"/"+str(raw["receipt"]));p=earlier[key]
        packet=local[key];mv=packet["positions"]["local"];assert p["repo"]==packet["repo"]
        receipt=set(map(tuple,p["receipt"]));old=views[rid][raw["view"]]
        info={n:(d,sz) for n,d,sz,_ in visible[rid][str(raw["view"])]}
        inc,_=plans[rid][str(raw["at"])];start=raw["start"];end=raw["end"]+raw["delta"]
        assert end>=start
        blocks=[];used=set()
        for idx,path,lo,hi,cost,prior,v in inc:
            target=path==raw["path"]
            if target and str(idx) not in mv:continue
            lines=[];novel=[];dist=[];features=[]
            if target:
                newlo,newhi=mv[str(idx)]
                assert hi-lo==newhi-newlo
                for q in range(lo,hi+1):
                    dg,size=info[q]
                    if old.get(q)!=dg:continue
                    addr=newlo+q-lo;atom=(addr,dg)
                    # Each line's contribution to this file-level demand appears in at most one candidate.
                    assert atom not in used;used.add(atom)
                    lines.append([addr,dg,size])
                    if atom not in receipt:
                        novel.append([addr,dg,size]);dist.append(distance(addr,start,end))
                mind=min((distance(q,start,end) for q in (newlo,newhi)),default=0)
                if newlo<=end and newhi>=start:mind=0
                side=-1 if newhi<start else (1 if newlo>end else 0)
                features=[math.log1p(idx),math.log1p(cost),math.log1p(prior),math.log1p(mind),
                     math.log1p(hi-lo+1),math.log1p(len(lines)),math.log1p(len(novel)),
                     (len(lines)-len(novel))/max(1,len(lines)),side]
            blocks.append(dict(idx=idx,target=target,cost=cost,prior=prior,lines=lines,novel=novel,distance=dist,x=features))
        assert choose(blocks,{})==packet["choices"]["local"]
        baseline={tuple(x) for b in blocks if b["idx"] in packet["choices"]["local"] and b["target"] for x in b["lines"]}
        assert baseline=={tuple(x) for x in p["by_method"]["local"]}
        rows[key]=dict(blocks=blocks,repo=p["repo"],issue=p["issue"],held=p["held"],group=p["group"],
                       original=packet["choices"]["local"],receipt=p["receipt"])
    folds=sorted({v["repo"] for v in rows.values()});assert len(folds)==5 and len(rows)==2696
    save("features.json.gz",rows);save("feature-seal.json",dict(features=sha(D/"features.json.gz"),repos=folds,
         tools=sha(C/"manifest.json"),prior=sha(F/"manifest.json"),program=sha(D/"features.py"),
         protocol=sha(D/"PROTOCOL_RU.md"),selector=sha(D/"common.py")))
    print("Frozen",len(rows),"task-observable feature records with",len(folds),"repository folds.")

if __name__=="__main__":main()

