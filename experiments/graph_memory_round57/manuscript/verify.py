"""Match manuscript figures and reported values to the frozen repository and inspect the PDF."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import re
import fitz

HERE = Path(__file__).resolve().parent
ROUND = HERE.parent


def data(relative):
    return json.loads((ROUND / relative).read_bytes())


def inspect():
    src = (HERE / "paper.tex").read_text("utf-8")
    with fitz.open(HERE / "paper.pdf") as document:
        assert len(document) == 4
        assert all(tuple(p.rect) == (0, 0, 612, 792) for p in document)
        fonts = {row[0] for p in document for row in p.get_fonts(full=True)}
        assert all(document.extract_font(f)[-1] for f in fonts)
        words = [len(p.get_text().split()) for p in document]
        text = "\n".join(p.get_text() for p in document)
        assert "??" not in text and all(f"Fig. {i}." in text for i in [1, 2, 3])
        assert len(re.findall(r"(?m)^TABLE I{1,2}$", text)) == 2
        refs = text.split("REFERENCES")[-1]
        assert set(re.findall(r"(?m)^\[(\d+)\]", refs)) == set(map(str, range(1, 8)))
        assert all(w >= 400 for w in words)
        assert all(len(p.get_text("blocks")) > 3 for p in document)
    rep = data("replication/results.json")
    assert rep["n"] == 932 and rep["pooled"]["fill6_norm"]["event_reads"] == rep["pooled"]["own_norm"]["event_reads"]
    assert round(100 * (1 - rep["pooled"]["fill6_norm"]["bytes"] / rep["pooled"]["own_norm"]["bytes"]), 1) == 33.1
    joint = data("seed_pair/metrics.json")["new"]["pooled"]
    assert joint["n"] == 621
    assert [round(100 * joint["metrics"][m]["recall"], 2) for m in ("sum", "joint", "placebo")] == [36.89, 37.19, 37.82]
    physical = data("block_index/results.json")
    assert [physical["long-" + m]["footprint"] for m in ("split", "filelist")] == [512000, 323584]
    assert [physical["long-" + m]["counts"]["event_bytes"] for m in ("split", "filelist")] == [27716, 135845]
    composed = data("composed/results.json")
    for label, counts in (("continuous", (149294, 91732, 123058, 21142)), ("restart", (149294, 102444, 128801, 106781))):
        for method, limit in zip(("flat", "lru", "own", "shared"), counts):
            run = composed[f"long-{label}-{method}"]
            assert run["footprint"] == 323584 and run["queries"] == 196
            assert run["all_body_bytes"] + run["all_posting_bytes"] == limit
    assert composed["long-restart-r56_split"]["restore_bytes"] == 51120
    for plan, wanted in (("own", 38.36), ("shared", 28.50), ("r56_split", 19.62), ("lru", 31.61)):
        runs = composed["long-continuous-" + plan]["all_read_ns"]
        assert len(runs[1]) == 5 and round(runs[0] / 1000000, 2) == wanted
    certs = [r["pooled"] for r in data("joint_certificate/results.json").values()]
    assert [sum(r[k] for r in certs) for k in ("n", "initial_scores", "reads", "packet_plus_members_bytes", "full_bytes")] == [1153, 1120, 43, 535143, 392416]
    trace = data("agent_trace/results.json")
    assert trace["scope"]["traces"] == 108 and trace["primary"]["n"] == 134
    assert trace["cache_all_views"]["graph"]["served"] == 327334
    for number in ("33.1", "932", "621", "36.89", "37.19", "37.82", "1,120", "535,143", "392,416",
                   "512,000", "323,584", "21,142", "123,058", "106,781", "303,104", "299,008", "327,334", "4,096"):
        assert number in text and number in src, number
    for entry in ("seed_pair/demo.html", "seed_pair/demo.py", "seed_pair/replay.sqlite"):
        assert (ROUND / entry).is_file()
    assets = ("paper.tex", "paper.pdf", "sources.bib", "capture.py", "figure.py", "dask-replay.png", "retention.pdf", "pair-worlds.pdf")
    return {"pages": len(words), "page_words": words, "dimensions_pt": [612, 792], "embedded_fonts": len(fonts),
            "figures": 3, "tables": 2, "references": 7, "unresolved_references": 0,
            "sha256": {name: sha256((HERE / name).read_bytes()).hexdigest() for name in assets}}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--record", action="store_true")
    args = p.parse_args()
    result = inspect()
    path = HERE / "verification.json"
    if args.record:
        path.write_bytes((json.dumps(result, indent=2, sort_keys=True) + "\n").encode())
    else:
        assert result == json.loads(path.read_bytes())
    print(f"Verified four IEEE pages, {result['embedded_fonts']} embedded fonts, three figures and experiment outputs.")


if __name__ == "__main__":
    main()
