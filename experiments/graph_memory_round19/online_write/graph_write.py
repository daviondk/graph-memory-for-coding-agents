"""Online call-key alignment intervention at the frozen primary capacity."""
import collections
import gzip
import json
import os
import sys
from concurrent.futures import ProcessPoolExecutor
from predict import HERE,CACHE,digest,dump,stable,select,read,content_tokens

def worker(shard):
    src = HERE/f"forecast-{shard}.jsonl.gz"
    out = HERE/f"graph-{shard}.jsonl.gz"
    with gzip.open(src,"rt",encoding="utf-8") as inp, gzip.open(out,"wt",encoding="utf-8",compresslevel=3) as f:
        for line in inp:
            r = json.loads(line)
            with gzip.open(CACHE/f"{shard}-{r['t']}.json.gz","rb") as p:
                raw = json.load(p)
            meta = {s["event_id"]:unit["metadata"] for unit in raw["pool"] for s in unit["source_spans"]}
            keys,prev_for,calls,roles = [],{}, {},[]
            previous = None
            edge_stats = collections.Counter()
            for eid,pointer in r["addresses"]:
                m = meta[eid]
                cid = m["call_id"]
                assert isinstance(cid,str) and cid
                role = m["node_kind"]
                true = stable(r["t"]+"/"+cid)
                sham = true
                calls[eid] = cid
                if role == "content.tool_argument":
                    assert cid not in prev_for, "duplicate argument event"
                    prev_for[cid] = previous
                    previous = cid
                else:
                    pred = prev_for.get(cid)
                    sham = stable(r["t"]+"/"+pred) if pred is not None else stable("orphan/"+eid)
                    edge_stats["outputs"] += 1
                    edge_stats["rerouted_to_earlier"] += int(pred is not None)
                keys.append((true,sham))
                roles.append(role)
            depths = collections.Counter()
            priorities = []
            blocks = r["blocks"]
            for e,a,b,c,nbyte in blocks:
                j = depths[e]
                priorities.append(((j,keys[e][0]),(j,keys[e][1])))
                depths[e] += 1
            costs = [b[3] for b in blocks]
            lex = [content_tokens(raw["fields"][r["addresses"][e][0]][a:b]) for e,a,b,_,_ in blocks]
            questions = [(qid, content_tokens(q)) for qid,q in raw["q"]]
            arms = {label:[keep, read(keep,costs,lex,questions)] for ip,label in enumerate(("shared","shifted"))
                    for keep in [select(costs,priorities,ip,8192)]}
            f.write(dump(dict(t=r["t"],arms=arms,calls=calls,roles=roles,stats=edge_stats))+"\n")
    return digest(out)

def run():
    seal = json.loads((HERE/"forecast-lock.json").read_bytes())
    for filename,h in seal["forecasts"].items():
        assert digest(HERE/filename)==h
    lock = dict(protocol=digest(HERE/"GRAPH_PROTOCOL_RU.md"),generator=digest(HERE/"graph_write.py"),
                inputs=digest(HERE/"forecast-lock.json"))
    with ProcessPoolExecutor(4) as pool:
        hashes = list(pool.map(worker,range(8)))
    lock["forecasts"]={f"graph-{s}.jsonl.gz":h for s,h in enumerate(hashes)}
    (HERE/"graph-lock.json").write_text(dump(lock),encoding="utf-8")
if __name__=="__main__":
    run()

