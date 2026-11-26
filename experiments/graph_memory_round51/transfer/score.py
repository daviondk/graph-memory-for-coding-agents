"""Score sealed HotpotQA answers with the pinned author evaluator."""
import ast
from collections import Counter
from contextlib import redirect_stdout
from io import StringIO
import sys
import json
import importlib.util

from study import D, P, N, FILES, ARMS, EVAL_HASH, columns, put, get, sha, shared, check


def official():
    assert sha(P/"official.py") == EVAL_HASH
    sys.modules.setdefault("ujson", json)
    spec = importlib.util.spec_from_file_location("hotpot_author", P/"official.py")
    evaluator = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(evaluator)
    return evaluator


def grade():
    check()
    ctx = get(D/"contexts.json.gz")
    ans = get(D/"answers.json.gz")
    sealed = get(D/"answer-seal.json")
    assert sha(D/"input-seal.json") == sealed["input"] and sha(D/"answers.json.gz") == sealed["answers"]
    assert set(ctx) == set(get(D/"panel.json")["order"])
    rows = {x["id"]:x for path in FILES for x in columns(path,["id","answer","type","supporting_facts"]) if x["id"] in ctx}
    assert len(rows) == N
    inputs = get(P/"visible.json.gz")
    scorer = official()
    gold = {}
    outcomes = {}
    raw = []
    for q in sorted(rows):
        r = rows[q]
        titles = [d[1] for d in inputs[q][1]]
        ft = set(r["supporting_facts"]["title"])
        docs = ctx[q]
        scores = {}
        for arm in ARMS:
            target, prompt_key, length = docs["refs"][arm]
            ans_text = ans[prompt_key]["answer"]
            read = {titles[docs["seed"]],titles[target]}
            scores[arm] = [float(scorer.exact_match_score(ans_text,r["answer"])),scorer.f1_score(ans_text,r["answer"])[0],
                           int(ft <= read),len(read & ft)/len(ft)]
        gold[q] = dict(answer=r["answer"], kind=r["type"], supports=sorted(i for i,t in enumerate(titles) if t in ft),
                       support_titles=sorted(ft), titles=titles)
        outcomes[q] = dict(cluster=docs["cluster"], switch=docs["switch"], kind=r["type"], arms=scores)
        raw.append({"_id":q, "answer":r["answer"], "supporting_facts":list(zip(r["supporting_facts"]["title"],r["supporting_facts"]["sent_id"],strict=True))})
    gp, ap = P/"official-gold.json",P/"official-pred.json"
    gp.write_text(json.dumps(raw,ensure_ascii=True),encoding="ascii")
    metrics = {}
    for a in ARMS:
        ap.write_text(json.dumps({"answer":{q:ans[x["refs"][a][1]]["answer"] for q,x in ctx.items()},
                                   "sp":{q:[] for q in ctx}},ensure_ascii=True),encoding="ascii")
        capture=StringIO()
        with redirect_stdout(capture):scorer.eval(str(ap),str(gp))
        vals=ast.literal_eval(capture.getvalue().strip())
        metrics[a] = {k:vals[k] for k in ("em","f1")}
        for j,k in enumerate(["em","f1"]):
            assert abs(sum(x["arms"][a][j] for x in outcomes.values())/N-vals[k]) < 1e-12
    put(D/"gold.json.gz",gold)
    put(D/"outcomes.json.gz",outcomes)
    results = shared("statistics_sem").analyze(list(outcomes.values()))
    results["columns"]=["official_em","official_answer_f1","all_support_titles","fraction_support_titles"]
    results["outcomes"]=sha(D/"outcomes.json.gz")
    results["official"]=metrics
    results["switched"]={a:sum(c["refs"][a][0]!=c["refs"]["dense"][0] for c in ctx.values()) for a in ARMS}
    results["kinds"] = dict(Counter(x["kind"] for x in outcomes.values()))
    put(D/"results.json",results)
    shared("signflip").run("new")
    print(json.dumps(dict(official=metrics,changes=results["switched"],primary=results["contrasts"]["adaptive-dense"]),ensure_ascii=True))

if __name__ == "__main__":
    grade()
