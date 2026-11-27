"""Vary full-list representations in both LRU and graph-complement implementations."""
from argparse import ArgumentParser
from collections import Counter
from contextlib import closing
from pathlib import Path
from random import Random
from tempfile import TemporaryDirectory
from unittest.mock import patch
import sys

from formats import Encoder, ENCODERS, R59, unpack_list, varints
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "coverage"))
import coverage as notifications
from coverage import Coverage, EXCEPTION, possible_losses, prefix_number
from run_coverage import load, prepare, save
from lazy_reader import BlockStore, Cache, Hot, Policy, POST, unpack


class EncodedCache(Cache):
    def __init__(self, cap, encoder):
        super().__init__(cap)
        self.encoder = encoder

    def get(self, key):
        data = super().get(key)
        if data is not None and key[0] == POST:
            return varints(unpack_list(data))
        return data

    def put(self, key, data, admission=None, refresh=True):
        if key[0] == POST:
            data = self.encoder(unpack(data))
        super().put(key, data, admission=admission, refresh=refresh)


class Exact(Policy):
    def after_write(self, j, files):
        for f in files:
            key = (POST, f)
            data = self.cache.items.get(key)
            if data is not None:
                self.cache.put(key, varints((*unpack_list(data), j)), refresh=False)


def codec_functions(encode):
    def pack(n, excluded):
        return bytes([EXCEPTION]) + varints((n,)) + (encode(tuple(sorted(excluded))) if excluded else b"")

    def parts(data):
        n, end = prefix_number(data)
        return n, (unpack_list(data[end:]) if end < len(data) else ())

    # Change only the codec functions for the duration of this single-threaded arm.
    return dict(full=encode, expand=unpack_list, append_exact=lambda b,j: encode((*unpack_list(b), j)),
                pack_exceptions=pack, parts=parts)


def case(db, ops, mode, cap, oracle):
    cut = sum(op[0] == "w" for op in ops) // 2
    entries = []
    algo, codec = mode.split("/")
    encode = Encoder(codec)
    policy = None
    with patch.multiple(notifications, **codec_functions(encode)):
        for op in ops:
            if policy is None and db.next_id == cut:
                hot = Hot()
                if algo == "notify":
                    policy = Coverage(db, hot, cap, True)
                else:
                    policy = Exact(db, hot, "joint", cap)
                    policy.cache = EncodedCache(cap, encode)
            if op[0] == "w":
                _, j, rev, files = op
                assert db.append(j, rev, files)
                if policy is not None:
                    before = possible_losses(hot, files) if algo == "notify" else {}
                    hot.append(j, files)
                    if algo == "notify":
                        policy.after_committed(j, files, [(p, x) for p, x in before.items() if p not in hot.live])
                    else:
                        policy.after_write(j, files)
            elif policy is not None:
                _, anchor, tie, prior, gold = op
                ranked, st = policy.read(anchor, tie, prior)
                assert ranked == gold
                old = oracle[len(entries)]
                assert old["anchor"] == anchor and old["prefix"] == db.next_id
                if algo == "notify":
                    vals = [st[k] for k in ("posting_bytes", "body_bytes", "posting_calls", "body_calls")]
                else:
                    vals = [st[i] for i in (2, 3, 0, 1)]
                if codec == "basic":
                    archived = old["arms"][f"{cap}/{algo}"]
                    assert vals == [archived.get(k,0) for k in ("posting_bytes", "body_bytes", "posting_calls", "body_calls")]
                entries.append(vals)
        policy.cache.inventory()
    assert len(entries) == len(oracle)
    return dict(queries=entries, selections={str(k):v for k,v in encode.selected.items()})


def run():
    result = {}
    panels = {"r59": R59 / "holdout/events.json.gz", "new": HERE.parent / "panel/events.json.gz"}
    archive = load(HERE.parent / "coverage/runs.json.gz")["cases"]
    rng = Random(600318)
    modes = [f"exact/{m}" for m in (*ENCODERS, "best")] + ["notify/basic", "notify/best"]
    with TemporaryDirectory(dir=HERE) as tmp:
        p = Path(tmp) / "source.sqlite"
        for g, source in panels.items():
            for name, changes in load(source).items():
                for layout in ("B", "long"):
                    key = g + "/" + layout + "/" + name
                    ops, _ = prepare(changes, layout)
                    data = result[key] = {}
                    for cap, mode in rng.sample([(c, m) for c in (1024,4096) for m in modes], 2*len(modes)):
                        with closing(BlockStore(p, "filelist", True)) as db:
                            data[f"{cap}/{mode}"] = case(db, ops, mode, cap, archive[key]["logs"])
                        p.unlink()
            print(g, "complete", flush=True)
    return result


def summarize(raw):
    result = {}
    for name, arms in raw.items():
        group = "/".join(name.split("/")[:2])
        for mode, cells in arms.items():
            counter = result.setdefault(group, {}).setdefault(mode, Counter())
            for row in cells["queries"]:
                counter.update(dict(zip(("post", "body", "post_calls", "body_calls"), row)))
            counter["charged"] = counter["post"] + counter["body"]
            counter["queries"] += len(cells["queries"])
    return result


if __name__ == "__main__":
    ap = ArgumentParser()
    ap.add_argument("--verify", action="store_true")
    args = ap.parse_args()
    f = HERE / "runs.json.gz"
    raw = load(f) if args.verify else run()
    tab = summarize(raw)
    if args.verify:
        assert tab == load(HERE / "results.json")
    else:
        save(f, raw)
        save(HERE / "results.json", tab)
    for k, v in sorted(tab["new/B"].items()):
        print(k, v["charged"])
