"""Independently decode Git trees, sum votes over primitive preceding events, and audit the published rankings."""
import argparse
import gzip
import hashlib
import json
import math
import os
import random
import re
import statistics
import subprocess
from collections import Counter, defaultdict
from functools import lru_cache
from pathlib import Path

HERE = Path(__file__).resolve().parent
G1 = HERE.parents[1] / "graph_memory_round1/git_prediction"
DEFAULT_MIRRORS = Path("D:/CodexResearch/x20-r55-partner-clock")
DEFAULT_OLD = Path("D:/CodexResearch/x20-bench-workspace/work/graph_memory_round1/git_prediction")
TOL = 1e-12


def read(p):
    raw = p.read_bytes()
    return json.loads(gzip.decompress(raw) if p.suffix == ".gz" else raw)


def git(repo, *args):
    return subprocess.check_output(["git", "-C", str(repo), *args], env={**os.environ, "GIT_NO_LAZY_FETCH":"1"})


def check_git(repo, pin, events):
    """Compare consecutive first-parent trees. Ask cat-file only about tree objects."""
    boundary, head, n = pin
    assert n == len(events)
    lines = git(repo, "log", "--first-parent", "--format=%H %T %P", boundary+".."+head).decode().splitlines()
    previous_sha = boundary
    previous_tree = git(repo, "rev-parse", boundary+"^{tree}").strip()
    stream = subprocess.Popen(["git","-C",str(repo),"cat-file","--batch"],stdin=subprocess.PIPE,stdout=subprocess.PIPE,
                              env={**os.environ,"GIT_NO_LAZY_FETCH":"1"})
    tree_reads = 0
    @lru_cache(maxsize=None)
    def entries(oid):
        nonlocal tree_reads
        if not oid:
            return {}
        tree_reads += 1
        stream.stdin.write(oid+b"\n")
        stream.stdin.flush()
        obj, kind, size = stream.stdout.readline().split()
        assert obj == oid and kind == b"tree"
        buf = stream.stdout.read(int(size))
        assert stream.stdout.read(1) == b"\n"
        children = {}
        start = 0
        while start < len(buf):
            stop = buf.index(b"\0",start)
            mode,name = buf[start:stop].split(b" ",1)
            children[name] = mode, buf[stop+1:stop+21].hex().encode()
            start = stop + 21
        assert start == len(buf)
        return children
    def delta(before, after, prefix=b""):
        if before == after:
            return
        left, right = entries(before), entries(after)
        for name in set(left)|set(right):
            old, new = left.get(name), right.get(name)
            if old == new:
                continue
            p = prefix+name
            dir0, dir1 = old and old[0] == b"40000", new and new[0] == b"40000"
            if dir0 or dir1:
                yield from delta(old[1] if dir0 else None, new[1] if dir1 else None, p+b"/")
            if p.endswith(b".py"):
                if new and not dir1:
                    yield False, p.decode("utf8","surrogateescape")
                elif old and not dir0:
                    yield True, p.decode("utf8","surrogateescape")
    touched_count = removed_count = 0
    try:
        for event, line in zip(events,reversed(lines),strict=True):
            sha, tree, first_parent, *_ = line.split()
            assert sha == event[0] and first_parent == previous_sha
            changed = set(delta(previous_tree, tree.encode()))
            assert changed == {(False,p) for p in event[1]} | {(True,p) for p in event[2]}
            touched_count += len(event[1])
            removed_count += len(event[2])
            previous_sha, previous_tree = sha, tree.encode()
        assert head == previous_sha
    finally:
        stream.stdin.close()
        stream.stdout.close()
        assert stream.wait(timeout=10) == 0
    return dict(commits=n, touched=touched_count, removed=removed_count, unique_tree_objects=tree_reads)


@lru_cache(maxsize=None)
def path_terms(p):
    *dirs, base = p.lower().split("/")
    stem = base[:-3]
    return set(re.findall("[a-z]+|[0-9]+", stem)), set(dirs), re.sub(r"(^tests?_|_tests?$)", "", stem)


def affinity(a,b):
    def similarity(left,right):
        return len(left&right)/max(1,len(left|right))
    at, ad, astem = path_terms(a)
    bt, bd, bstem = path_terms(b)
    return math.exp(2.5*int(bool(astem) and astem==bstem)+1.3*similarity(at,bt)+0.7*similarity(ad,bd))


def votes(a_times,b_times,providers,sizes,i,models):
    common = a_times & b_times
    joint = []
    while common:
        lowest = common & -common
        j = lowest.bit_length()-1
        assert j < i
        joint.append(j)
        common ^= lowest
    if not joint:
        return {}
    raw = [1/(sizes[j]-1) for j in joint]
    result = dict(unit=math.fsum(raw),
                  exposure=math.fsum(w/sizes[j] for j,w in zip(joint,raw)),
                  jaccard=len(joint)/(a_times|b_times).bit_count(),
                  ochiai=len(joint)/math.sqrt(a_times.bit_count()*b_times.bit_count()))
    timelines = {"xor":a_times^b_times, "anchor":a_times, "candidate":b_times}
    for model in models:
        if "_" not in model:
            continue
        typ,half = model.split("_")
        if typ == "global":
            elapsed = [i-j for j in joint]
        else:
            elapsed = [(timelines[typ]>>(j+1)).bit_count() for j in joint]
        result[model] = math.fsum(w * 2**(-n/int(half)) for n,w in zip(elapsed,raw))
    providers.update(joint)
    return result


def metrics(rank,target):
    good = set(target)
    hit = [k for k,p in enumerate(rank,1) if p in good]
    return [len(hit)/len(good),int(1 in hit),1/min(hit) if hit else 0]


def restore(panel):
    content = read(HERE/(panel+"-ranks.json.gz"))
    if isinstance(content,list):
        return content
    def decode(r):
        paths = content["paths"][r["repo"]]
        return {**r,"anchor":paths[r["anchor"]],"targets":[paths[j] for j in r["targets"]],
                "ranked":{m:[paths[j] for j in ids] for m,ids in r["ranked"].items()}}
    return [decode(r) for r in content["rows"]]


def close(x,y):
    return math.isclose(x,y,rel_tol=TOL,abs_tol=TOL)


def check_panel(panel,root,old_root,check_trees):
    from clock import Memory  # system under test, used only to compare raw edge scores
    selected = read(HERE/"selection.json")
    events = read(HERE/(panel+"-events.json.gz"))
    pins = read(HERE/(panel+"-pins.json"))
    answer = read(HERE/(panel+"-results.json"))
    saved = {(r["repo"],r["i"]):r for r in restore(panel)}
    count = Counter()
    drift = defaultdict(int)
    mismatch_examples = []
    tree_info, summary = {}, {}
    max_edge_error = 0.
    by_model_ranks = Counter()
    for repo,history in events.items():
        if check_trees:
            mirror = root / repo.replace("/","__")
            if panel == "development":
                folders = [old_root/(tag+"_mirrors")/repo.replace("/","__") for tag in ("transfer","exposure")]
                [mirror] = [p for p in folders if p.exists()]
            tree_info[repo] = check_git(mirror,pins[repo],history)
        active = set()
        freq, touched_mask, last_delete = Counter(), Counter(), {}
        sizes = [len(t) for _,t,_ in history]
        outputs = defaultdict(list)
        if repo in answer["repos"]:
            models = list(answer["repos"][repo]["means"])
            if panel == "development":
                models = [m for m in models if "_" not in m or m in selected["clocks"].values()]
        else:
            models = ["prior"]
        engine = Memory(models)
        for i,(sha,touched,removed) in enumerate(history):
            if i >= len(history)//2 and 2 <= sizes[i] <= 20:
                r = saved.pop((repo,i))
                assert r["sha"] == sha and touched == sorted(set(touched))
                idx = int(hashlib.sha256((repo.replace("/","__")+":"+str(i)).encode()).hexdigest(),16)
                a = touched[idx % len(touched)]
                assert (a,r["targets"],r["reachable"]) == (r["anchor"],[p for p in touched if p != a],len(active&set(r["targets"])))
                assert engine.active == active and engine.frequency == freq
                allpaths = sorted(active-{a})
                prior = {p:affinity(a,p)*math.sqrt(1+freq[p]) for p in allpaths}
                mass = math.fsum(prior.values())
                prior = {p:4*v/mass for p,v in prior.items()}
                raw, providers = {}, set()
                old_supports = set()
                for p in allpaths:
                    raw[p] = votes(touched_mask[a],touched_mask[p],providers,sizes,i,models)
                    edge = engine.edges.get(a,{}).get(p)
                    assert bool(raw[p]) == bool(edge)
                    if not edge:
                        continue
                    dead = max(last_delete.get(p,-1), last_delete.get(a,-1))
                    if dead >= 0 and (touched_mask[a]&touched_mask[p]) & ((1<<(dead+1))-1):
                        old_supports.add(p)
                    for model in models:
                        if model == "prior":
                            continue
                        actual = engine.edge_score(model,a,p,edge,i)
                        val = raw[p][model]
                        max_edge_error = max(max_edge_error,abs(actual-val))
                        assert close(actual,val), (repo,i,a,p,model,actual,val)
                        count["raw_scores"] += 1
                count["queries"] += 1
                count["queries_exposed_to_pre_delete_support"] += bool(old_supports)
                count["historical_support_events_per_query_summed"] += len(providers)
                scale = math.fsum(raw[p].get("unit",0.) for p in allpaths)
                for model in models:
                    vals = {p:raw[p].get(model,0.) for p in allpaths}
                    total = math.fsum(vals.values())
                    score = {p:prior[p] + (v/total*scale if total else 0.) for p,v in vals.items()}
                    direct = sorted(allpaths,key=lambda p:(-score[p],-freq[p],p))[:5]
                    logged = r["ranked"][model]
                    assert len(direct)==len(logged)==len(set(logged)) and set(logged)<=set(allpaths)
                    count["rank_lists"] += 1
                    by_model_ranks[model] += 1
                    if logged != direct:
                        assert all(close(score[x],score[y]) for x,y in zip(logged,direct))
                        count["rank_lists_reordered_near_tie"] += 1
                        drift[model] += 1
                        if set(direct) != set(logged):
                            count["changed_top5_set_near_tie"] += 1
                        if metrics(direct,r["targets"])!=metrics(logged,r["targets"]):
                            count["changed_metric_vector_near_tie"] += 1
                        if len(mismatch_examples)<3:
                            mismatch_examples.append([repo,i,model,logged,direct])
                    outputs[model].append(metrics(logged,r["targets"]))
            engine.observe(touched,removed,i)
            active.difference_update(removed)
            active.update(touched)
            freq.update(touched)
            for p in removed:
                last_delete[p] = i
            if 1 <= len(touched) <= 20:
                for p in touched:
                    touched_mask[p] |= 1<<i
        if outputs:
            summary[repo] = {}
            for m,rows in outputs.items():
                mean = [statistics.fmean(c) for c in zip(*rows)]
                assert len(rows) == answer["repos"][repo]["n"]
                assert all(close(x,y) for x,y in zip(mean,answer["repos"][repo]["means"][m]))
                summary[repo][m] = mean
    assert not saved and count["queries"] == answer["n"]
    assert set(events)-set(summary) == set(answer["no_queries"])
    macro = {model:[statistics.fmean(col) for col in zip(*(group[model] for group in summary.values()))]
             for model in next(iter(summary.values()))}
    assert all(close(v, answer["macro"][m][i]) for m,ordered in macro.items() for i,v in enumerate(ordered))
    candidate = "anchor_8" if panel == "replication" else selected["clocks"]["xor"]
    control = answer["primary"]["control"]
    paired = [summary[repo][candidate][0]-summary[repo][control][0] for repo in sorted(summary)]
    positive, negative = sum(x>TOL for x in paired),sum(x< -TOL for x in paired)
    n = positive+negative
    probability = min(1.,2*(sum(math.comb(n,k) for k in range(min(positive,negative)+1))/2**n))
    assert close(statistics.fmean(paired),answer["primary"]["delta"]) and close(probability, answer["primary"]["sign_p"])
    assert [positive,len(paired)-n,negative] == answer["primary"]["signs"]
    rng = random.Random(55013)
    replicates = sorted(statistics.fmean(rng.choices(paired,k=len(paired))) for _ in range(20000))
    assert all(close(v,replicates[idx]) for idx,v in zip([499,19499],answer["primary"]["interval"]))
    return dict(counts=dict(count), checked_ranks_by_method=dict(by_model_ranks), near_ties_by_method=dict(drift),
                examples=mismatch_examples, maximum_raw_score_disagreement=max_edge_error,git=tree_info,
                macro_and_primary_verified=True)


def g1():
    out = {}
    dev = read(HERE/"development-results.json")["repos"]
    for tag in ("transfer","exposure"):
        previous = read(G1/(tag+"_run")/"summary.json")["evaluation"]["per_repo"]
        pairs = {"prior":"lexical", "unit":"unit_smoothed"}
        if tag=="exposure":
            pairs["exposure"] = "exposure_matched"
        top = 0.
        for r,x in previous.items():
            repo = r.replace("__","/")
            assert x["n"] == dev[repo]["n"] and close(x["coverage"],dev[repo]["reachable"])
            for m,old in pairs.items():
                for j,metric in enumerate(("r5","h1")):
                    err = abs(x["ranking"][old][metric] - dev[repo]["means"][m][j])
                    top = max(top,err)
        assert top<TOL
        out[tag] = dict(repositories=len(previous),metrics_compared=len(previous)*len(pairs)*2,max_difference=top)
    return out


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--mirrors",type=Path,default=DEFAULT_MIRRORS)
    parser.add_argument("--old-mirrors",type=Path,default=DEFAULT_OLD)
    parser.add_argument("--no-git",action="store_true",help="Validate the checked-in primitive event projections and ranks only.")
    args=parser.parse_args()
    frozen = read(HERE/"selection.json")
    for n,h in frozen["hashes"].items():
        assert hashlib.sha256((HERE/n).read_bytes()).hexdigest() == h
    panel_names = ["development","external","replication"]
    rosters = [set(read(HERE/(n+"-pins.json"))) for n in panel_names]
    assert not any(a&b for i,a in enumerate(rosters) for b in rosters[i+1:])
    result = {"panels":{}, "g1":g1(), "git_trees_checked":not args.no_git, "tolerance":TOL}
    for n in panel_names:
        result["panels"][n] = check_panel(n,args.mirrors,args.old_mirrors,not args.no_git)
        print(n,result["panels"][n]["counts"],flush=True)
    if not args.no_git:
        (HERE/"independent-audit.json").write_bytes((json.dumps(result,sort_keys=True,indent=2)+"\n").encode())


if __name__=="__main__":
    main()
