"""Score the frozen uniform-seed ablation; collect per-task discordance and interpretable edge evidence."""
import collections
import math
import random
from pathlib import Path
import grade
import rank

ROOT = Path(__file__).resolve().parent

def summary(rs, method):
    ranks = [v["rank"][method] for v in rs]
    return {"h1":sum(i==1 for i in ranks), "h3":sum(0<i<=3 for i in ranks),
            "mrr":sum(1/i for i in ranks if i)/len(rs)}

def pairs(data):
    n = len(data)
    by = collections.defaultdict(list)
    for r in data:
        by[r["iid"]].append(int(r["rank"]["graph"]==1)-int(r["rank"]["strong"]==1))
    delta = {k:sum(v) for k,v in by.items() if sum(v)}
    active = list(delta.values())
    observed = abs(sum(active))
    # Exact two-sided sign flipping whole task effects under exchangeability.
    import itertools
    signs = itertools.product((-1,1), repeat=len(active))
    extreme = sum(abs(sum(a*b for a,b in zip(sig,active))) >= observed for sig in signs)
    return {"tasks":len(by), "nonzero_tasks": delta, "enumerated": 2**len(active),
            "two_sided_task_sign_flip": extreme / 2**len(active), "anchors":n}

def by_repo(rs):
    bins = collections.defaultdict(list)
    for r in rs:
        bins[r["repo"]].append(r)
    return {repo:{"n":len(group), **{m:summary(group,m)["h1"] for m in ("strong","graph","uniform","shuffled")}}
            for repo,group in sorted(bins.items())}

def reasons(item, ranked, target):
    symbols={p:{w.lower() for w in rank.IDENT.findall(doc["snip"])
                if len(w)>=4 and w.lower() not in rank.STOP} for p,doc in item["docs"].items()}
    df=collections.Counter(w for bag in symbols.values() for w in bag)
    n=len(symbols)
    top=ranked["graph"][0]
    edges=[]
    for seed in ranked["strong"][:3]:
        if top==seed:continue
        shared=sorted((w for w in symbols[seed] & symbols[top] if 1<df[w]<=max(2,math.ceil(n*.55))),
                      key=lambda w:(df[w],w))
        if shared:edges.append({"seed":seed,"observed_terms":shared[:8],"total_shared":len(shared)})
    return {"id":item["id"],"repo":item["repo"], "literal":item["key"]["literal"], "scope":item["key"]["scope"],
            "strong":ranked["strong"][0],"graph":top,"correct":top in target,
            "top_seeds":ranked["strong"][:3],"edge_evidence":edges}

def main(panel):
    rank.D=panel
    inp={r["id"]:r for r in rank.load("inputs.json.gz")}
    fs={r["id"]:r["rank"] for r in rank.load("frozen_rankings.json.gz")}
    uni=rank.load("uniform_rankings.json.gz")
    lock=rank.load("uniform.lock.json")
    assert all(rank.h((panel/n).read_bytes()) == lock[n] for n in ("inputs.json.gz","uniform_rankings.json.gz"))
    cs=rank.load("per_anchor_scores.json.gz")
    for r in cs:
        u=uni[r["id"]];assert set(u)==set(inp[r["id"]]["docs"])
        target=set(r["targets"]);r["rank"]["uniform"]=next((i+1 for i,p in enumerate(u) if p in target),0)
    records=[];ds={}
    for end in ("next","patch"):
        group=[r for r in cs if r["which"]==end]
        ds[end] = {"scores":{m:summary(group,m) for m in ("strong","graph","uniform","shuffled")},
                   "task_test":pairs(group),"by_repo":by_repo(group)}
        for r in group:
            if (r["rank"]["strong"]==1) != (r["rank"]["graph"]==1):
                records.append({"endpoint":end,**reasons(inp[r["id"]],fs[r["id"]],set(r["targets"]))})
    rank.dump("diagnostics.json", ds);rank.dump("discordances.json",records)
    print(panel.name,[(ep, v["scores"],v["task_test"]["two_sided_task_sign_flip"]) for ep,v in ds.items()])

if __name__=="__main__":
    for panel in (ROOT,ROOT/"replication"):
        main(panel)
