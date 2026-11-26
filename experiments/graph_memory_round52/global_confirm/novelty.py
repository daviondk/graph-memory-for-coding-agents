"""ID-only lookup on historical archived panels. Does not parse historical gold or test labels."""
from collections import Counter
from pathlib import Path
import gzip
import re
import pyarrow.parquet as pq
from panel import HERE,S,DEV,PAR,canon,read,save,hashfile

def main():
    roots=HERE.parents[1]
    qmap={r["_id"]:r["question"] for b in pq.ParquetFile(PAR).iter_batches(columns=["_id","question"]) for r in b.to_pylist()}
    qmap.update(read(DEV/"questions.json.gz"))
    known=set(qmap)
    # Scan only address-bearing/input artifacts; never load a support, gold or evaluated-output file.
    neg=("gold","support","grade","result","outcome","answer","audit","comparison","score","manifest","release","statistic")
    files=[f for rnd in (49,50,51) for f in (roots/f"graph_memory_round{rnd}").rglob("*") if f.is_file()
           and f.name.lower().endswith((".json",".json.gz",".jsonl",".jsonl.gz",".tsv"))
           and not any(s in f.name.lower() for s in neg)]
    files += list(Path("D:/CodexResearch").glob("x20-r*/visible*.json.gz"))
    seen=set();info=[]
    pattern=re.compile(rb"(?<![a-fA-F0-9])[a-fA-F0-9]{32}(?![a-fA-F0-9])")
    panel=read(S/"questions.json.gz")
    for f in sorted(files):
        b=f.read_bytes()
        if f.suffix==".gz":b=gzip.decompress(b)
        ids={m[0].decode().lower() for m in pattern.finditer(b)}&known
        seen|=ids
        if ids:
            info.append([f.name if "x20-r" not in str(f) else f.parent.name+"/"+f.name,
                         str(f.relative_to(roots)).replace("\\","/") if f.is_relative_to(roots) else str(f),
                         len(ids),len(ids&set(panel)),hashfile(f)])
    known_q={canon(qmap[k]) for k in seen}
    also=sorted(q for q,t in panel.items() if q in seen or canon(t) in known_q)
    pool=sorted(set(panel)-set(also))
    out={"all":len(panel),"ever_unseen_ids":pool,"excluded":also,"history_ids":len(seen),"history_questions":len(known_q),
         "files_scanned":len(files),"matching_inputs":info,"overlap_id":len(set(panel)&seen),
         "overlap_normalized_only":len(also)-len(set(panel)&seen),"addendum":hashfile(HERE/"NOVELTY_ADDENDUM_RU.md")}
    save(HERE/"novelty.json",out)
    print("secondary clean",len(pool),"excluded",len(also),"files",len(files),"old ids",len(seen))

if __name__=="__main__":main()

