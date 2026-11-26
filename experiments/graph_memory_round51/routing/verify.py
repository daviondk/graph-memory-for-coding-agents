"""Offline independent replay of the four Hotpot policies and scores."""
import argparse
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import struct
import re

D=Path(__file__).resolve().parent
T=D.parent/"transfer"
spec=importlib.util.spec_from_file_location("prior_verifier",T/"verify.py")
base=importlib.util.module_from_spec(spec)
spec.loader.exec_module(base)

def get(name):
    b=(D/name).read_bytes()
    return json.loads(gzip.decompress(b) if name.endswith(".gz") else b)

def hash_(name):
    return hashlib.sha256((D/name).read_bytes()).hexdigest()

def verify():
    check=get("registration.json")
    assert check["protocol"]==hash_("PROTOCOL_RU.md") and check["code"]==hash_("study.py")
    assert check["transfer"]==base.sha(T/"SHA256.json")
    refs=get("contexts.json.gz");g=get("gold.json.gz");out=get("outcomes.json.gz");rank=get("orders.json.gz")
    flags=get("flags.json.gz");choices=get("router-choices.json.gz");ans=get("answers.json.gz");prompts=get("prompts.json.gz")
    assert set(refs)==set(g)==set(out)==set(rank)==set(flags)==set(choices)
    assert len(refs)==len({v["cluster"] for v in refs.values()})==1280
    assert not set(refs)&set(json.loads((T/"panel.json").read_bytes())["order"])
    assert get("route-seal.json")["choices"]==hash_("router-choices.json.gz")
    assert get("answer-seal.json")["answers"]==hash_("answers.json.gz")
    assert set(prompts)==set(ans)
    for k,ts in prompts.items():
        assert hashlib.sha256(struct.pack(f"<{len(ts)}I",*ts)).hexdigest()==k
    results=get("results.json");sums={a:[0.]*4 for a in ("router","adaptive","dense","linked_dense")}
    tail=get("reader-boundaries.json")["tail"]
    changed=0
    diffs=[]
    for q,c in refs.items():
        r=rank[q];gg=g[q];ts=re.findall("[a-z]+",gg["question"].lower())
        comparative={"both","either","same","different","than","earlier","later","older","younger","longer","shorter","larger","smaller","taller","higher","lower","more","fewer","most","least"}
        yes_no={"are","were","do","did","have","has","is","was"}
        flag=bool(comparative.intersection(ts) or (ts and ts[0] in yes_no and {"and","or"}.intersection(ts)))
        assert flag==flags[q]==out[q]["flag"]
        order=r["order"];scores=r["scores"];edges=set(r["edges"])
        assert len(order)==len(set(order)) and r["seed"] not in order
        assert all(scores[str(a)]>=scores[str(b)] for a,b in zip(order,order[1:]))
        dense=order[0];linked=next((i for i in order if i in edges),dense)
        gate=linked if scores[str(dense)]-scores[str(linked)]<=0.04178261756896973 else dense
        selected={"dense":dense,"linked_dense":linked,"adaptive":gate,"router":dense if flag else linked}
        cc=dict(c["refs"]);cc["router"]=cc["dense" if flag else "linked_dense"]
        assert choices[q]=={"address":selected["router"],"arm":("dense" if flag else "linked_dense")}
        actual=selected["router"]!=linked
        assert actual==out[q]["changed"]
        changed+=actual
        sequences=[]
        for a,idx in selected.items():
            dest,k,L=cc[a];assert idx==dest
            tt=prompts[k];assert len(tt)==L and tt[-len(tail):]==tail
            sequences.append(tt)
            em,f1=base.answer_metrics(ans[k]["answer"],gg["answer"])
            gold_titles=set(gg["support_titles"])
            hit=gold_titles&{gg["titles"][i] for i in [idx,r["seed"]]}
            values=[em,f1,float(hit==gold_titles),len(hit)/len(gold_titles)]
            assert all(abs(x-y)<1e-12 for x,y in zip(values,out[q]["arms"][a],strict=True))
            for j,v in enumerate(values):sums[a][j]+=v
        prefix=len(sequences[0])-c["n"]-len(tail)
        assert len({len(tt) for tt in sequences})==1 and all(tt[:prefix]==sequences[0][:prefix] for tt in sequences)
        diffs.append(out[q]["arms"]["router"][1]-out[q]["arms"]["linked_dense"][1])
    assert changed==results["switched"]
    p=results["paired"]["router-linked_dense"]
    assert p["wins"][1]==sum(x>1e-12 for x in diffs) and p["losses"][1]==sum(x< -1e-12 for x in diffs)
    for a,v in sums.items():
        assert all(abs(100*x/len(refs)-y)<1e-9 for x,y in zip(v,results["means_pct"][a],strict=True))
    for k,answer in get("replay.json").items():assert answer==ans[k]
    timings=get("timing-events.json.gz")
    assert {v[0] for v in timings if not v[1]}==set(ans) and len(timings)==len(ans)+32
    print(f"Verified 1280 visible-question flags, all 5120 address choices and scores, {len(prompts)} prompt hashes and {len(timings)} server timings.")

if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--manifest",action="store_true")
    args=parser.parse_args()
    if args.manifest:
        digests=get("SHA256.json")
        assert set(digests)=={p.name for p in D.iterdir() if p.is_file() and p.name!="SHA256.json"}
        assert all(hash_(name)==digest for name,digest in digests.items())
    verify()
