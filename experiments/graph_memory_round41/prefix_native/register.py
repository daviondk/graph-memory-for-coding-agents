from shared import D, OFF, C, W, SEEDS, ARMS, read, save, sha, panel
from pathlib import Path


def main():
    split = read(OFF / "split.json.gz")["test"]
    ts = {r["t"] for r in split}
    assert len(ts) == 1207 and len(split) == 2000
    weights = {}
    for s in SEEDS:
        for arm in ARMS:
            pub = OFF / f"seed-{s}" / arm
            fit = read(pub / "fit.json")
            f = Path("D:/CodexResearch/x20-native-multiseed/official580") / f"seed-{s}" / fit["attempt"] / "best.pt"
            assert sha(f) == fit["checkpoint"] == read(pub / "forecast-seal.json")["checkpoint"]
            weights[f"{s}/{arm}"] = [fit["checkpoint"], fit["weight"], sha(pub / "forecast-seal.json")]
    facts = dict(protocol=sha(D / "PROTOCOL_RU.md"), split=sha(OFF / "split.json.gz"), terminal_panel=panel(ts),
                 checkpoints=weights, causal_forecasts=sha(C / "forecast-seal.json"),
                 native_program=sha(D / "native.py"), seeds=SEEDS,
                 prefix_states={str(i):sha(C / f"state-{i}-seal.json") for i in range(8)})
    path = D / "registration.json"
    assert not path.exists()
    save(path, facts)
    print(sha(path))


if __name__ == "__main__":
    main()
