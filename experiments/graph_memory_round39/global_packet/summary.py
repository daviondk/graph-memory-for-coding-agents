from packet import D,W,read,save,sha,np,base
from pathlib import Path
import sys
sys.path.insert(0,str(D.parent/"remaining_budget"))
from intervals import summarize,SEEDS

def run():
    observed={};ids=None;ts=None;native=0
    for seed in SEEDS:
        prefix=f"test-{seed}";p=D/(prefix+"-outcomes.json.gz");stats=read(D/(prefix+"-scores.json"));assert stats["outcomes"]==sha(p)
        out=read(p);qs=sorted(out);group=[out[q][0] for q in qs]
        if ids is None:ids=qs;ts=group
        assert qs==ids and ts==group;native+=stats["checks"]
        for a in next(iter(out.values()))[1]:
            observed.setdefault(a,[]).append(np.array([out[q][1][a] for q in qs]))
        peer=D.parent/"remaining_budget";ref=read(peer/(prefix+"-outcomes.json.gz"));assert out.keys()==ref.keys()
        for rd in ("R35","full_rgcn","wo_chunk_adjacency"):
            for arm in ("strict","firstfit","reachdp"):
                key=rd+"/"+arm;v=np.array([ref[q][1][rd][arm] for q in qs])
                if key=="R35/firstfit":assert np.allclose(observed["R35-firstfit"][-1],v,rtol=0,atol=1e-12)
                else:observed.setdefault(key,[]).append(v)
    mats={k:np.array(v) for k,v in observed.items()};key="graph-dp"
    con=[(key,n) for n in mats if n!=key]+[("graph-greedy","R35-firstfit")]
    r=summarize(mats,ts,con);r.update(dev=read(D/"dev-selection.json"),native_checks=native,shared_packet_checks=10000,code=sha(D/"summary.py"))
    save(D/"results.json",r)
    print([(k,round(v[0]*100,2)) for k,v in r["means"].items()],flush=True)
if __name__=="__main__":run()

