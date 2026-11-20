"""Descriptive source checks after frozen scoring, including patch-transport stratification."""
from collections import Counter,defaultdict
import argparse
import json
from pathlib import Path
from run import ARMS,HERE,batches,declarations,digest
from summary import data


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--base",type=Path,default=Path("D:/CodexResearch/x20-official-vibe/VibeMemBench"))
    args=ap.parse_args()
    hs={h["sid"]:h for h in data("histories.jsonl.gz")}
    bins=defaultdict(Counter)
    discordant=[]
    for e in data("queries.jsonl.gz"):
        g="patch.txt" if e["path"].rsplit("/",1)[-1]=="patch.txt" else "other_paths"
        bins[g]["n"]+=1
        for a,hit in zip(ARMS,e["arms"]):
            bins[g][a+"_"+(hit[2] if hit else "miss")]+=1
        flush,sel=e["arms"][-2:]
        if bool(flush)==bool(sel):
            continue
        h=hs[e["sid"]]
        p=args.base/"benchmark"/h["path"]
        raw=p.read_bytes()
        assert digest(raw)==h["sha256"]
        d=json.loads(raw)
        turns=list(batches(d if isinstance(d,list) else d["messages"]))
        hit=sel or flush
        src=declarations(turns[hit[0]][0])[hit[1]][0]
        now=declarations(turns[e["b"]][0])[e["slot"]][0]
        assert src==now and digest(now.encode())==e["cmd_sha256"]
        discordant.append({"sid":e["sid"],"repo":h["repo"],"fill_batch":hit[0],"read_batch":e["b"],
                           "command":now,"path":e["path"],"bytes":e["bytes"],"stdout_sha256":e["stdout_sha256"],
                           "winner":"selective" if sel else "flush"})
    (HERE/"source_audit.json").write_text(json.dumps({"strata":bins,"selective_flush_discordant":discordant,
        "histories":len(set(e["sid"] for e in discordant)),"repos":len(set(e["repo"] for e in discordant))},
        indent=2),encoding="utf8")


if __name__=="__main__":
    main()
