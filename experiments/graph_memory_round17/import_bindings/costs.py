"""Paired cold-process cost of the import/protocol observer on unchanged Colorama."""
import gzip
import json
import platform
from pathlib import Path
from statistics import median
from cli_check import study
from experiment import ROOT,sha,save,provenance

def main():
    base=Path("D:/CodexResearch/x20-r17-import-binding-runs")/("costs-"+sha(Path(__file__).read_bytes())[:16])
    study.checkout(base)
    rows=[]
    for replicate in range(5):
        pair={}
        for mode in ((False,True) if replicate%2==0 else (True,False)):
            tag=("trace" if mode else "control")
            row=study.run(base,f"{replicate}-{tag}",study.FILES,trace=mode)
            assert len(row["obs"]["outcomes"])==26 and all(study.positive(x) for x in row["obs"]["outcomes"].values())
            pair[tag]=row["seconds"]
        rows.append(pair)
    obs=json.loads(gzip.decompress((ROOT/"colorama-warm.gz").read_bytes()))["obs"]
    binds,opaque,all_calls=provenance(study.source(study.MODULE),obs)
    graph={k:sorted(v) for k,v in binds.items() if v}
    retained_bytes=len(json.dumps({"defined":graph,"unknown":sorted(opaque),"per_test":obs["tests"]},
                                 separators=(",",":"),sort_keys=True).encode())
    save("costs.json",dict(pairs=rows,median_control_seconds=median(r["control"] for r in rows),
                           median_trace_seconds=median(r["trace"] for r in rows),
                           median_paired_extra_seconds=median(r["trace"]-r["control"] for r in rows),
                           compact_serialization_bytes=retained_bytes,scope="fresh pytest processes, shared host"))
    print((ROOT/"costs.json").read_text())


if __name__=="__main__":
    main()

