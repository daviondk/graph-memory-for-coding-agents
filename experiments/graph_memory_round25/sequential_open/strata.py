"""Post hoc characterization using the number of evidence fields missing before the first call."""
from collections import defaultdict
from pathlib import Path
import gzip,json
D=Path(__file__).resolve().parent
def rd(p):return json.loads(gzip.decompress(p.read_bytes()) if p.suffix==".gz" else p.read_bytes())
def main():
    ceiling=rd(D.parents[1]/"graph_memory_round24/attainable_open/per-query.json.gz")
    trials=rd(D/"per-query.json.gz")["corpora"]
    rows={}
    for corpus,records in trials.items():
        counts=defaultdict(lambda:defaultdict(int))
        for q,r in records.items():
            c=ceiling[corpus][q]
            if c["base"]:key="already_complete"
            elif c["missing_fields"]>1:key="several_missing_fields"
            elif c["field_visible"]:key="one_visible_missing_field"
            else:key="one_unseen_missing_field"
            group=counts[key];group["n"]+=1
            for a in ("first","frozen","any","balanced","tail"):group[a]+=r["steps"][a+"/cap"][0]
        if "one_unseen_missing_field" in counts:assert not any(v for k,v in counts["one_unseen_missing_field"].items() if k!="n")
        rows[corpus]=counts
    (D/"strata.json").write_text(json.dumps(rows,sort_keys=True,indent=2)+"\n",encoding="utf8")
    print(rows)
if __name__=="__main__":main()
