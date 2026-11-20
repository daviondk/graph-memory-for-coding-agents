"""Controlled order/content interventions in completed heldout Semlith stores."""
import os,time
from concurrent.futures import ProcessPoolExecutor
from data_io import *
from native_run import load_module

def one(config):
    directory=D/"native_holdout"/config
    os.environ.update(SEMLITH_BIN=str(D/"native/semlith.exe"),SEMLITH_HOME=str(directory/"home"),SEMLITH_MODEL_CACHE=str(D/"native/models"),SEMLITH_ACCEL="cpu",SEMLITH_EMBED_THREADS="2")
    load_module("common","publisher_common.py");arms=load_module("arms","publisher_arms.py");pub=load_module("repobench","publisher_repobench.py")
    selected=read("strict_roster.json");wanted=read("paired_roster.json");items=[];out=[]
    for p in files("java","test"):
        if not p.stem.startswith(config+"_test_"):continue
        pn=panel_name(p.stem);m={j:i for j,i in selected[p.stem] if i in wanted[pn]}
        for j,row in enumerate(rows(p,["code","context"])):
            if j in m:items.append((pn,m[j],row))
    engine=arms.SemlithMCP(str(directory/"store"));start=time.monotonic()
    try:
        for i,(pn,idx,r) in enumerate(items):
            ten=r["code"].splitlines()[-10:];recent=ten[-3:]
            if not recent:recent=[""]
            repeated=(recent*4)[-len(ten):] if ten else []
            alt={"rotate":"\n".join(ten[-3:]+ten[:-3]),"repeat":"\n".join(repeated)}
            assert len(alt["rotate"].encode())==len("\n".join(ten).encode())
            n=len(r["context"]);rs={}
            for a,q in alt.items():
                hits=engine.search(q,k=n+10,paths=[f"i{i:05d}/**"]);order=[]
                for e in hits:
                    o=int(Path(e.path).stem[1:]);assert 0<=o<n
                    if o not in order:order.append(o)
                rs[a+"_binary"]=order+[x for x in range(n) if x not in order]
                rs[a+"_bm25"]=pub.bm25_rank(q,r["context"])
            out.append([pn,idx,{a:len(s.encode()) for a,s in alt.items()},rs])
    finally:engine.close()
    write("order_"+config+".json",out)
    return {"config":config,"seconds":time.monotonic()-start,"hash":sha(D/("order_"+config+".json"))}
def main():
    assert (D/"paired_decision_lock.json").exists()
    write("order_method_lock.json",{f:sha(D/f) for f in ["ORDER_PROTOCOL_RU.md","order_diagnostic.py","paired_decision_lock.json"]})
    with ProcessPoolExecutor(2) as pool:result=list(pool.map(one,["java_cff","java_cfr"]))
    write("order_prediction_lock.json",result)
if __name__=="__main__":main()
