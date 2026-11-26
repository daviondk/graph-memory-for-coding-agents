"""Evaluate working-memory suggestions as a fourth ranked source in a fixed fusion."""
from collections import Counter
import argparse
import json
import tarfile
import numpy as np
from decide import DEFAULT_CACHE,FUSION,HERE,METHODS,TRACES,file_hash,first_chunks,hexdigest,original_runs,read_file,save

def decisions(observation):
    ranks=observation["ranks"]
    proposals=observation["proposals"]
    order=observation["lexical_order"]
    allowed=set(order)
    def score(methods, supplemental=(), flat=False):
        weights=Counter()
        for seq in [ranks[m] for m in methods]:
            for i,p in enumerate(seq,1):
                if p in allowed:weights[p]+=1/(60+i)
        for i,p in enumerate(supplemental,1):
            if p in allowed:weights[p]+=1/(60+(1 if flat else i))
        return max(order,key=lambda p:weights[p])
    return dict(triple=score(FUSION),static_four=score((*FUSION,"embed8")),memory_four=score(FUSION,proposals),
         flat=score(FUSION,proposals,True),reverse=score(FUSION,list(reversed(proposals))),
         static_seven=score(METHODS),memory_eight=score(METHODS,proposals))

def freeze(cache):
    seal=read_file(HERE/"explicit-seal.json")
    assert file_hash(HERE/"explicit-decisions.json.gz")==seal["decisions"]
    explicit=read_file(HERE/"explicit-decisions.json.gz")
    runs,_,_=original_runs(cache)
    with tarfile.open(cache/TRACES) as arc:
        for member in arc:
            if "/traces_" in member.name and member.isfile():
                row=json.load(arc.extractfile(member));q=row["sample_id"]
                if q in runs:runs[q]["raw"]=row["suggested_unread_files"]
    chunks=first_chunks(cache,runs)
    inputs={};choices={};demo={}
    for q,t in sorted(runs.items()):
        avail=chunks[t["repo"].replace("/","__"),t["commit"]]
        possible=set(t["raw"]).union(*t["ranks"].values())
        order=sorted((possible & set(avail))-set(t["reads"])-set(t["given"]))
        def pid(p):return hexdigest((t["repo"]+"\0"+p).encode())
        proposals=list(dict.fromkeys(t["raw"]))
        d=dict(ranks={m:list(map(pid,seq)) for m,seq in t["ranks"].items()},lexical_order=list(map(pid,order)),
                     proposals=list(map(pid,proposals)))
        pick=decisions(d)
        assert pick["triple"]==explicit[q]["chosen"]["fusion"]
        used=set(pick.values())
        receipts={pid(p):[avail[p][0][0],avail[p][0][1],avail[p][1]] for p in order if pid(p) in used}
        assert set(receipts)==used
        inputs[q]=d;choices[q]={"chosen":pick,"receipts":receipts}
        if t["repo"].lower() in {"clap-rs/clap","textualize/rich","pallets/click","pytest-dev/pytest","serde-rs/serde"}:
            paths=set(order)|set(t["reads"])|set(t["strict"])
            demo[q]=dict(repo=t["repo"],commit=t["commit"],paths={pid(p):p for p in sorted(paths)})
    save("demo-paths.json",demo)
    save("fusion-inputs.json.gz",inputs);save("fusion-choices.json.gz",choices)
    names=["FUSION_PROTOCOL_RU.md","explicit-seal.json","fusion.py","fusion-inputs.json.gz","fusion-choices.json.gz","demo-paths.json"]
    save("fusion-seal.json",{n:file_hash(HERE/n) for n in names})
    print("Sealed",len(inputs),"cases and",len(demo),"code demo cases")

def grade(verify):
    seal=read_file(HERE/"fusion-seal.json")
    assert all(file_hash(HERE/n)==v for n,v in seal.items())
    dec=read_file(HERE/"explicit-decisions.json.gz");lab=read_file(HERE/"labels.json.gz")
    inp=read_file(HERE/"fusion-inputs.json.gz");sealed=read_file(HERE/"fusion-choices.json.gz")
    ids=sorted(dec);arms=list(sealed[ids[0]]["chosen"])
    measures={m:[] for m in arms}
    for q in ids:
        choice=decisions(inp[q])
        assert choice==sealed[q]["chosen"]
        for m,p in choice.items():
            hit=p in lab[q]
            recall=len((set(dec[q]["strict"])|{p}) & set(lab[q]))/len(lab[q])
            measures[m].append([hit,recall])
    arr={k:np.array(v,dtype=float) for k,v in measures.items()}
    _,ix=np.unique([dec[q]["repo"] for q in ids],return_inverse=True)
    k=int(ix.max()+1);size=np.bincount(ix);w=np.random.default_rng(54021).multinomial(k,[1/k]*k,size=10000)
    def compare(a,b):
        delta=arr[a]-arr[b];sums=np.zeros((k,2));np.add.at(sums,ix,delta)
        boot=(w@sums)/(w@size)[:,None]*100
        return dict(delta_pp=(delta.mean(0)*100).tolist(),ci95=np.percentile(boot,[2.5,97.5],axis=0).T.tolist(),
            wins=(delta>0).sum(0).tolist(),losses=(delta<0).sum(0).tolist(),switched=sum(sealed[q]["chosen"][a]!=sealed[q]["chosen"][b] for q in ids))
    contrasts=[("memory_four",b) for b in ("static_four","triple","static_seven","flat","reverse")]+[("memory_eight","static_seven")]
    out=dict(n=len(ids),repos=k,columns=["new_hit","total_recall"],means={m:(v.mean(0)*100).tolist() for m,v in arr.items()},
             comparisons={a+"-"+b:compare(a,b) for a,b in contrasts})
    if verify:assert read_file(HERE/"fusion-results.json")==out
    else:save("fusion-results.json",out)
    print(out["comparisons"]["memory_four-static_four"])
if __name__=="__main__":
    cli=argparse.ArgumentParser();cli.add_argument("action",choices=("freeze","grade","verify"))
    cli.add_argument("--cache",default=DEFAULT_CACHE,type=type(DEFAULT_CACHE));opts=cli.parse_args()
    if opts.action=="freeze":freeze(opts.cache)
    else:grade(opts.action=="verify")
