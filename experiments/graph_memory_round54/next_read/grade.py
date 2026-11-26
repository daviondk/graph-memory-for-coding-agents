"""Grade sealed choices using the strict-context evaluator's file relevance labels."""
import argparse
from collections import Counter
import json
import tarfile
import numpy as np
from decide import CORPUS, DEFAULT_CACHE, HERE, METHODS, TRACES, file_hash, hexdigest, read_file, save

def read_labels(cache, decisions):
    with tarfile.open(cache/TRACES) as arc:
        detail, = [m for m in arc if m.name.endswith("trajectory_details.jsonl")]
        labels = {}
        for line in arc.extractfile(detail):
            row=json.loads(line)
            q=row["sample_id"]
            if q in decisions:
                trace=decisions[q]
                assert (row["repo"],row["base_commit"],row["task_type"]) == (trace["repo"],trace["commit"],trace["task"])
                labels[q]=set(row["gold_files"])
    with tarfile.open(cache/CORPUS,"r|zst") as arc:
        for member in arc:
            if member.name.endswith("Qwen3-Embedding-4B_details.jsonl"):
                check={r["sample_id"]:set(r["gold_files"]) for r in map(json.loads,arc.extractfile(member))}
                assert all(check[q] == v for q,v in labels.items())
                break
        else:
            raise AssertionError("Missing independent source of golds")
    assert set(labels)==set(decisions) and all(labels.values())
    return {q:sorted(hexdigest((decisions[q]["repo"]+"\0"+p).encode()) for p in gold) for q,gold in labels.items()}

def metrics(old, chosen, gold):
    union=old | ({chosen} if chosen else set())
    return [float(chosen in gold),len(gold & union)/len(gold),float(gold<=union),float(bool(gold & union))]

NAMES=["new_hit","total_recall","all_gold","any_gold"]
def analyze(decisions, labels):
    keys=sorted(decisions);methods=sorted(decisions[keys[0]]["chosen"])+["strict"]
    values={}; repo=[]; groups={}
    for i,q in enumerate(keys):
        row=decisions[q];old=set(row["strict"]);gold=set(labels[q]);repo.append(row["repo"])
        choice=row["chosen"]|{"strict":None}
        assert not set(row["opened"])&set(row["receipts"])
        for p in row["chosen"].values():
            lo,hi,digest=row["receipts"][p]
            assert p and hi>=lo and len(digest)==64
        groups.setdefault(row["task"],[]).append(i)
        groups.setdefault("proposal" if row["new_suggestions"] else "no_proposal",[]).append(i)
        for m in methods:values.setdefault(m,[]).append(metrics(old,choice[m],gold))
    groups["all"]=list(range(len(keys)))
    vals={k:np.array(v) for k,v in values.items()}
    clusters,idx=np.unique(repo,return_inverse=True);k=len(clusters)
    rng=np.random.default_rng(54021); weights=rng.multinomial(k,[1/k]*k, size=10000)
    size=np.bincount(idx,minlength=k)
    def compare(a,b):
        diff=vals[a]-vals[b]
        sums=np.zeros((k,len(NAMES)));np.add.at(sums,idx,diff)
        boot=(weights@sums)/(weights@size)[:,None]*100
        output={}
        for j,name in enumerate(NAMES):
            output[name]=dict(delta_pp=float(diff[:,j].mean()*100),
                ci95=np.percentile(boot[:,j],[2.5,97.5]).tolist(),wins=int((diff[:,j]>0).sum()),losses=int((diff[:,j]<0).sum()))
        return output
    summary={}
    for g,ind in groups.items():
        summary[g]=dict(n=len(ind),rates_pct={m:dict(zip(NAMES,(vals[m][ind].mean(axis=0)*100).tolist())) for m in methods})
    comparisons={f"{a}-{b}":compare(a,b) for a,b in [("memory","fusion"),("confirmed","fusion"),
             ("memory","embed4"),("memory","embed8"),("fusion","strict"),("memory","strict")]+[("memory_"+m,m) for m in METHODS]}
    return dict(n=len(keys),repos=len(clusters),sample_sizes=dict(Counter(repo)),
                proposed=sum(bool(d["original_suggestions"]) for d in decisions.values()),
                valid=sum(bool(d["new_suggestions"]) for d in decisions.values()),
                changed=sum(d["chosen"]["memory"]!=d["chosen"]["fusion"] for d in decisions.values()),
                missing_refs=sum(d["missing"] for d in decisions.values()),
                total_refs=sum(d["original_suggestions"] for d in decisions.values()),subsets=summary,paired=comparisons)
def main(cache,verify):
    seal=read_file(HERE/"decision-seal.json")
    assert seal["decisions"]==file_hash(HERE/"decisions.json.gz") and seal["code"]==file_hash(HERE/"decide.py")
    assert seal["protocol"]==file_hash(HERE/"PROTOCOL_RU.md")
    dec=read_file(HERE/"decisions.json.gz")
    if verify:
        out=analyze(dec,read_file(HERE/"labels.json.gz"))
        assert out==read_file(HERE/"results.json")
    else:
        labels=read_labels(cache,dec)
        save("labels.json.gz",labels)
        out=analyze(dec,labels)
        save("results.json",out)
    print(out["n"],out["repos"],out["proposed"],out["valid"],out["changed"],out["paired"]["memory-fusion"])
if __name__=="__main__":
    cli=argparse.ArgumentParser()
    cli.add_argument("--cache",type=__import__("pathlib").Path,default=DEFAULT_CACHE)
    cli.add_argument("--verify",action="store_true")
    args=cli.parse_args();main(args.cache,args.verify)
