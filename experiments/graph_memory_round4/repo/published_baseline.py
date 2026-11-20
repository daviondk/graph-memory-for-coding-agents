"""Use the authors' exact Python BM25 scorer, original crop and original per-level RNG."""
import gzip,json
from datetime import datetime,timezone
from data_io import *
from native_run import load_module

def main():
    load_module("common","publisher_common.py");load_module("arms","publisher_arms.py")
    official=load_module("repobench","publisher_repobench.py")
    keep=read("roster.json");output={}
    for lang in ("java","python"):
        with gzip.open(D/("lexical_"+lang+".jsonl.gz"),"wt",encoding="utf8") as f:
            for p in files(lang,"test"):
                select=dict(keep[p.stem])
                for i,row in enumerate(rows(p,["code","context"])):
                    if i not in select:continue
                    for k in (3,10):
                        order=official.bm25_rank(official.crop(row["code"],k),row["context"])
                        f.write(json.dumps([panel_name(p.stem),select[i],k,order],separators=(",",":"))+"\n")
        output[lang]=sha(D/("lexical_"+lang+".jsonl.gz"))
    write("lexical_lock.json",{"utc":datetime.now(timezone.utc).isoformat(),"sha256":output})
if __name__=="__main__":main()
