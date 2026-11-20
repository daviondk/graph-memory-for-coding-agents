import collections
import hashlib
import itertools
import json
import math
import statistics
from pathlib import Path

from prepare import HERE, LETTERS, prompt

if __name__ == "__main__":
    rows = json.loads((HERE/"selection.json").read_text())
    calls = [json.loads(s) for s in (HERE/"requests.jsonl").read_text().splitlines()]
    responses = [json.loads(s) for s in (HERE/"responses.jsonl").read_text().splitlines()]
    assert len(calls)==len(responses)==72
    records = {r["sha"]:r for r in rows}
    assert len(records) == 24
    observations = {}
    metrics = collections.defaultdict(collections.Counter)
    for call, reply in zip(calls, responses):
        sha, arm = call["sha"], call["arm"]
        row = records[sha]
        assert call["request"] == prompt(row,arm)
        assert reply["sha"]==sha and reply["arm"]==arm
        assert hashlib.sha256(json.dumps(call["request"]).encode()).hexdigest()==reply["request_sha256"]
        msg = reply["response"]["choices"][0]
        output = msg["message"]["content"].strip()
        correct_format = output in set(LETTERS)
        answer = row["slate"][LETTERS.index(output)] if correct_format else None
        assert (sha,arm) not in observations
        if arm == "true":
            assert msg["message"].get("reasoning_content") in ("", None)
        hit = answer in row["targets"]
        observations[(sha,arm)] = {"answer":output,"path":answer,"hit":int(hit)}
        usage = reply["response"]["usage"]
        m = metrics[arm]
        for key, value in {"n":1,"hit":int(hit),"malformed":int(not correct_format),"input_tokens":usage["prompt_tokens"],
                           "output_tokens":usage["completion_tokens"],"cached_tokens":usage["prompt_tokens_details"]["cached_tokens"],
                           "seconds":reply["seconds"],"http_retries":len(reply["http_errors"])}.items():
            m[key] += value
    pairs = {}
    for a,b in [("true","shuffled"),("true","masked"),("masked","shuffled")]:
        d = [observations[(s,a)]["hit"]-observations[(s,b)]["hit"] for s in records]
        win,lose = d.count(1),d.count(-1)
        n = win+lose
        p = min(1,2*sum(math.comb(n,i) for i in range(min(win,lose)+1))/2**n) if n else 1.0
        pairs[a+"_vs_"+b] = {"wins":win,"losses":lose,"ties":d.count(0),"delta":statistics.fmean(d),"exact_p_two_sided":p,
                              "different_choices":sum(observations[(s,a)]["answer"]!=observations[(s,b)]["answer"] for s in records)}
        repo_sums = collections.Counter()
        for sha, delta in zip(records, d):
            repo_sums[records[sha]["repo"]] += delta
        extreme = 0
        for signs in itertools.product((-1,1),repeat=len(repo_sums)):
            stat = sum(v*s for v,s in zip(repo_sums.values(),signs))
            extreme += abs(stat) >= abs(sum(repo_sums.values()))
        pairs[a+"_vs_"+b]["posthoc_by_repo_signed_deltas"] = repo_sums
        pairs[a+"_vs_"+b]["posthoc_cluster_swap_two_sided"] = extreme / 2**len(repo_sums)
    table = []
    for r in rows:
        top = {m: observations[(r["sha"],m)] for m in ["masked","true","shuffled"]}
        table.append({"repo":r["repo"],"sha":r["sha"],"anchor":r["anchor"],"targets":r["targets"],
                      "ceiling":bool(set(r["slate"]) & set(r["targets"])),"lexical":r["lex"] in r["targets"],
                      "graph":r["graph"] in r["targets"],"answers":top})
    result = {"n":len(rows),"repos":len({r["repo"] for r in rows}),"ceiling":sum(r["ceiling"] for r in table),
              "deterministic":{name:sum(r[name] for r in table) for name in ("lexical","graph")},
              "arms":metrics, "pairs":pairs, "table":table}
    (HERE/"results.json").write_text(json.dumps(result,indent=2),encoding="utf-8")
    print(json.dumps({k:v for k,v in result.items() if k!="table"},indent=2))
