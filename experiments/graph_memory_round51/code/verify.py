"""Independent combinatorial and bootstrap replay. --source additionally decodes both transports in lineage order."""
import argparse
import hashlib
import itertools
from collections import defaultdict
from statistics import median
from functools import cmp_to_key
import numpy as np
from common import *

def account(z, indices, cache):
    cost={}
    for i in indices: cost[z["keys"][i]]=z["tokens"][i]
    return [sum(v for k,v in cost.items() if k not in cache),len(cost.keys()-cache),sum(cost.values())]

def independent_rank(q,z,old,t,permuted):
    if not old: return z["current"][:8]
    pos={i:r for r,i in enumerate(z["current"],1)}
    prev={old["keys"][i]:r for r,i in reversed(list(enumerate(old["current"],1)))}
    hist={i:prev[key_] for i,key_ in enumerate(z["keys"]) if key_ in prev}
    if permuted:
        grouped=defaultdict(list)
        for i in hist: grouped[z["seen"][i],(pos[i]-1)//8].append(i)
        for block in grouped.values():
            perm=sorted(block,key=lambda i:key(["placebo",q,z["ids"][i]]))
            vals=[hist[i] for i in perm]
            for index,i in enumerate(perm): hist[i]=vals[(index+1)%len(perm)]
    def compare(i,j):
        if z["seen"][i]!=z["seen"][j]: return z["seen"][i]-z["seen"][j]
        pi,pj=hist.get(i,pos[i]),hist.get(j,pos[j])
        left=pos[i]**(4-t)*pi**max(0,t)*pj**max(0,-t)
        right=pos[j]**(4-t)*pj**max(0,t)*pi**max(0,-t)
        return ((left>right)-(left<right)) if left!=right else pos[i]-pos[j]
    return sorted(pos,key=cmp_to_key(compare))[:8]

def verify():
    x=read(HERE/"inputs.json.gz");pk=read(HERE/"packets.json.gz");out=read(HERE/"outcomes.json.gz");j=read(HERE/"judgments.json.gz")
    results=read(HERE/"results.json");f=read(HERE/"forecast-seal.json");source=read(HERE/"input-seal.json")
    assert sha(HERE/"PROTOCOL_RU.md")==f["protocol"]==source["protocol"]
    assert sha(HERE/"packets.json.gz")==f["packets"] and sha(HERE/"inputs.json.gz")==source["inputs"]
    assert sha(HERE/"outcomes.json.gz")==results["outcomes"] and sha(HERE/"judgments.json.gz")==results["judgments"]
    dev=[q for q,z in x.items() if z["panel"]=="dev"]
    csum=[sum(score(independent_rank(q,x[q],x.get(x[q]["parent"]),int(4*w),False),j[q])[0] for q in dev) for w in WEIGHTS]
    assert csum==f["dev_counts"] and f["temperature"]==WEIGHTS[csum.index(max(csum))]
    assert f["program"]==sha(HERE/"predict.py")
    n=0
    for q,z in x.items():
        p=z["parent"];past=x.get(p);base=z["current"];k=min(len(base),8)
        assert pk[q]["current"]==base[:k]
        if past: assert z["depth"]>past["depth"] and z["panel"]==past["panel"] and z["repo"]==past["repo"]
        for a,chosen in pk[q].items():
            cache=set(past["keys"][i] for i in pk[p][a]) if p else set()
            positions=[base.index(i) for i in chosen]
            assert len(set(chosen))==len(chosen)==k
            # Direct reference score from set intersections.
            sat=[sum(i in chosen for i in set(g[2]))>=g[0] for g in j[q]["groups"]]
            expected=list(account(z,chosen,cache))
            observed=[int(all(sat) or any(not (set(t)-set(chosen)) for t in j[q]["alts"])),sum(sat)/len(sat) if sat else 1.,*expected,
                      sum(positions)-sum(range(k))]
            assert np.allclose(observed,out[q][a],rtol=0,atol=1e-12)
            if not p: assert chosen==base[:k]
            if a in ("calibrated","persistence","innovation","placebo"):
                t=-2 if a=="innovation" else 2 if a=="persistence" else int(4*f["temperature"])
                assert chosen==independent_rank(q,z,past,t,a=="placebo")
            if a.startswith("min_") and p:
                initial=set(range(k));opts=[]
                # m replacements cost at least m squared ranks. With regret <=4 only m=0,1,2 are possible.
                for moves in range(3):
                    for removed in itertools.combinations(range(max(0,k-4),k),moves):
                        for added in itertools.combinations(range(k,min(len(base),k+4)),moves):
                            ranks=tuple(sorted((initial-set(removed))|set(added)))
                            loss=sum(added)-sum(removed)
                            if loss>4: continue
                            value=[base[r] for r in ranks]
                            if sum(z["seen"][i] for i in value)!=sum(z["seen"][i] for i in base[:k]): continue
                            charge=account(z,value,cache)
                            opts.append((charge[{"min_transfer":0,"min_misses":1,"min_length":2}[a]],loss,ranks))
                assert tuple(positions)==min(opts)[2]
            n+=1
    assert n==results["official_packets"]==2440
    for panel in ("dev","outside"):
        qs=sorted(q for q in x if x[q]["panel"]==panel)
        for qs,model in [(qs,panel),([q for q in qs if x[q]["parent"]],panel+"_warm")]:
            stats=results["panels"][model]
            for a,total in stats["totals"].items(): assert np.allclose(np.sum([out[q][a] for q in qs],axis=0),total)
            repos=sorted({x[q]["repo"] for q in qs});counts=np.array([sum(x[q]["repo"]==r for q in qs) for r in repos])
            draws=np.random.default_rng(510311).multinomial(len(repos),[1/len(repos)]*len(repos),size=20000)
            for pair,info in stats["pairs"].items():
                aa,bb=pair.split(" - ")
                runs=np.array([np.sum([np.subtract(out[q][aa],out[q][bb]) for q in qs if x[q]["repo"]==r],axis=0) for r in repos])
                assert np.allclose(info["ci"],np.quantile((draws@runs)/(draws@counts)[:,None],[.025,.975],axis=0))
    wire=read(HERE/"wire-results.json");wrec=read(HERE/"wire-records.json.gz");cols=read(HERE/"column-results.json");crec=read(HERE/"column-records.json.gz")
    assert sha(HERE/"WIRE_PROTOCOL_RU.md")==wire["wire_protocol"] and sha(HERE/"COLUMNS_PROTOCOL_RU.md")==cols["protocol"]
    assert sha(HERE/"wire-records.json.gz")==wire["records"] and sha(HERE/"column-records.json.gz")==cols["records"]
    dev=[q for q in x if x[q]["panel"]=="dev"]
    fixed=[min(r,key=lambda idx:sum(wrec[q]["bytes"][idx] for q in dev)) for r in (range(12),range(12,24))]
    assert fixed==wire["fixed_dev"]
    for panel in ("dev","outside"):
        for warm in (False,True):
            qs=[q for q in x if x[q]["panel"]==panel and (not warm or x[q]["parent"])]
            repos=sorted({x[q]["repo"] for q in qs})
            name=panel+("_warm" if warm else "")
            wstat=wire["panels"][name];assert wstat["states"]==len(qs) and wstat["repos"]==len(repos)
            def ratio_check(table,seed,cols_idx):
                draws=np.random.default_rng(seed).multinomial(len(repos),[1/len(repos)]*len(repos),size=20000)
                sums=np.array([sum((table[q] for q in qs if x[q]["repo"]==r),start=np.zeros(len(table[qs[0]]))) for r in repos])
                sim=draws@sums; col1,col2=cols_idx
                return sums.sum(0)[[col1,col2]],sim[:,col2]/sim[:,col1]
            wt={q:np.asarray([min(wrec[q]["bytes"][:12]),min(wrec[q]["bytes"]),*[wrec[q]["bytes"][i] for i in fixed]]) for q in qs}
            for i,mode in enumerate(("portfolio","fixed")):
                target=wstat["contrasts"][mode]
                val,rr=ratio_check(wt,510312,(2*i,2*i+1))
                assert np.array_equal(val,target["bytes"]) and np.allclose(np.quantile(1-rr,[.025,.975]),target["ci"])
            if panel=="outside":
                cstat=cols["panels"][name]
                table={q:np.asarray(crec[q]["bytes"]+[median(v) for v in crec[q]["encode_ns"]]+[median(v) for v in crec[q]["decode_ns"]]) for q in qs}
                for mode,(a,b) in zip(("digest vs typed","typed digest vs previous JSON","slot JSON vs plain JSON"),((2,3),(1,3),(0,1))):
                    for g,off in (("bytes",0),("encode",4),("decode",8)):
                        val,rr=ratio_check(table,510313,(off+a,off+b));s=cstat["contrasts"][mode][g]
                        assert np.array_equal(val,s["totals"]) and np.allclose(np.quantile(rr,[.025,.975]),s["ci_ratio"])
                assert cstat["derivable"]==sum(crec[q]["derivable"] for q in qs)
    ext=read(HERE/"external-records.json.gz");e=read(HERE/"external-results.json")
    assert sha(HERE/"TEST500_PROTOCOL_RU.md")==e["protocol"] and sha(HERE/"external-records.json.gz")==e["records"]
    assert not {z["repo"] for z in x.values()}&{z["repo"] for z in ext.values()}
    for view,qs in (("all",list(ext)),("warm",[q for q in ext if ext[q]["parent"]])):
        rec=e["panels"][view];repos=sorted({ext[q]["repo"] for q in qs})
        sums=np.array([np.sum([ext[q]["bytes"] for q in qs if ext[q]["repo"]==r],axis=0) for r in repos])
        boot=np.random.default_rng(510314).multinomial(len(repos),[1/len(repos)]*len(repos),size=20000)@sums
        assert len(qs)==rec["states"] and sums.sum(0).tolist()==rec["bytes"]
        assert np.allclose(rec["ci"],np.quantile(1-boot[:,3]/boot[:,2],[.025,.975]))
        assert sum(ext[q]["derivable"] for q in qs)==rec["derivable"]
    return x,wrec,crec

def replay(x,wrec,crec):
    import wire,columns
    src=wire.capsules(x)
    decoded={}
    for q in sorted(x,key=lambda q:(x[q]["depth"],q)):
        previous=decoded.get(x[q]["parent"],[])
        frames=wire.encode(src[q],previous,range(24))
        for i,f in frames.items():
            assert len(f)==wrec[q]["bytes"][i] and hashlib.sha256(f).hexdigest()==wrec[q]["hashes"][i]
            assert wire.decode(f,previous)==src[q]
        shortest=min(frames.values(),key=len)
        decoded[q]=wire.decode(shortest,previous)
        assert hashlib.sha256(wire.packed(decoded[q])).hexdigest()==wrec[q]["canonical_sha256"]
        if q in crec:
            for j,i in enumerate((5,17,24,25)):
                f=columns.selected_encode(src[q],previous,i)
                assert len(f)==crec[q]["bytes"][j] and hashlib.sha256(f).hexdigest()==crec[q]["hashes"][j]
                assert columns.selected_decode(f,previous)==src[q]
    print("Reconstructed 305 ordered source packets, 7320 Zstd frames and 816 fixed transports using decoded predecessor packets.")
if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--source",action="store_true")
    args=parser.parse_args()
    x,w,c=verify()
    if args.source: replay(x,w,c)
    if args.source:
        import external
        expected=read(HERE/"external-results.json");rows,s=external.run()
        assert rows==read(HERE/"external-records.json.gz") and s["panels"]==expected["panels"]
        print("Reconstructed 1964 Test500 frames across 491 states and 43 additional repositories.")
    print("Verified 2440 scored packets, exhaustive history-constrained choices, paired clustered intervals and transport sizes.")

