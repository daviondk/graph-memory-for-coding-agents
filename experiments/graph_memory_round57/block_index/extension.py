"""Matched block-level follow-up after observing the complete-list baseline."""
import argparse
import platform
from pathlib import Path
import random
import sqlite3
import sys
from tempfile import TemporaryDirectory

from bench import HERE, REPETITIONS, aggregate, load, protocol_digest, panels, prepare, run, save
from block_store import EXTRA, R56

MODES=("filelist","sealed",*EXTRA)
SEED=57062


def trial(args, modes, seed, prefix, protocol_file, opener=None):
    path=HERE/(prefix+"-runs.json.gz")
    expected=load(R56/"durable/runs.json.gz")["oracle"]
    protocol=protocol_digest(HERE/protocol_file)
    if args.verify:
        raw=load(path)
        assert raw["oracle"]==expected and raw["protocol_sha256"]==protocol
        assert len(raw["runs"])==len(expected)*REPETITIONS*len(modes)
        assert aggregate(raw["runs"],modes)==load(HERE/(prefix+"-results.json"))
        print("Verified",len(raw["runs"]),"matched extension runs.");return
    streams=panels(); inputs={}
    for p in ("B","long"):
        for repo,rows in streams[p].items():
            inputs[p,repo],digest=prepare(rows,p)
            assert digest==expected[p+"/"+repo]
    raw=load(path) if path.exists() else dict(seed=seed,python=sys.version,sqlite=sqlite3.sqlite_version,
        platform=platform.platform(),protocol_sha256=protocol,oracle=expected,runs=[])
    assert raw["oracle"]==expected and raw["protocol_sha256"]==protocol
    done={(r["panel"],r["repo"],r["rep"],r["mode"]) for r in raw["runs"]}
    rng=random.Random(seed)
    with TemporaryDirectory(dir=HERE,prefix="list-") as td:
        for rep in range(REPETITIONS):
            for (panel,repo),ops in inputs.items():
                for pos,mode in enumerate(rng.sample(modes,len(modes))):
                    if (panel,repo,rep,mode) in done:continue
                    db=Path(td)/"run.sqlite"
                    row=run(ops,db,mode) if opener is None else run(ops,db,mode,open_store=opener,source_counters=True)
                    row.update(panel=panel,repo=repo,rep=rep,mode=mode,position=pos)
                    raw["runs"].append(row);db.unlink()
            save(path,raw);save(HERE/(prefix+"-results.json"),aggregate(raw["runs"],modes))
            print(prefix,"block",rep+1,"/",REPETITIONS,flush=True)


def cli():
    ap=argparse.ArgumentParser()
    ap.add_argument("--verify",action="store_true")
    return ap.parse_args()


if __name__=="__main__":
    trial(cli(),MODES,SEED,"extra","EXTENSION_RU.md")
