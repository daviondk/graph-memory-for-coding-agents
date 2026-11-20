"""Shuffle evidence within repositories before opening the released relevance links."""
import csv
import hashlib
import importlib.util
from collections import defaultdict
import numpy as np
from predict import ROOT, PRIOR, OLD, load, sha, save, utc


def table(path):
    with path.open(encoding="utf8", newline="") as file:
        return list(csv.DictReader(file))


def main():
    tr = PRIOR.parent / "transfer"
    files = [ROOT/"WITHIN_REPO.md", ROOT/"within_predict.py", ROOT/"within_score.py", ROOT/"blind_lock.json",
             tr/"source_times_lite.csv", tr/"query_times_lite.csv", OLD/"rank.py", OLD/"cards.json", OLD/"queries.json"]
    registration = {p.name:sha(p) for p in files}
    target = ROOT/"within_registry.json"
    if target.exists():
        assert load(target)["files"] == registration
    else:
        save(target, {"utc":utc(), "files":registration})
    spec = importlib.util.spec_from_file_location("previous",OLD/"rank.py")
    engine = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(engine)
    cards = load(OLD/"cards.json")
    qs = [r["query"] for r in load(OLD/"queries.json")[:99]]
    scores = {f:engine.bm25([c[f] for c in cards],qs) for f in ("symptom","closure","edits")}
    base = 2*engine.reciprocal(scores["symptom"])+engine.reciprocal(scores["closure"])
    keys = [c["key"] for c in cards]
    repos = {r["trace_key"]:r["repo"].lower() for r in table(tr/"source_times_lite.csv")}
    by_repo = defaultdict(list)
    for i,k in enumerate(keys):
        by_repo[repos[k]].append(i)
    assert len(by_repo) == 12 and min(map(len,by_repo.values())) >= 3
    sizes = np.array([len(c["edits"].split()) for c in cards])
    donors, ranks = [],[]
    for seed in range(64):
        salt = "x20/perm-robustness/20261116/"+str(seed)
        ix = np.empty(300,dtype=np.uint16)
        for group in by_repo.values():
            rows = sorted(group, key=lambda j:(sizes[j],hashlib.sha256((salt+"|"+keys[j]).encode()).hexdigest()))
            end = len(rows)-3 if len(rows)%2 else len(rows)
            for a,b in zip(rows[:end:2],rows[1:end:2]):
                ix[a],ix[b] = b,a
            if end<len(rows):
                a,b,c = rows[end:]
                ix[a],ix[b],ix[c] = b,c,a
        assert all(repos[keys[j]] == repos[keys[k]] for j,k in enumerate(ix))
        assert (ix!=np.arange(300)).all() and np.array_equal(np.sort(ix),np.arange(300))
        donors.append(ix)
        ranks.append(engine.ranks(base+engine.reciprocal(scores["edits"][:,ix])).astype(np.uint16))
    truth = engine.ranks(base+engine.reciprocal(scores["edits"]))
    assert np.array_equal(truth,np.load(PRIOR/"rankings.npz")["lex_real"][:99])
    np.savez_compressed(ROOT/"within_ranks.npz", rankings=np.stack(ranks), donors=np.stack(donors))
    delta=np.abs(sizes[np.array(donors)]-sizes)
    save(ROOT/"within_lock.json",{"utc":utc(),"files":{p:sha(ROOT/p) for p in ("within_registry.json","within_ranks.npz")},
         "n_unique":len({x.tobytes() for x in donors}), "n_repos":len(by_repo), "mean_word_length_delta":delta.mean(),
         "max_word_length_delta":int(delta.max()), "real_parity":len(truth)})
    print("64 within-repository donor mappings blind-locked for all 99 queries.")


if __name__=="__main__":
    main()

