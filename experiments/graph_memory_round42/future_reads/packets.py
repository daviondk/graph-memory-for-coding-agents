"""Freeze observable (new line, literal digest, byte cost) for available candidate policies."""
from data import *


def freeze(choices,relocated,plan,current_path,old_view,native_past):
    selected=set(choices);out={}
    for idx,path,lo,hi,_,_,_ in plan:
        if idx not in selected or path!=current_path:continue
        u,v=relocated[str(idx)]
        assert v-u==hi-lo
        for line in range(lo,hi+1):
            dg,size=old_view[line]
            if native_past.get(line)!=dg:continue
            addr=u+line-lo;key=(addr,dg)
            assert key not in out or out[key]==size
            out[key]=size
    return [[n,d,sz] for (n,d),sz in sorted(out.items())]


def main():
    assert sha(D/"PROTOCOL_RU.md")=="7a87d186ed3c9e6e1c72395d77847725bc1dca3c5ab6218f8ed184847b490afc"
    cases=bind(G,"selections.json.gz");plans=bind(G,"guarded-plans.json.gz");vis=bind(V,"visible.json.gz")
    previous=bind(S,"predictions.json.gz");local=bind(C,"predictions.json.gz")
    union=read(L/"forecasts.json.gz");assert sha(L/"forecasts.json.gz")==read(L/"forecast-seal.json")["forecast"]
    # For preparation, only rows exactly at previous-read and present-receipt indices are exposed to the policy.
    limit={}
    for r in cases:limit.setdefault(r["run"],set()).update((r["view"],r["receipt"]))
    corpus=bind(H,"events.json.gz")
    material={run:{ev[0]:ev for ev in corpus[run]["events"] if ev[0] in indices} for run,indices in limit.items()}
    del corpus
    sols={}
    for r in cases:
        rid=r["run"];key=h(rid+"/"+str(r["receipt"]));earlier,current=material[rid][r["view"]],material[rid][r["receipt"]]
        assert earlier[1]=="read" and current[1]=="edit" and h(earlier[2])==h(current[2])==r["path"]
        orig=previous[key];new=local[key];u=union[key]
        assert orig["old"]==new["old"]==u["old"]==r["old"] and u["issue"]==r["issue"]==new["issue"]
        assert u["held"]==r["held"]
        plan,_=plans[rid][str(r["at"])];vmap={n:(d,size) for n,d,size,_ in vis[rid][str(r["view"])]}
        available=dict(earlier[3]);receipt=dict(current[3]["rows"])
        out={}
        for m in METHODS:
            if m=="union":
                seq=u["ids"];maps=u["addresses"]
                original=orig["maps"];all_units=original["content"]|original["range"]
                assert all(all_units[j]==s for j,s in maps.items())
            elif m in ("local","edges"):
                seq=new["choices"][m];maps=new["positions"][m]
            else:seq=orig["choices"][m];maps=orig["maps"][m]
            out[m]=freeze(seq,maps,plan,r["path"],vmap,available)
        sols[key]=dict(run=rid,ack=r["receipt"],receipt=sorted(receipt.items()),issue=r["issue"],held=r["held"],group=r["group"],
                       repo=new["repo"],by_method=out)
    assert set(sols)==set(previous)==set(local)==set(union) and len(sols)==2696
    save("packets.json.gz",sols);save("packet-seal.json",dict(packets=sha(D/"packets.json.gz"),local=sha(C/"predictions.json.gz"),
        structural=sha(S/"predictions.json.gz"),union=sha(L/"forecasts.json.gz"),visibility=sha(H/"events.json.gz"),
        inputs=sha(G/"selections.json.gz"),program=sha(D/"packets.py"),protocol=sha(D/"PROTOCOL_RU.md")))
    print("Frozen addressable packets including verified merged strategy on",len(sols),"edits.")


if __name__=="__main__":main()

