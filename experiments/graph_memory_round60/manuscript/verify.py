"""Validate the released PDF and reconcile its paper statistics with local registries."""
import argparse
import hashlib
import json
from pathlib import Path
from statistics import median

import fitz

HERE = Path(__file__).resolve().parent
R60 = HERE.parent


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check_results():
    cov = read(R60 / "coverage/results.json")
    cases = {"old12/B": [123019, 115945, 118988, 109005],
             "r59/B": [21957, 20055, 22941, 17177],
             "new/B": [11531, 10465, 16991, 9213]}
    for panel, target in cases.items():
        arms = cov[panel]["arms"]
        assert [arms[f"1024/{m}"]["charged"] for m in ("exact", "xor", "lazy", "notify")] == target
    notify = cov["new/B"]["arms"]["1024/notify"]
    assert [notify[key] for key in ("queries", "posting_bytes", "body_bytes", "certified_multiple",
                                    "exception_insertions", "scan_bytes")] == [485, 5085, 4128, 14, 1003, 110897]
    for mode in ("exact", "notify"):
        assert cov["new/B"]["arms"][f"4096/{mode}"]["charged"] == 4322
    succinct = read(R60 / "succinct/results.json")["new/B"]
    assert [succinct[f"1024/{m}/best"]["charged"] for m in ("exact", "notify")] == [11372, 9201]
    wire = read(R60 / "wire/results.json")["arms"]
    for m, b, n in (("exact", 20115, 412), ("xor", 17919, 386), ("notify", 16533, 374)):
        row = wire[f"1024/{m}/0"]["counters"]
        assert (row["wire"], row["trips"]) == (b, n)
    obs = read(R60 / "observed_coverage/results.json")
    for case, target in (("16/1024", [1668] * 3), ("4/256", [7798, 7650, 7636])):
        assert [obs[case]["methods"][x]["charged"] for x in ("exact", "xor", "notify")] == target
    assert obs["16/1024"]["methods"]["notify"]["query"] == 436
    cpu = read(R60 / "hot_delta/results.json")["new/B"]
    for m, target in (("append", (11646, 41.53)), ("notify", (9213, 71.06)), ("hot_trusted", (10863, 52.42))):
        row = cpu[f"1024/{m}"]
        assert (row["charged"][0], round(median(row["combined_ns"])/1e6, 2)) == target
    fast = read(R60 / "fast_coverage/hit-results.json")
    for panel, m, b, t in (("r60", "resident_hit", 9187, 38.16), ("r60", "full_reuse", 11646, 38.75),
                           ("r60", "hot_only", 14918, 35.39), ("both", "resident_hit", 26122, 91.43),
                           ("both", "full_reuse", 33837, 94.60)):
        row = fast[panel]["methods"][f"1024/{m}"]
        assert set(row["traffic"]) == {b}
        assert round(median(row["total_ns"])/1e6, 2) == t


def inspect():
    check_results()
    pdf = HERE / "paper.pdf"
    with fitz.open(pdf) as doc:
        assert len(doc) == 4
        pages = [p.get_text() for p in doc]
        assert all(p.rect == fitz.Rect(0, 0, 612, 792) for p in doc)
        assert all("\ufffd" not in t and "??" not in t for t in pages)
        joined = " ".join(pages)
        for token in ("9,187", "9,201", "16,533", "38.16", "91.43", "7,636",
                      "WebGraph", "Noria", "REFERENCES", "TABLE I", "TABLE II", "Fig. 1.", "Fig. 2."):
            assert token in joined, token
        fonts = {f[0]: f[3] for p in doc for f in p.get_fonts()}
        assert all(doc.extract_font(x)[3] for x in fonts)
        refs = len(set(x["uri"] for p in doc for x in p.get_links() if x.get("uri")))
        assert refs >= 6
        return {"page_count":len(doc), "paper_inches":[8.5, 11],
                "words_per_page":[len(t.split()) for t in pages], "embedded_fonts":len(fonts),
                "distinct_links":refs, "registries_checked":["coverage","succinct","wire","observed_coverage","hot_delta","fast_coverage"],
                "sha256":{p:digest(HERE / p) for p in ("paper.pdf","paper.tex","projects.pdf","lab.png")}}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--record", action="store_true")
    args = parser.parse_args()
    result = inspect()
    record = HERE / "verification.json"
    if args.record:
        record.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    else:
        assert result == read(record)
    print(json.dumps(result))
