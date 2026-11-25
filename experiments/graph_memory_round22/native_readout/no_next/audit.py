"""Paired audit on frozen R20 ISETrace ranks. Pure Python; never loads encoders."""
from collections import defaultdict
import gzip
import json
import math
from pathlib import Path
import statistics
import sys

import lock

sys.path.insert(0, str(lock.HERE.parent))
import holm_audit as bit

ARMS = ("degree", "factor")
REFS = ("rgcn", "no_next")


def locked():
    plan = bit.read(lock.HERE / "input-plan.json")
    assert lock.sha(lock.HERE / "input-plan.json") == "fe9672a8990184d634e1bc73833431c49d6bc8ba6adca15c1ba9ae85bda35dbf"
    for path, wanted in plan["sha256"].items():
        assert lock.sha(lock.WORK / path) == wanted, path
    assert lock.sha(lock.C / "forecast-seal.json") == lock.PAPER_SEAL


def checkout(folder, filename, receipt, files):
    path = folder / filename
    digest = lock.sha(path)
    assert digest == receipt[filename], path
    files[str(path.relative_to(lock.WORK))] = digest
    return bit.index(bit.read(path))


def graph_order(items, units, ids):
    result = []
    for item in items:
        j = ids[item["node_id"]]
        assert bit.spans(item) == bit.spans(units[j])
        assert item["token_count"] == units[j]["token_count"] > 0
        result.append(j)
    return result


def save(path, data):
    text = json.dumps(data, sort_keys=True, indent=None if path.suffix == ".gz" else 2,
                      ensure_ascii=False, allow_nan=False) + "\n"
    content = text.encode()
    if path.suffix == ".gz":
        content = gzip.compress(content, compresslevel=6, mtime=0)
    path.write_bytes(content)
    return lock.sha(path)


def paired(rows, trajectory_count, base, arm, metric):
    diffs = [r["arms"][arm][metric] - r["arms"][base][metric] for r in rows]
    n = len(rows)
    d = statistics.fmean(diffs)
    grouped = defaultdict(list)
    for r, delta in zip(rows, diffs, strict=True):
        grouped[r["t"]].append(delta-d)
    g = len(grouped)
    assert g == trajectory_count
    se = math.sqrt(g/(g-1) * math.fsum(math.fsum(x)**2 for x in grouped.values())) / n
    assert se > 0
    z = d/se
    return dict(arm=arm, reference=base, metric=metric, query_count=n, trajectory_count=g,
                arm_mean=statistics.fmean(r["arms"][arm][metric] for r in rows),
                reference_mean=statistics.fmean(r["arms"][base][metric] for r in rows),
                n_better=sum(x > 1e-12 for x in diffs), n_worse=sum(x < -1e-12 for x in diffs),
                delta_pp=d*100, se_pp=se*100, z=z, two_sided_p=math.erfc(abs(z)/math.sqrt(2)))


def family(contrasts, key):
    n = len(contrasts)
    critical = statistics.NormalDist().inv_cdf(1-.05/(2*n))
    p_adj = 0
    for i, row in enumerate(sorted(contrasts, key=lambda v: v["two_sided_p"])):
        p_adj = max(p_adj, min(1, (n-i)*row["two_sided_p"]))
        row[key] = dict(size=n, holm_rank=i+1, holm_p=p_adj, reject=p_adj <= .05,
                        simultaneous_bonf_ci_pp=[row["delta_pp"] + s*critical*row["se_pp"] for s in (-1,1)])


def go():
    locked()
    seals = {folder:bit.read(folder/name)[key] for folder,name,key in (
        (lock.D,"forecast-seal.json","forecasts"), (lock.G,"forecast-seal.json","forecasts"),
        (lock.C,"forecast-seal.json","forecasts"), (lock.F,"hash64-seal.json","files"))}
    old_rows = bit.read(lock.F / "metrics-test-rows.json.gz")
    old_rows["rgcn"] = bit.read(lock.F / "metrics-full-rows.json.gz")["rgcn"]
    gold = bit.read(lock.GOLD)
    true_t = {r["q"]:r["t"] for r in bit.read(lock.D / "split.json.gz")["test"]}
    assert set(gold)==set(true_t) and len(true_t)==2000
    generated = {}
    out = []
    checked = 0
    candidates = 0
    discrepancy = 0
    for i in range(8):
        tables = [checkout(folder,name,seals[folder],generated) for folder,name in (
            (lock.D, f"forecasts-main-{i}.json.gz"), (lock.F, f"hash64-ranks-{i}.json.gz"),
            (lock.G, f"forecasts-rgcn-{i}.json.gz"), (lock.C, f"forecasts-rgcn-{i}.json.gz"))]
        dense, compact, full, no_next = tables
        assert all(set(tab) == set(dense) for tab in tables)
        for q, view in dense.items():
            t = view["t"]
            assert all(tab[q]["t"]==t for tab in tables) and t==true_t[q]
            units = view["rr"]
            ids = {node["node_id"]:j for j,node in enumerate(units)}
            m = len(ids)
            assert m == len(units) and m>0
            candidates += m
            orders = {arm:compact[q]["ranks"][arm] for arm in ARMS}
            orders["rgcn"] = graph_order(full[q]["rr"], units, ids)
            orders["no_next"] = graph_order(no_next[q]["rr"], units, ids)
            assert all(sorted(v) == list(range(m)) for v in orders.values())
            masks, total = bit.gold_bitmasks(units, gold[q])
            costs = [v["token_count"] for v in units]
            values = {name:bit.metrics(order,costs,masks,total) for name,order in orders.items()}
            for name in (*ARMS, "rgcn"):
                assert t==old_rows[name][q]["t"]
                for k, x in values[name].items():
                    err = abs(x-old_rows[name][q][k])
                    discrepancy = max(discrepancy,err)
                    assert err<1e-12
                    checked += 1
            out.append(dict(q=q,t=t,candidate_count=m,arms=values,
                            delta_no_next={a:{k:values[a][k]-values["no_next"][k] for k in bit.METRICS} for a in ARMS}))
    assert len(out)==len({r["q"] for r in out})==2000 and candidates==249089
    out.sort(key=lambda v:v["q"])
    g = len({r["t"] for r in out})
    assert g == 1207
    per_query = save(lock.HERE / "per-query.json.gz", out)
    previous = {(r["arm"],r["metric"]):r for r in bit.read(lock.HERE.parent / "holm-audit.json")["rows"]}
    results = [paired(out,g,ref,arm,metric) for ref in REFS for arm in ARMS for metric in bit.METRICS]
    for reference in REFS:
        family([r for r in results if r["reference"]==reference],"within_reference_16")
    for r in results:
        if r["reference"]=="rgcn":
            prior = previous[r["arm"],r["metric"]]
            assert abs(r["delta_pp"]-prior["mean_difference_pp"])<1e-10
            assert abs(r["within_reference_16"]["holm_p"]-prior["holm_adjusted_p"])<1e-10
    family(results,"both_references_32")
    fits = {}
    for key, path in (("rgcn",lock.G),("no_next",lock.C)):
        cp = bit.read(path/"checkpoint.json")
        assert all(e["train_task_count"]==3894 and e["dev_task_count"]==500 for e in cp["records"])
        assert cp["trainer"]["random_seed"]==13 and lock.sha(path/"best.pt")==cp["sha"]
        fits[key] = dict(arm=cp["model"]["ablation_name"],epoch=cp["epoch"],seed=13,train=3894,dev=500,
                         weights=cp["sha"],relations=cp["model"]["enabled_provenance_relations"])
    assert set(fits["rgcn"]["relations"])-set(fits["no_next"]["relations"])=={"content.next"}
    assert set(fits["no_next"]["relations"])<=set(fits["rgcn"]["relations"])
    result = dict(query_weighted=True,cluster="trajectory",G=g,N=len(out),paired_candidates=candidates,
                  source_intervals_and_costs_agree_across_rgcn_and_dense=True,permutations_verified=4*len(out),
                  recomputed_scalars=4*8*len(out),old_scalars_crosschecked=checked,max_abs_old_discrepancy=discrepancy,
                  fit=fits,forecasts_sha256=generated,per_query_sha256=per_query,
                  source_lock=lock.sha(lock.HERE/"input-plan.json"),code_sha256=lock.sha(Path(__file__)),
                  procedure="Two-sided paired cluster influence Gaussian SE, G/(G-1) correction; Holm separately per reference (16) or jointly (32). Normal Bonferroni simultaneous confidence bands; each query weighted equally.",
                  caveat="Single training seed, benchmark already explored. Families do not account for all prior selection.",
                  contrasts=results)
    digest=save(lock.HERE/"contrasts.json",result)
    print("CONTRASTS SHA",digest,flush=True)
    for r in results:
        if r["reference"]=="no_next" or r["both_references_32"]["reject"]:
            print(r["reference"],r["arm"],r["metric"],round(r["delta_pp"],5),
                  round(r["within_reference_16"]["holm_p"],6),round(r["both_references_32"]["holm_p"],6))
    print("counts",sum(r["within_reference_16"]["reject"] for r in results if r["reference"]=="no_next"),
          sum(r["both_references_32"]["reject"] for r in results))

if __name__ == "__main__":
    go()
