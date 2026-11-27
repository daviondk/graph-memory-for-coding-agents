"""Project only ID ranks and choices from prior receipts; never open any issue or trajectory text."""
import argparse
import csv
import json
from pathlib import Path
from common import HERE, load, save, sha

OLD = Path("D:/CodexResearch/x20-bench-workspace/work/sota_round/swe_context")
STAGE = Path("D:/CodexResearch/x20-swe-context")
R59 = HERE.parents[1] / "graph_memory_round59"

def get_lines(p):
    with p.open(encoding="utf8") as f:
        for line in f: yield json.loads(line)

def cost(r):
    return [r["usage"]["prompt_tokens"], r["usage"]["completion_tokens"]]

def export():
    import pyarrow.parquet as pq
    pin = load(OLD/"blind_commit.json")
    for name in ("qwen_calls.jsonl","blind_ranks.json","source.json"):
        assert sha(OLD/name)==pin[name]
    src = load(OLD/"source.json")
    official = {r["relative"]:r["sha256"] for r in src["files"]}
    tasks = []
    seen = set()
    for name in ("SWEContextBench_Related_Lite","SWEContextBench_Related"):
        path = STAGE / (name+".parquet")
        assert sha(path)==official[path.name]
        for t in pq.read_table(path, columns=["instance_id","repo"]).to_pylist():
            if t["instance_id"] not in seen:
                tasks.append(t)
                seen.add(t["instance_id"])
    ranks = load(OLD/"blind_ranks.json")
    assert len(ranks)==len(tasks)==357
    rows = {}
    for i, (t, ranks_row) in enumerate(zip(tasks, ranks, strict=True)):
        assert i == ranks_row["ordinal"]
        rows[i] = {"task":t["instance_id"],"repo":t["repo"], "ranks":{k:v for k,v in ranks_row.items() if k!="ordinal"},"readers":{}}
    files = [OLD/"blind_commit.json",OLD/"qwen_calls.jsonl",OLD/"blind_ranks.json",OLD/"matched_reader/calls.jsonl"]
    for name in ("recall_hybrid","recall_keyword"):
        p = OLD / (name+".json")
        assert sha(p)==load(OLD/(name+"_pin.json"))["sha256"][p.name]
        files += [p, OLD/(name+"_pin.json")]
        for i,r in enumerate(load(p)):
            assert r["ordinal"]==i
            rows[i]["ranks"][name]=r[name]
    for r in get_lines(OLD/"qwen_calls.jsonl"):
        a = rows[r["ordinal"]]
        assert set(r["order"])==set(a["ranks"]["fusion"][:5])
        a["readers"]["full"]=[r["choice"], *cost(r)]
    for r in get_lines(OLD/"matched_reader/calls.jsonl"):
        a = rows[r["ordinal"]]
        kind = r["arm"]
        assert set(r["order"])==set(a["ranks"]["recall_hybrid" if kind=="recall_five" else "fusion"][:5])
        a["readers"][kind]=[r["choice"], *cost(r)]
    b = R59/"agent_benchmark"
    arms, ans = load(b/"assignments.json.gz"),load(b/"answers.json.gz")
    x, pred = load(b/"inputs.json.gz"),load(b/"predictions.json.gz")
    files += [b/name for name in ("assignments.json.gz","answers.json.gz","inputs.json.gz","predictions.json.gz")]
    for i, record in arms.items():
        a = rows[int(i)]
        assert set(record["base"])==set(a["ranks"]["fusion"][:5])
        for k, h in record["arms"].items():
            a["readers"][k]=[pred[i][k]["selected"],len(x[h]),ans[h]["output_tokens"]]
    other_file=R59/"graph_candidates/predictions.json.gz"
    files.append(other_file)
    for i in load(other_file): rows[int(i)]["r59_candidates"]=True
    assert all(len(r["readers"])>=3 for i,r in rows.items() if i<99)
    save("inputs.json.gz",list(rows.values()))
    save("source.json",{"source_digests":{f.as_posix().replace(OLD.as_posix()+"/","archive/").replace(R59.as_posix()+"/","R59/"):sha(f) for f in files},
                        "official_rev":src["hf"],"official_code":src["github"],"official_tables":{k:v for k,v in official.items() if k.endswith(".parquet")}})

def labels():
    import pyarrow.parquet as pq
    pin=load(HERE/"decision-seal.json")
    assert sha(HERE/"decisions.json.gz")==pin["decisions.json.gz"]
    rel=STAGE/"SWEContextBench_Relationship.parquet"
    assert sha(rel)==load(HERE/"source.json")["official_tables"][rel.name]
    with (OLD/"evaluation_library.csv").open(encoding="utf8") as f:
        library={r["instance_id"]:r["trace_key"] for r in csv.DictReader(f)}
    assert len(library)==len(set(library.values()))==300
    gold={}
    for r in pq.read_table(rel,columns=["related_instance_id","experience_instance_id"]).to_pylist():
        target=r["related_instance_id"]; prev=r["experience_instance_id"]
        if prev not in gold.setdefault(target,[]):gold[target].append(prev)
    rows=load(HERE/"inputs.json.gz")
    save("labels.json.gz",[{"positive_ids":[library.get(n) for n in gold[r["task"]]],"task":r["task"]} for r in rows])
    save("label-source.json",{"library":sha(OLD/"evaluation_library.csv"),"relationship":sha(rel),"transformation":"One entry per unique official relationship, in release order; null for a positive missing from the 300. IDs match archived trajectory keys."})

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--labels",action="store_true")
    if p.parse_args().labels: labels()
    else: export()

