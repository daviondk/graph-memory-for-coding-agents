"""Verify the blind seal, then run the pinned evaluator and paired summaries."""
import hashlib
import json
import statistics as st
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CODING = ROOT.parent / "coding"
sys.path.insert(0, str(CODING))
from controls import bootstrap, lengths, trim
from score import ExploreEvaluator, METRICS, line_counts


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    lock = json.loads((ROOT / "predictions_lock.json").read_bytes())
    assert sha(ROOT/"tasks.json") == lock["tasks"] and sha(ROOT/"predict_holdout.py") == lock["prediction_code"]
    assert sha(ROOT/"protocol.md") == lock["protocol"]
    tasks = json.loads((ROOT/"tasks.json").read_bytes())
    repo_of = {t["instance_id"]:t["repo"] for t in tasks}
    ids = list(repo_of)
    pred = {}
    for q in ids:
        file = ROOT/"predictions"/(q+".json")
        assert sha(file)==lock["prediction_hashes"][q]
        pred[q] = json.loads(file.read_bytes())
    assert hashlib.sha256(json.dumps(lock["prediction_hashes"],sort_keys=True).encode()).hexdigest()==lock["joint_sha256"]
    bench = CODING/"bench.final.public.jsonl"
    assert sha(bench) == "dc4f114ececd0bfb987361c26ae5e2440456e2cccb36adfccb09ea5385aec202"
    ev = ExploreEvaluator(bench)
    ev.file_line_counts = {q:line_counts(q,ev.bench_data_dict[q]["ground_truth"]) for q in ids}
    arms = ["tfidf", "prior", "new"]
    caps = {q:min(lengths(pred[q][a]) for a in arms) for q in ids}
    report = {"n":len(ids),"repositories":len(set(repo_of.values())),"prediction_lock":lock["joint_sha256"],
              "gated_on_issues":sum(pred[q]["query_names_count"]>0 for q in ids),
              "mean_index_and_ranking_seconds":{k:st.mean(pred[q][k] for q in ids) for k in
                    ("tfidf_seconds","prior_additional_seconds","char_additional_seconds")},
              "means":{},"paired":{}}
    rows = []
    for mode in ("equal_lines","five_regions"):
        out = {}
        for a in arms:
            regions = {q: (trim(pred[q][a],caps[q]) if mode=="equal_lines" else pred[q][a]) for q in ids}
            if mode=="equal_lines":
                assert all(lengths(regions[q])==caps[q] for q in ids)
            else:
                assert all(len(regions[q])==5 for q in ids)
            metric = ev.evaluate(lambda _,q:regions[q],ids,METRICS)
            out[a] = metric
            report["means"][mode+"_"+a] = {m:st.mean(metric[q][m] for q in ids) for m in METRICS}
            report["means"][mode+"_"+a].update({"mean_raw_lines":st.mean(lengths(regions[q]) for q in ids),
                                               "mean_regions":st.mean(len(regions[q]) for q in ids)})
            rows.extend({"instance_id":q,"repo":repo_of[q],"mode":mode,"arm":a,"lines":lengths(regions[q]),
                         "regions":len(regions[q]),**metric[q]} for q in ids)
        for a in ("tfidf","prior"):
            delta = {q:out["new"][q]["f1_score"]-out[a][q]["f1_score"] for q in ids}
            paired = bootstrap(delta,repo_of)
            paired["leave_one_repository_out"] = {r:st.mean(delta[q] for q in ids if repo_of[q]!=r)
                                                  for r in sorted(set(repo_of.values()))}
            paired["repository_differences"] = {r:st.mean(delta[q] for q in ids if repo_of[q]==r)
                                                for r in sorted(set(repo_of.values()))}
            report["paired"][mode+"_new_vs_"+a] = paired
    (ROOT/"results.json").write_text(json.dumps(report,indent=2),encoding="utf8")
    (ROOT/"rows.jsonl").write_text("".join(json.dumps(r)+"\n" for r in rows),encoding="utf8")
    for mode in ["equal_lines","five_regions"]:
        print(mode,[(a,round(100*report["means"][mode+"_"+a]["f1_score"],3),
                        round(report["means"][mode+"_"+a]["mean_raw_lines"],1)) for a in arms])
        for a in ("tfidf","prior"):
            x=report["paired"][mode+"_new_vs_"+a]
            loo=list(x["leave_one_repository_out"].values())
            print("new vs",a,x["difference"],x["repo_bootstrap_95"],"W/T/L",x["wins"],x["ties"],x["losses"],
                  "LOO",min(loo),max(loo))
    print("gated issues",report["gated_on_issues"],"time", report["mean_index_and_ranking_seconds"])


if __name__=="__main__":
    main()
