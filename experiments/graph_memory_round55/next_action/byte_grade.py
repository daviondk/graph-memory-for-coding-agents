"""Check solver constraints and report paired physical source payload and recall."""
import argparse

import numpy as np

from inputs import HERE, R54, digest, read, save

MODELS = ("static","snapshot","history","rrf7")


def grade(verify):
    seal = read(HERE/"byte-seal.json")
    assert all(digest(HERE/n) == h for n,h in seal.items())
    choices = read(HERE/"byte-decisions.json.gz")
    cert = read(HERE/"solver-certificates.json")["groups"]
    source = read(R54/"learned_read/projection.json.gz")
    old = read(R54/"next_read/explicit-decisions.json.gz")
    fusion = read(R54/"next_read/fusion-choices.json.gz")
    chunks = read(HERE/"first-chunks.json.gz")
    scores = read(HERE/"oof-scores.json.gz")
    gold = {q:set(a) for q,a in read(R54/"next_read/labels.json.gz").items()}
    ids = sorted(choices)
    methods = sorted(choices[ids[0]])
    groups, ix = np.unique([source[q]["group"] for q in ids],return_inverse=True)
    n = np.bincount(ix)
    per_query = {}
    matched = 0
    for q in ids:
        row = source[q]
        prior = {**old[q]["receipts"], **fusion[q]["receipts"]}
        for i, (order, length, sha) in chunks[q].items():
            key = row["paths"][int(i)]
            if key in prior:
                assert prior[key] == [order[0], order[1], sha]
                matched += 1
        record = {}
        for name, selected in choices[q].items():
            assert len(set(selected)) == len(selected) <= 2
            retrieved = {row["paths"][i] for i in selected}
            hits = len(gold[q] & retrieved)
            recall = len((retrieved | set(row["strict"])) & gold[q])/len(gold[q])
            record[name] = [hits, sum(chunks[q][str(i)][1] for i in selected), len(selected), recall]
        per_query[q] = record
    measures, results = {}, dict(replicated_receipts=matched, methods={}, contrasts={}, by_repo={})
    for name in methods:
        values = measures[name] = np.array([per_query[q][name] for q in ids])
        aggregate = np.zeros((len(n),4))
        np.add.at(aggregate,ix,values)
        assert np.array_equal(aggregate[:,2], n)
        for j,grp in enumerate(groups):
            b = cert[grp]
            if name == "dense":
                assert int(aggregate[j,1]) == b["byte_cap"]
            else:
                check = b[name]
                model = name.split("_",1)[1]
                utility = sum(int(round(1e9*scores[q][model][i])) for q in ids if source[q]["group"] == grp for i in choices[q][name])
                assert utility == check["utility_integer"] and abs(utility+check["primary_dual"]) < 0.6
                assert abs(check["tie_dual"] - aggregate[j,1]) < 0.6
                assert int(aggregate[j,1]) == check["returned_bytes"]
                if name.startswith("bytes_"):
                    assert aggregate[j,1] <= b["byte_cap"]
            results["by_repo"].setdefault(grp,{})[name] = [int(x) for x in aggregate[j,:3]]
        num, payload = values.sum(0)[:2]
        results["methods"][name] = dict(hits=int(num), bytes=int(payload), reads=int(values[:,2].sum()),
              hits_per_100_reads=100*num/len(ids), total_recall_pct=100*values[:,3].mean(),
              hit_tasks=int((values[:,0] > 0).sum()),
              allocations=[int((values[:,2] == k).sum()) for k in range(3)])
    draws = np.random.default_rng(55001).integers(len(n),size=(10000,len(n)))
    contrasts = [("bytes_history", "bytes_snapshot"), ("bytes_static", "dense"), ("bytes_snapshot","dense"),
                 ("bytes_history","dense")] + [("bytes_"+m,"count_"+m) for m in MODELS]
    for a,b in contrasts:
        sums = np.bincount(ix, weights=measures[a][:,0] - measures[b][:,0])
        boot = 100*sums[draws].sum(1)/n[draws].sum(1)
        results["contrasts"][a+"-"+b] = dict(delta=100*sums.sum()/n.sum(), ci=np.quantile(boot,[.025,.975]).tolist())
    if verify:
        assert results == read(HERE/"byte-results.json")
    else:
        save("byte-results.json", results)
    print({m:[v["hits"],v["bytes"]] for m,v in results["methods"].items()})
    print(results["contrasts"]["bytes_history-bytes_snapshot"])


if __name__ == "__main__":
    arg=argparse.ArgumentParser()
    arg.add_argument("--verify",action="store_true")
    grade(arg.parse_args().verify)
