"""Independent roster, score and count check for the 2Wiki replication."""
import gzip,hashlib,json,itertools
from pathlib import Path
from collections import Counter
import pyarrow.parquet as pq
from scipy.stats import binomtest
ROOT=Path(__file__).resolve().parent
def read(name):
    with gzip.open(ROOT/name,"rt",encoding="utf8") as f:return [json.loads(x) for x in f]
def main():
    pred=read("typed_predictions.jsonl.gz");scores=read("typed_item_scores.jsonl.gz")
    assert hashlib.sha256((ROOT/"typed_predictions.jsonl.gz").read_bytes()).hexdigest()==json.loads((ROOT/"typed_lock.json").read_text())["prediction_sha256"]
    old={r["id"] for r in read("transfer_predictions.jsonl.gz") if r["dataset"]=="w2"}
    data=pq.read_table(ROOT/"inputs"/"2wiki-dev.parquet",columns=["_id","type","context","supporting_facts"]).to_pylist()
    order=sorted((r for r in data if r["type"]!="bridge_comparison"),key=lambda r:hashlib.sha256(("external-wiki-261118|"+r["_id"]).encode()).hexdigest())
    assert old=={r["_id"] for r in order[:2000]}
    truth={r["_id"]:r for r in order[2000:6000]}
    assert len(truth)==len(pred)==len(scores)==4000
    assert set(truth)=={r["id"] for r in pred}=={r["id"] for r in scores}
    s={r["id"]:r for r in scores};native=json.loads((ROOT/"inputs"/"2wiki-beam.json").read_text())
    counts=Counter();n=0
    for r in pred:
        uid=r["id"];src=truth[uid]
        titles=[t for t,ss in json.loads(src["context"])]
        gold={t for t,i in json.loads(src["supporting_facts"])}
        assert titles==r["titles"] and len(gold)==2
        assert set(native[uid])==set(r["pred"]["beam"])
        for a,ids in r["pred"].items():
            assert len(ids)==len(set(ids))==2
            n+=1;acc=int({titles[i] for i in ids}==gold)
            counts[a]+=acc;assert acc==s[uid]["hits"][a]
    res=json.loads((ROOT/"typed_results.json").read_text())
    assert counts==res["hits"]
    for pair,v in res["contrasts"].items():
        a,b=pair.split("-");d=[r["hits"][a]-r["hits"][b] for r in scores]
        assert sum(d)/len(d)==v["delta"] and (d.count(1),d.count(-1))==(v["wins"],v["losses"])
    record={"verified_selections":n,"questions":len(truth),"previous_ids_overlap":len(set(truth)&old),"recount":dict(counts)}
    (ROOT/"typed_verification.json").write_text(json.dumps(record,indent=2),encoding="utf8")
    print(json.dumps(record))
if __name__=="__main__":main()
