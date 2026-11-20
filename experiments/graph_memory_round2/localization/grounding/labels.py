"""Freeze features and model implementation first, then open both official targets."""
import hashlib,json,re,gzip
from pathlib import Path
import pyarrow.parquet as pq
HERE=Path(__file__).resolve().parent;ROOT=HERE.parent
h=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    lock=json.loads((HERE/"feature_lock.json").read_text())
    assert all(h(HERE/n)==d for n,d in lock.items())
    design={n:h(HERE/n) for n in ("model.py","PROTOCOL.md","METRIC_NOTE.md","features.py","features.jsonl.gz","feature_lock.json")}
    (HERE/"design_lock.json").write_text(json.dumps(design,indent=2),encoding="utf8")
    loc={r["instance_id"]:sorted({s.split(":")[0] for s in r["edit_functions"]}) for r in
         pq.read_table(ROOT/"input/locagent_test.parquet",columns=["instance_id","edit_functions"]).to_pylist()}
    verified=ROOT.parents[1]/"sota_round/coding/verified.parquet"
    other={r["instance_id"]:sorted({b for a,b in re.findall(r"^diff --git a/(\S+) b/(\S+)\s*$",r["patch"],flags=re.M)}) for r in
           pq.read_table(verified,columns=["instance_id","patch"]).to_pylist()}
    valid={};author_ok=norm_top1=dis=0;counts={}
    for s in (ROOT/"input/river.jsonl").read_text(encoding="utf8").splitlines():
        r=json.loads(s);g=r.get("gold_files") or [r["gold"].rsplit(":",1)[0]]
        single=r["gold"].rsplit(":",1)[0]
        first=r["candidates"][0]["source"]
        author=any(first.endswith(k) for k in g);exact=first.split("/",1)[1] in g
        author_ok+=author;norm_top1+=exact;dis+=author!=exact
        valid[r["id"]]={"any":g,"single":[single],"patch":other[r["id"]]}
    print("River original 500 author and normalized",author_ok,norm_top1,dis)
    lg={i:{"any":g,"single":g,"patch":g} for i,g in loc.items()}
    (HERE/"labels.json").write_text(json.dumps({"loc":lg,"river":valid}),encoding="utf8")
    (HERE/"metric_audit.json").write_text(json.dumps({"river_n":len(valid),"river_first_by_author":author_ok,
        "river_first_after_normalization":norm_top1,"river_disagreements_top1":dis,
        "loc_n":len(loc),"n_distinct_gold_targets":{s:sum(len(x["any"])>1 for x in vals.values()) for s,vals in (("loc",lg),("river",valid))}},
        indent=2),encoding="utf8")
if __name__=="__main__":main()

