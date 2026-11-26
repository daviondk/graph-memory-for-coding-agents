"""Compare rankings and pack sealed native orders without opening gold."""
import argparse
from collections import Counter, defaultdict
from shared import D, W, OFF, SEEDS, ARMS, read, save, sha, pack


def compile_outputs(label):
    train = W / "graph_memory_round19/trained_rank"
    ref_seal = read(train / "forecast-seal.json")["forecasts"]
    terminal = defaultdict(Counter)
    half = defaultdict(Counter)
    predictions = []
    src_hash = {}
    control_differences = []
    for sh in range(8):
        src = D / f"{label}-{sh}.json.gz"
        seal = read(D / f"{label}-{sh}-seal.json")
        assert sha(src) == seal["data"] and sha(D / "registration.json") == seal["registration"]
        src_hash[sh] = seal["data"]
        rows = read(src)
        if not rows:
            continue
        path = train / f"forecasts-main-{sh}.json.gz"
        assert sha(path) == ref_seal[path.name]
        costs = {r["q"]:[n["token_count"] for n in r["rr"]] for r in read(path)}
        references = {}
        for s in SEEDS:
            for arm in ARMS:
                p = OFF / f"seed-{s}" / arm
                saved = {v["file"]:v["sha"] for v in read(p / "forecast-seal.json")["receipts"]}
                historical = p / f"picks-{sh}.json.gz"
                assert sha(historical) == saved[historical.name]
                references[f"{s}/{arm}"] = {r["q"]:r["graph"] for r in read(historical)}
        for q, t, cut, by_arm in rows:
            out = {}
            for key, seq in by_arm.items():
                valid = set(seq)
                reference = references[key][q]
                if cut == 100:
                    assert valid == set(reference)
                restricted = [i for i in reference if i in valid]
                assert len(seq) == len(valid) == len(restricted)
                strict, ff = pack(seq, costs[q], True), pack(seq, costs[q], False)
                hs, hf = pack(restricted, costs[q], True), pack(restricted, costs[q], False)
                count = (terminal if cut == 100 else half)[key]
                count.update(dict(questions=1, order=int(seq==restricted), top1=int(seq[0]==restricted[0]),
                                  top5=int(seq[:5]==restricted[:5]), strict=int(strict==hs), firstfit=int(ff==hf)))
                if cut == 100 and seq != restricted:
                    mismatch = next(j for j, pair in enumerate(zip(seq, restricted)) if pair[0] != pair[1])
                    control_differences.append([q,key,len(seq),mismatch,int(strict==hs),int(ff==hf)])
                if cut == 50:
                    out[key] = [strict, ff, hs, hf]
            if cut == 50:
                predictions.append([q,t,out])
    assert len({r[0] for r in predictions}) == len(predictions)
    panel = len(read(D / "registration.json")["terminal_panel"])
    if label == "forecast":
        assert len(predictions) == 2000 and len({r[1] for r in predictions})==1207
    out = D / f"{label}-packets.json.gz"
    save(out, predictions)
    save(D / f"{label}-seal.json", dict(predictions=sha(out), shards=src_hash, questions=len(predictions),
         terminal=terminal, prefix_vs_restricted=half, terminal_differences=control_differences,
         registration=sha(D / "registration.json"), wrapper=sha(D / "packets.py")))
    print(label, len(predictions), "terminal control", dict(terminal), flush=True)


if __name__ == "__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--quick",action="store_true")
    compile_outputs("quick" if parser.parse_args().quick else "forecast")
