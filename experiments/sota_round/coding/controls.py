"""Run author-supplied retrievers and a matched emitted-line diagnostic."""
import hashlib
import json
import random
import statistics as st
import sys
from collections import defaultdict
from pathlib import Path

from cache_paths import CACHE, ROOT
sys.path[:0] = [str(CACHE / "deps"), str(ROOT / "deps"), str(ROOT / "upstream")]
from explorers.rag_tfidf import TFIDFExplorer
from explorers.rag_potion import PotionExplorer
from eval import ExploreEvaluator
from score import METRICS, line_counts


def compute(arm):
    if arm == "potion":
        from model2vec import StaticModel
        model = StaticModel.from_pretrained(str(CACHE / "potion-base-8M"))
    records = {}
    for task in json.loads((ROOT / "tasks.json").read_bytes()):
        q = task["instance_id"]
        source = CACHE / "snapshots" / q
        explorer = TFIDFExplorer(source) if arm == "tfidf" else PotionExplorer(source, _model=model)
        h = hashlib.sha256()
        for c in explorer._chunks:
            h.update(json.dumps([c.path,c.start,c.end,c.content],ensure_ascii=False).encode())
        existing = json.loads((ROOT / "predictions" / (q + ".json")).read_bytes())
        if h.hexdigest() != existing["chunk_inventory_sha256"]:
            raise RuntimeError("Inventory mismatch: " + q)
        predictions = explorer.explore(instance_id=q, query=task["problem_statement"], top_k=5)
        records[q] = [[r.path,r.start,r.end] for p in predictions for r in p.regions]
        print(arm,q,len(records[q]),flush=True)
    (ROOT / (arm + "_predictions.json")).write_text(json.dumps(records,indent=2),encoding="utf8")


def trim(predictions, budget):
    result = []
    for path, start, end in predictions:
        if budget <= 0:
            break
        length = min(budget, end-start+1)
        result.append([path,start,start+length-1])
        budget -= length
    return result


def lengths(items):
    return sum(end-start+1 for _,start,end in items)


def bootstrap(deltas,repo_of):
    groups = defaultdict(list)
    for iid, v in deltas.items():
        groups[repo_of[iid]].append(v)
    repos = sorted(groups)
    rng = random.Random(20261116)
    boot = [st.mean(v for r in rng.choices(repos,k=len(repos)) for v in groups[r]) for _ in range(10000)]
    bounds = st.quantiles(boot, n=40, method="inclusive")
    return {"difference":st.mean(deltas.values()),"repo_bootstrap_95":[bounds[0],bounds[-1]],"wins":sum(v>0 for v in deltas.values()),
            "ties":sum(v==0 for v in deltas.values()),"losses":sum(v<0 for v in deltas.values())}


def score_controls():
    tasks = json.loads((ROOT / "tasks.json").read_bytes())
    ids = [t["instance_id"] for t in tasks]
    repo_of = {t["instance_id"]:t["repo"] for t in tasks}
    pred = {q:json.loads((ROOT / "predictions" / (q+".json")).read_bytes()) for q in ids}
    methods = {arm:{q:pred[q][arm] for q in ids} for arm in ["fusion","bm25"]}
    for arm in ["tfidf","potion"]:
        path = ROOT / (arm+"_predictions.json")
        if path.is_file():
            methods[arm] = json.loads(path.read_bytes())
    ev = ExploreEvaluator(ROOT / "bench.final.public.jsonl")
    ev.file_line_counts = {q:line_counts(q, ev.bench_data_dict[q]["ground_truth"]) for q in ids}
    paired, means, rows = {}, {}, []
    for control in sorted(set(methods) - {"fusion"}):
        for mode in ["five_regions","same_emitted_lines"]:
            caps = {q:min(lengths(methods[m][q]) for m in ("fusion",control)) for q in ids}
            case = f"fusion_vs_{control}_{mode}"
            by_method = {}
            for name in ["fusion",control]:
                preds = {q:trim(methods[name][q], caps[q]) if mode == "same_emitted_lines" else methods[name][q] for q in ids}
                if mode == "same_emitted_lines":
                    assert all(lengths(preds[q]) == caps[q] for q in ids)
                scores = ev.evaluate(lambda _,q: preds[q], ids, METRICS)
                by_method[name] = scores
                means[case+"_"+name] = {m:st.mean(scores[q][m] for q in ids) for m in METRICS}
                means[case+"_"+name]["mean_raw_lines"] = st.mean(lengths(preds[q]) for q in ids)
                rows.extend({"case":case,"arm":name,"id":q,"raw_lines":lengths(preds[q]),**scores[q]} for q in ids)
            paired[case] = bootstrap({q:by_method["fusion"][q]["f1_score"]-by_method[control][q]["f1_score"] for q in ids},repo_of)
    output = {"n":len(ids),"paired":paired,"means":means}
    (ROOT / "controls_results.json").write_text(json.dumps(output,indent=2),encoding="utf8")
    (ROOT / "controls_rows.jsonl").write_text("".join(json.dumps(r)+"\n" for r in rows),encoding="utf8")
    print(json.dumps(paired,indent=2))


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action",choices=["tfidf","potion","score"])
    action=parser.parse_args().action
    if action=="score":
        score_controls()
    else:
        compute(action)
