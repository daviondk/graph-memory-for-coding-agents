"""Prepare 74 history graphs independently of held-out outcomes. Raw evidence stays in a private cache."""
import os
import sys
from pathlib import Path
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent))
import study as s
sys.path.insert(0,str(s.RES))
from setup_graph import pilot,RAW
from graph_memory.datasets.isetrace.adapter import parse_isetrace_record,adapt_isetrace_record
PRIVATE=Path(os.environ.get("TYPED_DATA","D:/CodexResearch/x20-typed-reader-private"))
OLD=s.HERE.parent.parent/"graph_memory_round19/write_transfer"
DEV_RAW=Path("D:/CodexResearch/x20-isetrace-runtime/write-dev-private/projection")

def main():
    PRIVATE.mkdir(parents=True,exist_ok=True)
    ix=s.graph_index()
    full=s.read(OLD/"cohort.json");reg=s.read(s.TR/"split.json.gz")
    dev_ids={r["q"] for r in reg["dev"]};dev_tra={r["t"] for r in reg["dev"]};train_tra={r["t"] for r in reg["train"]}
    subset=[r for r in full if r["q"] not in dev_ids]
    assert len(subset)==80 and all(not r["publication_dev500"] for r in subset)
    tids={r["t"] for r in subset}
    assert len(tids)==74 and not tids&train_tra
    sh={p.name.split("-",1)[-1].split(".",1)[0]:int(p.name.split("-",1)[0]) for p in DEV_RAW.glob("*.json.gz")}
    missing=tids-set(ix)
    assert all(t in sh for t in missing)
    tok=pilot.offsets(pilot.Tokenizer.from_file(str(pilot.CACHE/"tokenizer.json")))
    raw_lock={r["path"].split("/")[-1]:r["sha256"] for r in s.read(s.OFF/"source-lock.json")}
    inv={t:dict(native=True,sha=d,shard=sh[t]) for t,(p,d) in ix.items() if t in tids}
    for i in sorted({sh[t] for t in missing}):
        source=RAW/f"trajectories-{i:05d}.jsonl"
        assert s.sha(source)==raw_lock[source.name]
        want={t for t in missing if sh[t]==i}
        for raw,obj in pilot.stream(source):
            t=obj["session_id"]
            if t not in want:continue
            tr=adapt_isetrace_record(parse_isetrace_record(obj),source_revision=pilot.RAW[1])
            g=pilot.native.build_provenance_graph(tr,content_chunker=lambda ss:pilot.token_chunks(ss,tokenizer=tok,max_tokens=504,overlap_tokens=64))
            old=s.read(DEV_RAW/f"{i}-{t}.json.gz")
            pool=pilot.native.provenance_unit_candidates(g)
            assert len(pool)==len(old["pool"])
            for x,y in zip(pool,old["pool"],strict=True):
                assert [v.model_dump() for v in x.source_spans]==y["source_spans"]
            f=PRIVATE/f"{t}.json.gz"
            s.put(f,dict(t=t,g=g.model_dump(),split="extended_dev",raw_source=__import__("hashlib").sha256(raw).hexdigest()))
            inv[t]=dict(native=False,sha=s.sha(f),shard=i,pu=len(pool))
    assert set(inv)==tids
    s.put(HERE/"source-plan.json",dict(queries={r["q"]:r["t"] for r in subset},records=inv,
      novel_trajectories=sorted(tids-dev_tra),shared=len([r for r in subset if r["t"] in dev_tra]),new=len([r for r in subset if r["t"] not in dev_tra]),
      fixed_protocol=s.sha(HERE/"PROTOCOL_RU.md"),source=s.sha(OLD/"cohort.json"),code=s.sha(Path(__file__))))
    print("graphs",len(tids),"newly built",len(missing),flush=True)
if __name__=="__main__":main()
