"""Independent recount of rankings, provenance hashes and examples."""
import collections
import gzip
import hashlib
import json
from pathlib import Path

from features import RX, facts, meaningful, shaped

HERE = Path(__file__).resolve().parent

def read_rows(name):
    return [json.loads(line) for line in gzip.decompress((HERE / name).read_bytes()).splitlines()]

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def examples(records, labels, inputs):
    examples = {}
    ordered = sorted(records, key=lambda x: hashlib.sha256(x["id"].encode()).hexdigest())
    for row in ordered:
        rid = row["id"]
        ranking = row["rankings"]
        if not ranking["graph"] or not ranking["decl"]:
            continue
        g = set(labels["river"][rid]["any"])
        if (ranking["graph"][0] in g) == (ranking["decl"][0] in g):
            continue
        sign = "win" if ranking["graph"][0] in g else "loss"
        if sign in examples:
            continue
        r = inputs["river", rid]
        cues = {t for t in RX.findall(r["question"][:40000]) if meaningful(t) and shaped(t)}
        fs = {p: facts(oid) for p,oid in r["blobs"].items()}
        owner = ranking["graph"][0]
        if owner not in fs or not fs[owner]:
            continue
        peer = [(t,p) for t in sorted(cues & fs[owner][2])
                for p in r["paths"] if p!=owner and fs.get(p) and t in fs[p][3]]
        if not peer:
            continue
        examples[sign] = {"id":rid, "native":ranking["native"][0],"decl":ranking["decl"][0],
                          "graph":owner,"gold":sorted(g),"name_and_file":peer[:4]}
    return examples

def main():
    root = HERE.parent
    design = json.loads((HERE / "design_lock.json").read_text())
    for k,v in design.items():
        assert sha(HERE/k)==v, k
    rows = read_rows("score_rows.jsonl.gz")
    lab = json.loads((HERE/"labels.json").read_text())
    stats = json.loads((HERE/"results.json").read_text())
    inputs={(r["source"],r["id"]):r for r in json.loads(gzip.decompress((HERE/"inputs.json.gz").read_bytes()))}
    features=read_rows("features.jsonl.gz")
    all_inputs=collections.defaultdict(set)
    for src,rid in inputs: all_inputs[src].add(rid)
    assert all_inputs["loc"].isdisjoint(all_inputs["river"])
    assert all(v <= set(lab[s]) for s,v in all_inputs.items())
    assert len(all_inputs["loc"]) == 274 and len(all_inputs["river"]) == 407
    sums=collections.Counter()
    diffs=collections.Counter()
    for r in rows:
        panel=r["panel"]
        source="loc" if panel.startswith("loc_") else "river"
        for arm,paths in r["rankings"].items():
            assert sorted(paths)==sorted(r["rankings"]["native"]) and len(paths)<=5
            diffs[panel,arm,"order"]+=paths!=r["rankings"]["native"]
            diffs[panel,arm,"first"]+=paths[:1]!=r["rankings"]["native"][:1]
            for label,gold in lab[source][r["id"]].items():
                at=next((j for j,p in enumerate(paths,1) if p in gold),None)
                assert r["arms"][arm][label]["hit"]==int(at==1)
                assert abs(r["arms"][arm][label]["mrr"]-(1/at if at else 0))<1e-12
                sums[panel,arm,label]+=int(at==1)
    for (panel,arm,label),n in sums.items():
        assert n==stats[panel]["totals"][arm][label]["hit"]
    report={"assertions":"design hashes, disjoint IDs, each ranker permutes the identical slate of <=5 paths, independent gold membership and MRR for all labels and arms, aggregate hits",
            "n_rows":len(rows),"rank_change_vs_native":{"/".join(k):v for k,v in diffs.items()},
            "source":{"total_paths":sum(len(i["paths"]) for i in inputs.values()),"parsed":sum(t["n_ast"] for t in features),
                      "with_blob":sum(t["n_blobs"] for t in features),"filtered_by_source":{s:sum(i["excluded"] for (src,id_),i in inputs.items() if s==src) for s in all_inputs}},
            "examples": examples([r for r in rows if r["panel"]=="river_loro"],lab,inputs),
            "examples_selection":"first by SHA-256(instance_id) for each direction graph vs declaration-local with an issue-shaped identifier declared by graph's first file and observed in a different candidate; descriptive evidence only"}
    (HERE/"audit.json").write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding="utf8")
    print(json.dumps({"rows":len(rows),"source":report["source"],"examples":report["examples"],"loc_first_changes":diffs["loc_loro","graph","first"]},ensure_ascii=True,indent=2))
if __name__=="__main__":main()

