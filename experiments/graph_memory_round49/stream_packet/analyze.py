"""Grade sealed packets and bootstrap timing and support differences by whole trajectory."""
from collections import defaultdict
from statistics import median
import numpy as np
from fixture import D,W,load,save,digest

def grade(inputs):
    sealed=load(D/"forecast-seal.json")
    predictions=load(D/"packets.json.gz")
    assert sealed["packets"]==digest((D/"packets.json.gz").read_bytes())
    source=W/"graph_memory_round34/interval_witness/test-atoms.json.gz"
    receipt=load(D/"judgment-source.json")
    assert digest((D/"judgments.json.gz").read_bytes())==receipt["file"]
    atoms=load(D/"judgments.json.gz")
    if source.is_file():
        assert digest(source.read_bytes())==receipt["source"]
        original={digest(q.encode()):[[b-a,sorted(set(ids))] for _,a,b,ids in rows] for q,rows in load(source).items()}
        assert original==atoms
    assert set(atoms)==set(predictions)==set(inputs)
    scores={}
    for q,v in predictions.items():
        costs={r[1]:r[2] for r in inputs[q][1]};birth={r[1]:r[0] for r in inputs[q][1]}
        req=atoms[q];total=sum(w for w,ids in req)
        row={}
        for stage,step in (("final",v["last"]),("eight",8)):
            if str(step) not in v:continue
            have=all(any(birth[i]<=step for i in ids) for _,ids in req)
            opts={}
            for rule,items in v[str(step)].items():
                ids=set(items);tokens=sum(costs[i] for i in ids)
                covered=sum(w for w,a in req if any(i in ids for i in a))
                assert len(items)==len(ids) and tokens<=2048 and all(birth[i]<=step for i in ids)
                opts[rule]=[int(covered==total),covered/total,tokens]
            row[stage]=[int(have),opts]
        scores[q]=row
    save(D/"scores.json.gz",scores)
    return scores
def cluster_weights(inputs):
    hashes=sorted({r[0] for r in inputs.values()})
    ix={t:i for i,t in enumerate(hashes)}
    rng=np.random.default_rng(49010)
    weights=rng.multinomial(len(hashes),np.full(len(hashes),1/len(hashes)),size=10000).astype(float)
    return weights,{q:ix[r[0]] for q,r in inputs.items()}
def interval(data):
    return np.percentile(data,[2.5,97.5]).tolist()
def main():
    inp=load(D/"input.json.gz");sc=grade(inp);boot,groups=cluster_weights(inp);n=boot.shape[1]
    ts=load(D/"timing.json.gz");blocks=defaultdict(list);diagnostics={}
    for q,rep,mode,p,elapsed,vis,re,peak in ts:
        k=q,mode,p;blocks[k].append(elapsed)
        b=vis,re,peak;assert diagnostics.setdefault(k,b)==b
    assert len(ts)==2000*5*9 and all(len(v)==5 for v in blocks.values())
    modes=sorted({(a,b) for q,a,b in blocks})
    costs={};times={}
    for mode,p in modes:
        a=np.zeros(n);rows=rest=0;peaks=[];total=0
        for q in inp:
            k=q,mode,p;ns=median(blocks[k]);a[groups[q]]+=ns;total+=ns
            vis,re,peak=diagnostics[k];rows+=vis;rest+=re;peaks.append(peak)
        costs[mode,p]=a
        times[f"{mode}/{p}"]=dict(cpu_ms=total/1e6,dp_rows=rows,rewound=rest,max_dp_bytes=max(peaks),median_peak_bytes=median(peaks))
    for mode,p in modes:
        a,b=costs[0,p],costs[mode,p]
        row=times[f"{mode}/{p}"]
        row.update(speedup=float(a.sum()/b.sum()),ci=interval((boot@a)/(boot@b)))
        if p==1:
            a=costs[-1,p];row.update(vs_tail=float(a.sum()/b.sum()),vs_tail_ci=interval((boot@a)/(boot@b)))
    metrics={}
    for stage in ("final","eight"):
        for eligible in (False,True):
            data=np.zeros((n,1+3*3))
            for q,r in sc.items():
                if stage not in r or eligible and not r[stage][0]:continue
                y=data[groups[q]];y[0]+=1
                for j,rule in enumerate(("full","no_support","dense")):y[1+3*j:4+3*j]+=r[stage][1][rule]
            s=data.sum(axis=0);br=boot@data
            row={"n":int(s[0]),"methods":{},"contrasts":{}}
            for j,rule in enumerate(("full","no_support","dense")):
                m=s[1+j*3:4+j*3]/s[0]
                row["methods"][rule]={"full":m[0],"coverage":m[1],"tokens":m[2]}
                if j:
                    idx=1+3*j;row["contrasts"][rule]=dict(delta_pp=100*(s[1]-s[idx])/s[0],ci=interval(100*(br[:,1]-br[:,idx])/br[:,0]))
            metrics[f"{stage}/"+("available" if eligible else "all_fired")]=row
    result=dict(time=times,quality=metrics,actual=load(D/"forecast-seal.json"))
    save(D/"results.json",result)
    print(times["16/1"],times["0/1"],times["16/4"],times["16/0"])
    for key,row in metrics.items():print(key,row)
if __name__=="__main__":main()
