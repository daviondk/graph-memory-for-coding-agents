"""Re-score immutable choices with an additional public repository checkout alias."""
import argparse
import gzip
import hashlib
import json
import os
import random
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
os.environ["OPENBLAS_NUM_THREADS"] = "1"
import numpy as np
from memory import ARMS, SUBMIT, canonical, clip, each_batch, signature
from replay import label_reason, write
from summarize import lines

HERE = Path(__file__).resolve().parent


def signature_alias(cmd, alias):
    family, path = signature(alias.sub("/testbed", cmd))
    return family, "" if path.rsplit("/",1)[-1] == "patch.txt" else path


def score(args):
    src = args.base / "benchmark"
    events = defaultdict(list)
    for e in lines("decisions.jsonl.gz"):
        if e["branch"] == "labelled":
            events[e["sid"]].append(e)
    repo_counts = {}
    groups = defaultdict(Counter)
    with gzip.open(HERE/"alias_decisions.jsonl.gz", "wt", encoding="utf8", compresslevel=5) as out:
        for hist in lines("histories.jsonl.gz"):
            _, _, repo, sid, _ = hist["path"].split("/")
            rc = repo_counts.setdefault(repo, Counter())
            local = events.pop(sid, [])
            if not local:
                continue
            slug = repo.split("__",1)[1]
            alias = re.compile(r"(?<![\w./~+-])/"+re.escape(slug)+r"(?=/|[\s;&'\"|)]|$)",re.I)
            raw = (src / hist["path"]).read_bytes()
            assert hashlib.sha256(raw).hexdigest() == hist["sha256"]
            nums = json.loads(raw)
            batches = list(each_batch(nums if isinstance(nums,list) else nums["messages"],Counter()))
            source = {}
            for b, batch in enumerate(batches):
                for s in batch:
                    value = clip(canonical(s.cmd),1024)
                    source[(b,s.slot)] = (value,signature(value),signature_alias(value,alias))
            previous = None
            pairs, success = [], []
            by_b = {e["fail"][0]: e for e in local}
            for b, batch in enumerate(batches):
                if e := by_b.get(b):
                    assert b+1 < len(batches) and label_reason(batches[b+1])=="labelled"
                    gold = canonical(batches[b+1][0].cmd)
                    assert hashlib.sha256(gold.encode()).hexdigest() == e["gold"]["sha256"]
                    gold0 = signature(gold)
                    target = signature_alias(gold,alias)
                    assert list(gold0) == [e["gold"]["family"],e["gold"]["target"]]
                    extractable = bool(all(target))
                    ceiling = {"success":bool(extractable and target in success),"pair":bool(extractable and target in pairs)}
                    row = {"sid":sid,"fail":e["fail"],"target":list(target),"ceiling":ceiling,"hits":{}}
                    for arm, choices in e["choices"].items():
                        bits = []
                        for j, ptr in enumerate(choices):
                            val,old,new = source[tuple(ptr[2:])]
                            before = int(val == gold)+2*int(all(gold0) and old==gold0)+4*int(bool(gold0[0]) and old[0]==gold0[0])
                            assert before==e["hits"][arm][j], (sid,b,arm,j)
                            bits.append(int(extractable and new == target))
                        row["hits"][arm] = bits
                    write(out,row)
                    keys = ["all_labelled"]
                    if e["recurrent"]:
                        keys.append("primary")
                        if extractable:
                            keys.append("primary_extractable")
                    if e["fp_recurrent"]:
                        keys.append("fingerprint_recurrent")
                    for g in keys:
                        acc = groups[g]
                        acc["n"]+=1
                        acc["extractable"]+=int(extractable)
                        for key,v in ceiling.items():
                            acc["ceiling_"+key]+=int(v)
                        for k in (1,3):
                            compact = any(row["hits"]["compact"][:k])
                            for arm, bits in row["hits"].items():
                                hit = any(bits[:k])
                                acc[f"{arm}@{k}"]+=int(hit)
                                if g == "primary":
                                    rc[f"{arm}_only{k}"]+=int(hit and not compact)
                                    rc[f"{arm}_compactonly{k}"]+=int(compact and not hit)
                                    rc[f"{arm}_hit{k}"]+=int(hit)
                        if g == "primary":
                            rc["n"]+=1
                if previous is not None and label_reason(batch)=="labelled":
                    pairs.append(source[(b,0)][2])
                success.extend(source[(b,s.slot)][2] for s in batch if s.rc==0 and not SUBMIT.search(s.cmd))
                previous = next((s for s in batch if s.rc is not None and s.rc != 0),None)
    assert not events
    rng = random.Random(20261116)
    repos = sorted(repo_counts)
    weights=np.zeros((10000,len(repos)),dtype=np.int64)
    for i in range(len(weights)):
        weights[i]=np.bincount(rng.choices(range(len(repos)),k=len(repos)),minlength=len(repos))
    den=weights @ np.array([repo_counts[r]["n"] for r in repos])
    contrasts={}
    for arm in ARMS:
        if arm=="compact":
            continue
        for k in (1,3):
            plus=np.array([repo_counts[r][f"{arm}_compactonly{k}"] for r in repos])
            minus=np.array([repo_counts[r][f"{arm}_only{k}"] for r in repos])
            delta=plus-minus
            contrasts[f"{arm}@{k}"]={"delta":float(sum(delta)/groups["primary"]["n"]),
                "ci95":np.quantile((weights@delta)/den,[.025,.975]).tolist(),
                "compact_only":int(sum(plus)),"other_only":int(sum(minus))}
    (HERE/"alias_summary.json").write_text(json.dumps({"cohorts":groups,"paired_primary":contrasts,
        "repositories":repo_counts},indent=2),encoding="utf8")


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--base",type=Path,default=Path("D:/CodexResearch/x20-official-vibe/VibeMemBench"))
    ap.add_argument("--freeze",action="store_true")
    args=ap.parse_args()
    names=("alias-protocol.md","score_alias.py","freeze.json","decisions.jsonl.gz","histories.jsonl.gz")
    hashes={f:hashlib.sha256(gzip.decompress((HERE/f).read_bytes()) if f.endswith(".gz") else (HERE/f).read_bytes()).hexdigest() for f in names}
    frozen=HERE/"alias_freeze.json"
    if args.freeze:
        with frozen.open("x",encoding="utf8") as f:
            json.dump({"utc":datetime.now(timezone.utc).isoformat(),"sha256":hashes},f,indent=2)
        return
    recorded=json.loads(frozen.read_bytes())["sha256"]
    assert recorded==hashes
    score(args)


if __name__=="__main__":
    main()
