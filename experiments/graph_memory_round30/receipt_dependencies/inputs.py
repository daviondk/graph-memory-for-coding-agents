"""Freeze write-time registry and unseen delete requests without building a cache."""
from pathlib import Path
import hashlib
import sys
D=Path(__file__).resolve().parent;W=D.parents[1];R=W/"graph_memory_round29/multi_retraction";DIV=W/"graph_memory_round29/cache_diversity"
sys.path.insert(0,str(R))
from multiban_design import PRIVATE,read,save,sha,merge,arrays,pack,decode
from store import state

def h(s):
    return hashlib.sha256(s.encode()).digest()
def main():
    p,cases,old,logs,base=state()
    parent=read(R/"scenarios.json.gz");out={}
    for q in p["qids"]:
        reg=sorted({tuple(x[:2]) for x in cases[q]["states"]["base"]["parts"]});index={r:i for i,r in enumerate(reg)}
        primary={f"{kind}-{k}":[index[tuple(x)] for x in xs] for kind in ("targeted","independent") for k,xs in parent[q][kind].items()}
        sampled={}
        for level in (1,3,5,8):
            for j in range(16):
                name=f"p{level}.{j}";sampled[name]=[i for i in range(len(reg)) if int.from_bytes(h(f"r30-receipt/{q}/{name}/{i}")[:8],"big")*10<level*(1<<64)]
        mixed={}
        for j in range(12):
            seed=h(f"r30-nonreceipt/{q}/{j}");eligible=[r for r in reg if r[1]-r[0]>2];l,r=eligible[int.from_bytes(seed[:4],"big")%len(eligible)]
            width=1+int.from_bytes(seed[4:8],"big")%min(40,r-l-1);pos=l+int.from_bytes(seed[8:12],"big")%(r-l-width+1)
            partial=(pos,pos+width)
            while partial in index:
                if partial[1]-partial[0]>1:partial=(partial[0],partial[1]-1)
                else:
                    candidates=[(v,v+1) for v in range(l,r) if (v,v+1) not in index];assert candidates;partial=candidates[0];break
            ids=[] if j<8 else [int.from_bytes(seed[12:16],"big")%len(reg)]
            mixed[f"{'partial' if j<8 else 'mixed'}-{j}"]={"known":ids,"unknown":[partial]}
        out[q]={"article":cases[q]["title"],"registry":reg,"primary":primary,"sampled":sampled,"outside":mixed}
    plan={"protocol":sha(D/"PROTOCOL_RU.md"),"input":sha(R/"scenario-seal.json"),"parent":sha(R/"manifest.json"),"code":sha(Path(__file__)),
          "timing_panel":p["panel"],"sizes":[8,64],"policies":["raw","producer","mask_group","mask_pareto","geometry","nms30"]}
    pf=D/"plan.json"
    if pf.exists():assert read(pf)==plan
    else:save(pf,plan)
    save(D/"events.json.gz",out);save(D/"event-seal.json",{"plan":sha(pf),"events":sha(D/"events.json.gz"),"n":len(out)})
if __name__=="__main__":main()
