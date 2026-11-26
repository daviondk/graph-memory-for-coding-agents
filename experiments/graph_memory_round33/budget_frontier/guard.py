"""Check a source-length gate on a single, reusable order. No target labels enter routing."""
from collections import Counter, defaultdict
from transfer import B, BUDGET, HERE, SEEDS, load, metrics, nm, np, prefix, R19, route, save, sha, sources
from pathlib import Path

POLICIES = ("cost", "fixed_count", "empty_guard", "count_guard")
CONTRASTS = (("count_guard","cost"), ("count_guard","fixed_count"), ("empty_guard","cost"), ("empty_guard","fixed_count"), ("count_guard","empty_guard"))

def decisions(orders, lengths):
    n_base = len(prefix(orders["cost"], lengths, 256))
    n_head = len(prefix(orders["fixed_count"], lengths, 256))
    return {"cost": "cost", "fixed_count": "fixed_count",
            "empty_guard": "cost" if n_head == 0 < n_base else "fixed_count",
            "count_guard": "cost" if n_head < n_base else "fixed_count"}

def seal():
    output = {}
    inputs = {}
    for i,path in enumerate(sources("test")):
        ranks_path = HERE/f"repeat-ranks-{i}.json.gz"
        ranks = load(ranks_path)
        inputs[str(i)] = sha(ranks_path)
        for r in load(path):
            q = r["q"]
            lengths = [n["token_count"] for n in r["rr"]]
            output[q] = {s: decisions(v, lengths) for s,v in ranks[q].items()}
    assert len(output)==2000
    dst=HERE/"guard-assignments.json.gz"
    save(dst, output)
    save(HERE/"guard-seal.json", {"assignments":sha(dst),"inputs":inputs,
         "script":sha(Path(__file__)),"protocol":sha(HERE/"GUARD_PROTOCOL_RU.md")})

def aggregate(rows):
    ids = sorted(rows)
    means = {k:np.mean([rows[q]["scores"][k] for q in ids], axis=0).tolist() for k in POLICIES}
    by_t = defaultdict(list)
    for q in ids:
        score=rows[q]["scores"]
        by_t[rows[q]["t"]].append(np.concatenate([np.subtract(score[a],score[b]) for a,b in CONTRASTS]))
    ts = sorted(by_t)
    sums = np.asarray([np.sum(by_t[t],axis=0) for t in ts]); sizes = np.array([len(by_t[t]) for t in ts])
    rng=np.random.default_rng(33); n=len(ts); boot=[]
    for _ in range(100):
        idx=rng.integers(n,size=(100,n))+n*np.arange(100)[:,None]
        weights=np.bincount(idx.ravel(),minlength=100*n).reshape(100,n)
        boot.append(weights@sums/(weights@sizes)[:,None])
    limits=100*np.quantile(np.concatenate(boot),[.025,.975],axis=0)
    delta=100*sums.sum(axis=0)/sizes.sum()
    tests={}
    for i,(a,b) in enumerate(CONTRASTS):
        section=slice(i*9,(i+1)*9)
        tests[a+" vs "+b]={"delta_pp":delta[section].tolist(),"ci95_pp":limits[:,section].tolist()}
    return {"n":len(ids),"t":len(ts),"means":means,"vs":tests,
            "proportion_switched":{p:float(np.mean([rows[q]["switches"][p] for q in ids])) for p in POLICIES[2:]}}

def dev():
    source_ranks=load(HERE/"dev-ranks.json.gz"); k=load(HERE/"count-selection.json")["k"]
    hold=set(load(HERE/"selection.json")["hold_t"]); refs=load(R19/"write_transfer/gold-spans.json.gz")
    rows={}
    for p in sources("dev"):
        for r in load(p):
            if r["t"] not in hold:continue
            q=r["q"]; nodes=[nm.pilot.RankedNodeRecord.model_validate(n) for n in r["rr"]]
            lens=[n.token_count for n in nodes]; ranks=source_ranks[q]
            orders=route({"frozen":ranks["a0"],"cost":ranks["a4"]},lens,k)
            choices=decisions(orders,lens); truth=tuple(nm.pilot.SourceSpan.model_validate(v) for v in refs[q])
            values={m:metrics(tuple(nodes[j] for j in orders[m]),truth) for m in ("fixed_count","cost")}
            rows[q]={"t":r["t"],"scores":{m:values[choices[m]] for m in POLICIES},"switches":{p:choices[p]=="cost" for p in POLICIES[2:]}}
    return aggregate(rows)

def main():
    seal()
    selections=load(HERE/"guard-assignments.json.gz"); test={}; hashes={}
    for i in range(8):
        p=HERE/f"repeat-outcomes-{i}.json.gz"; hashes[p.name]=sha(p)
        for q,r in load(p).items():
            assert q not in test
            test[q]=r
    assert test.keys()==selections.keys()
    panels={"dev_hold":dev()}
    for label,seeds in (("seed13",SEEDS[:1]), ("extra4",SEEDS[1:]), ("all5",SEEDS)):
        ids=[str(s) for s in seeds]; rows={}
        for q,r in test.items():
            choices=selections[q]
            scores={p:np.mean([r["seeds"][s][choices[s][p]] for s in ids],axis=0) for p in POLICIES}
            rows[q]={"t":r["t"],"scores":scores,"switches":{p:np.mean([choices[s][p]=="cost" for s in ids]) for p in POLICIES[2:]}}
        panels[label]=aggregate(rows)
    save(HERE/"guard-results.json",{"panels":panels,"seal":sha(HERE/"guard-seal.json"),"score_inputs":hashes})
if __name__=="__main__":main()
