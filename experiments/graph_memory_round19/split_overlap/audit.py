"""Audit matched forecasts on raw-field overlap strata without refitting models."""
import argparse
import gzip
import hashlib
import json
import os
import re
import sys
import unicodedata
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROUND = HERE.parent
RUN = Path(os.environ.get("ISETRACE_RUNTIME", "D:/CodexResearch/x20-isetrace-runtime"))
QUERY = RUN / "inputs/query-authoring/isetrace-v7-raw.jsonl"
UPSTREAM = RUN / "upstream"
sys.path.insert(0, str(UPSTREAM))
from graph_memory.query_synthesis.provenance.authoring import parse_task_intents, parse_task_sources

PROTOCOL_SHA = "62496a9f5ab62e2978ce5085cae3ce7ff848c82fcaec21b56a8771dd19b707e0"
WRITER_PATH = ROUND / "write_learned/transfer-outcomes.json.gz"
DENSE_PATH = ROUND / "trained_rank/outcomes.json.gz"


def sha(path):
    with path.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def read(path):
    with (gzip.open(path, "rt", encoding="utf8") if path.suffix == ".gz" else path.open(encoding="utf8")) as f:
        return json.load(f)


def save(name, obj):
    raw = (json.dumps(obj, ensure_ascii=False, sort_keys=True, indent=None if name.endswith(".gz") else 2) + "\n").encode()
    (HERE / name).write_bytes(gzip.compress(raw, mtime=0) if name.endswith(".gz") else raw)


def signature(text, normalized):
    if normalized:
        text = re.sub(r"\s+", " ", unicodedata.normalize("NFKC", text).casefold()).strip()
    return hashlib.sha256(text.encode("utf8")).digest()


def authoring_fields(item):
    sources = parse_task_sources(item["text"])
    source_text = {s.handle: s.text for s in sources}
    gold = item["gold"]
    assert gold and len(source_text) == len(sources)
    assert all(g["quote"] in source_text[g["source"]] for g in gold)
    result = []
    for normalized in [False, True]:
        def digest(txt):
            return signature(txt, normalized)
        intents = tuple(digest(s) for s in parse_task_intents(item["text"]))
        source_tuple = tuple(digest(s.text) for s in sources)
        result.append(dict(sources=set(source_tuple), gold_fields={digest(source_text[g["source"]]) for g in gold},
                           gold_quotes={digest(g["quote"]) for g in gold}, intents=set(intents),
                           intents_order=intents, question=digest(item["query"]), sources_order=source_tuple))
    return result


def indices(records):
    return {k: (set.union(*(r[k] for r in records)) if k in ("sources", "intents", "gold_quotes")
                else {r[k] for r in records}) for k in ("sources","intents","gold_quotes","intents_order","question","sources_order")}


def match(index, record):
    return dict(gold_field=bool(index["sources"] & record["gold_fields"]),
                all_gold_fields=record["gold_fields"] <= index["sources"],
                any_source=bool(index["sources"] & record["sources"]),
                gold_quote=bool(index["gold_quotes"] & record["gold_quotes"]),
                any_intent=bool(index["intents"] & record["intents"]),
                whole_intent_list=record["intents_order"] in index["intents_order"],
                whole_question=record["question"] in index["question"],
                whole_source_list=record["sources_order"] in index["sources_order"])


def freeze():
    assert sha(HERE / "PROTOCOL_RU.md") == PROTOCOL_SHA
    split_file = ROUND / "trained_rank/split.json.gz"
    dev_file = ROUND / "write_transfer/cohort.json"
    selection_file = ROUND / "write_learned/plan.json"
    split = read(split_file)
    heldout = dict(test=split["test"], dev=read(dev_file))
    select = set(read(selection_file)["selection"])
    train = dict(dense=split["train"], writer=[x for x in split["train"] if x["t"] in select])
    assert (len(train["writer"]), len(select), len(train["dense"])) == (411, 256, 3894)
    assert (len(heldout["test"]), len(heldout["dev"])) == (2000, 580)
    for left, right in ((train["dense"],heldout["test"]), (train["dense"],heldout["dev"]), (heldout["dev"],heldout["test"])):
        for k in ["q","t"]:
            assert {r[k] for r in left}.isdisjoint({r[k] for r in right})
    required = {r["q"] for rows in [train["dense"], *heldout.values()] for r in rows}
    mapped = {}
    with QUERY.open(encoding="utf8") as f:
        for line in f:
            item = json.loads(line)
            if item["id"] in required:
                assert item["id"] not in mapped
                mapped[item["id"]] = authoring_fields(item)
    assert set(mapped) == required
    flags, summary = [], {}
    for label, training in train.items():
        for mode, name in enumerate(["raw","nfkc_casefold_space"]):
            lookup = indices([mapped[r["q"]][mode] for r in training])
            for part, rows in heldout.items():
                items = [dict(q=r["q"], t=r["t"], **match(lookup, mapped[r["q"]][mode])) for r in rows]
                stats = {k: dict(questions=sum(i[k] for i in items), trajectories=len({i["t"] for i in items if i[k]}))
                         for k in items[0] if k not in ("q", "t")}
                summary["/".join([label,part,name])] = stats
                if mode == 0:
                    flags.extend(dict(train=label, split=part, **i) for i in items)
    save("overlap-flags.json.gz", flags)
    save("overlap-summary.json", summary)
    save("overlap-lock.json", dict(protocol=PROTOCOL_SHA, code=sha(HERE/"audit.py"),
         flags=sha(HERE/"overlap-flags.json.gz"), summary=sha(HERE/"overlap-summary.json"),
         inputs={str(f):sha(f) for f in (split_file, dev_file, selection_file, QUERY,
              UPSTREAM/"graph_memory/query_synthesis/provenance/authoring.py", WRITER_PATH, DENSE_PATH)}))


def compare(records):
    groups = sorted({row[0] for row in records})
    at = {g:i for i,g in enumerate(groups)}
    stats = np.array([row[1:] for row in records], dtype=float)
    ids = np.array([at[row[0]] for row in records])
    counts = np.bincount(ids, minlength=len(groups))
    delta = stats[:, [0,2]] - stats[:, [1,3]]
    sums = np.column_stack([np.bincount(ids, weights=delta[:,j], minlength=len(groups)) for j in [0,1]])
    rng = np.random.default_rng(13)
    boot = []
    for _ in range(100):
        draw = rng.integers(len(groups), size=(100,len(groups)))
        boot.append(sums[draw].sum(axis=1) / counts[draw].sum(axis=1)[:,None])
    intervals = np.percentile(np.concatenate(boot), [2.5,97.5], axis=0).T.tolist()
    return dict(n=len(records), trajectories=len(groups), fs_a=int(stats[:,0].sum()), fs_b=int(stats[:,1].sum()),
                wins=int((delta[:,0]>0).sum()), losses=int((delta[:,0]<0).sum()),
                fs_diff=delta[:,0].mean(), fs_ci=intervals[0], coverage_a=stats[:,2].mean(),
                coverage_b=stats[:,3].mean(), coverage_diff=delta[:,1].mean(), coverage_ci=intervals[1])


def evaluate():
    lock = read(HERE/"overlap-lock.json")
    assert sha(HERE/"audit.py") == lock["code"] and sha(HERE/"overlap-flags.json.gz") == lock["flags"]
    for name in [WRITER_PATH,DENSE_PATH]:
        assert lock["inputs"][str(name)] == sha(name)
    flags = read(HERE/"overlap-flags.json.gz")
    outcomes = {("writer",p):{} for p in ("test", "dev")}
    for row in read(WRITER_PATH):
        arms = row["a"]
        a, b = arms["tokens/full"], arms["tokens/output_head"]
        outcomes["writer",row["split"]][row["q"]] = (row["t"],a[3],b[3],a[4],b[4])
    dense = {}
    for row in read(DENSE_PATH):
        dense.setdefault(row["q"],{})[row["arm"]] = row
    outcomes["dense","test"] = {}
    for q, arms in dense.items():
        a, b = arms["related"], arms["skip"]
        outcomes["dense","test"][q] = (a["t"],a["full_support"],b["full_support"],a["coverage"],b["coverage"])
    result = {}
    for (model, split), table in outcomes.items():
        keep = {r["q"]:r for r in flags if (r["train"],r["split"]) == (model,split)}
        assert set(keep) == set(table) and all(r["t"]==table[q][0] for q,r in keep.items())
        for stratum in ["all","unmatched","matched"]:
            subset = sorted(q for q in keep if stratum=="all" or keep[q]["gold_field"]==(stratum=="matched"))
            result["/".join([model,split,stratum])] = out = compare([table[q] for q in subset])
            if model == "dense":
                out["prefix_fs"] = int(sum(dense[q]["prefix"]["full_support"] for q in subset))
    return result


def verify():
    manifest = read(HERE/"MANIFEST_SHA256.json")
    for path, h in manifest.items():
        assert sha(HERE/path)==h, path
    assert manifest.keys() == {f.name for f in HERE.iterdir() if f.is_file() and f.name!="MANIFEST_SHA256.json"}
    assert evaluate() == read(HERE/"results.json")
    print("verified", len(manifest), "files, three paired contrasts, each overall and by match stratum")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=["freeze", "score", "verify"])
    cmd = parser.parse_args().stage
    if cmd == "freeze":
        freeze()
    elif cmd == "score":
        save("results.json", evaluate())
    else:
        verify()
