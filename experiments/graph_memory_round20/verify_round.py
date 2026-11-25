"""Cross-study checks on the released decisions, including unchanged common baselines."""
import hashlib
import gzip
import json
import math
import sys
from pathlib import Path
D=Path(__file__).resolve().parent
def load(p):
    b=p.read_bytes();return json.loads(gzip.decompress(b) if p.suffix==".gz" else b)
def sha(p):
    with p.open("rb") as f:return hashlib.file_digest(f,"sha256").hexdigest()
def check():
    checkfiles={};mismatch=0;shared={}
    folders=[D/"fine_read",D/"fine_train",D/"fine_lextrain",D/"fine_subset/availability",D/"fine_subset/hash64"]
    for stage,n in (("dev",500),("dense",2000),("rgcn_availability",2000),("rgcn_hash64",2000),("rgcn",2000)):
        ref=None;count=0
        for folder in folders:
            p=folder/(stage+"-outcomes.json.gz")
            if not p.exists():continue
            rows=load(p);checkfiles[p.relative_to(D).as_posix()]=sha(p);count+=1
            ids=set(rows["skip"]);assert len(ids)==n
            for arm,vals in rows.items():
                assert set(vals)==ids and all(v["tokens"]<=2048 and 0<=v["density"]<=1 and 0<=v["coverage"]<=1 and bool(v["full_support"])==(v["coverage"]==1) for v in vals.values())
            keys=("prefix","skip","rrf","parent");component={k:rows[k] for k in keys}
            if ref is None:ref=component
            else:assert ref==component,(stage,folder)
            summaries=load(folder/(stage+"-results.json"));assert summaries["n"]==n
            for k,recs in rows.items():
                assert summaries["summary"][k]["hits"]==sum(v["full_support"] for v in recs.values())
                for attr in ("coverage","density","tokens","f1"):
                    assert math.isclose(sum(v[attr] for v in recs.values())/n,summaries["summary"][k][attr],abs_tol=1e-10)
                if k!="skip":
                    contrast=summaries["pairs"][k+"-skip"];assert contrast["fs_wins"]-contrast["fs_losses"]==summaries["summary"][k]["hits"]-summaries["summary"]["skip"]["hits"]
        if count:shared[stage]={"compared_models":count,"n":n}
    stable=load(D/"online_update/outcomes.json.gz")["frozen"];orig=load(D/"set_writer/test-outcomes.json.gz")["read/frozen"]
    assert stable==orig and len(stable)==2000
    writer_controls={}
    for stage,n in (("test",2000),("dev",580)):
        degree=load(D/"degree_write"/(stage+"-outcomes.json.gz"))
        reference=load(D/"set_writer"/(stage+"-outcomes.json.gz"))
        for arm in ("archive/frozen","read/frozen"):
            assert len(degree[arm])==n and degree[arm]==reference[arm],(stage,arm)
        writer_controls[stage]=n
    dr=load(D/"dialogue_stream/outcomes.json.gz");ab=load(D/"dialogue_stream/components-outcomes.json.gz")
    for q,r in dr.items():
        u=ab[q]
        for arm in ("base","cal"):
            cell=r["4096/"+arm];hit=u["arms"][arm]["hit"]
            assert cell["recall"]==(hit/u["p"] if u["p"] else None) and cell["paid"]==u["arms"][arm]["tokens"]
    assert len(dr)==62 and len(ab)==500
    return {"matched_packing_decisions_scored":shared,"identical_writer_baselines":len(stable),"degree_writer_shared_controls":writer_controls,"identical_causal_dialogue_histories":len(dr),
            "all_dialogue_histories":len(ab),"data_files":checkfiles,"code":sha(D/"verify_round.py")}
if __name__=="__main__":
    result=check();dest=D/"cross-study-audit.json"
    if "--write" in sys.argv:dest.write_text(json.dumps(result,sort_keys=True,separators=(",",":"))+"\n",encoding="utf8")
    elif dest.exists():assert result==load(dest)
    print("PASS",result["matched_packing_decisions_scored"])
