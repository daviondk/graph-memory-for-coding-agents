"""Create and freeze 64 complete rankings before the separate scoring process."""
import datetime
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import time
import numpy as np

ROOT = Path(__file__).resolve().parent
PRIOR = ROOT.parent
OLD = Path(os.environ.get("SWE_CONTEXT_BASE", str(PRIOR.parents[1]/"sota_round"/"swe_context")))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path):
    return json.loads(path.read_text(encoding="utf8"))


def save(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf8")


def utc():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def donor(salt, keys, lengths):
    order = sorted(range(len(keys)), key=lambda j: (lengths[j], hashlib.sha256((salt+"|"+keys[j]).encode()).hexdigest()))
    ix = np.empty(len(keys), dtype=np.uint16)
    for i, j in zip(order[::2], order[1::2]):
        ix[i], ix[j] = j, i
    return ix


def main():
    start = time.perf_counter()
    registration = {x.name:sha(x) for x in (ROOT/"PROTOCOL.md", ROOT/"predict.py", ROOT/"score.py",
                    OLD/"rank.py", OLD/"queries.json", OLD/"cards.json", PRIOR/"rankings.npz")}
    if (ROOT/"registration.json").exists():
        assert registration == load(ROOT/"registration.json")["files"]
    else:
        save(ROOT/"registration.json", {"utc":utc(), "files":registration})
    spec=importlib.util.spec_from_file_location("ranker",OLD/"rank.py")
    engine=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(engine)
    cards=load(OLD/"cards.json")
    keys=[c["key"] for c in cards]
    qs=[r["query"] for r in load(OLD/"queries.json")]
    scores={field:engine.bm25([c[field] for c in cards],qs) for field in ("symptom","closure","edits")}
    lengths=[len(c["edits"].split()) for c in cards]
    base=2*engine.reciprocal(scores["symptom"])+engine.reciprocal(scores["closure"])
    const=np.load(PRIOR/"rankings.npz")
    def apply(ix):
        return engine.ranks(base+engine.reciprocal(scores["edits"][:,ix])).astype(np.uint16)
    original=donor("20261116-write-factor-shuffle", keys,lengths)
    assert np.array_equal(const["lex_shuffle"],apply(original))
    assert np.array_equal(const["lex_real"],apply(np.arange(300)))
    assert np.array_equal(const["lex_absent"],engine.ranks(base))
    mappings=np.stack([donor("x20/perm-robustness/20261116/"+str(i),keys,lengths) for i in range(64)])
    assert len({x.tobytes() for x in mappings})==64
    assert all(np.array_equal(np.sort(x),np.arange(300)) for x in mappings) and (mappings!=np.arange(300)).all()
    ranks=np.stack([apply(ix) for ix in mappings])
    np.savez_compressed(ROOT/"predictions.npz", rankings=ranks, donors=mappings)
    save(ROOT/"blind_lock.json",{"utc":utc(),"files":{name:sha(ROOT/name) for name in
         ["registration.json","predictions.npz"]},"parity":{"lex_real":357,"lex_absent":357,"lex_shuffle":357},
         "wall_seconds":time.perf_counter()-start, "gpu":0,"llm_calls":0})
    print("64 complete blind donor assignments on all 357 questions; original three lists matched",flush=True)


if __name__=="__main__":
    main()

