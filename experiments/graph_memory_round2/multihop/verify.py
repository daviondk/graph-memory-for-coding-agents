"""Independent direct scorer for complete evidence and frozen predictions. No estimator is imported."""
from pathlib import Path
import gzip,hashlib,json,collections
import pyarrow.parquet as pq

HERE=Path(__file__).resolve().parent
def dig(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(name):return json.loads((HERE/name).read_text(encoding="utf8"))
def rows(name):
    return [json.loads(z) for z in gzip.open(HERE/name,"rt",encoding="utf8")]
def idx_gold(ids,titles):
    return {i for i,t in enumerate(titles) if t in ids}
def main():
    official={}
    groups={}
    def saved(name,leaf,aggregate,match):
        lock=read(leaf)
        assert dig(HERE/name)==lock[match]
        for row in rows(name):
            scope=row.get("dataset","hotpot");uid=row["id"]
            groups[scope,uid]=row.get("split","all")
            assert (scope,uid) not in official
            official[scope,uid]=row
    saved("predictions.jsonl.gz","prediction_lock.json","results.json","sha256")
    saved("transfer_predictions.jsonl.gz","transfer_lock.json","transfer_results.json","prediction_sha256")
    gold={}
    nums=collections.defaultdict(int)
    for scope,path in (("hotpot","dev.parquet"),("h2","transfer-train-half.parquet")):
        for batch in pq.ParquetFile(HERE/"inputs"/path).iter_batches(batch_size=256,columns=["id","context.title","supporting_facts.title"]):
            for r in batch.to_pylist():
                tag=scope,r["id"]
                if tag in official:
                    assert official[tag]["titles"]==r["context"]["title"]
                    gold[tag]=set(r["supporting_facts"]["title"])
    for r in pq.read_table(HERE/"inputs/2wiki-dev.parquet",columns=["_id","context","supporting_facts"]).to_pylist():
        tag="w2",r["_id"]
        if tag in official:
            assert official[tag]["titles"]==[p[0] for p in json.loads(r["context"])]
            gold[tag]={t for t,i in json.loads(r["supporting_facts"])}
    for line in (HERE/"inputs/musique-dev.jsonl").open(encoding="utf-8"):
        r=json.loads(line);tag="mu",r["id"]
        if tag in official:
            assert official[tag]["titles"]==[p["title"] for p in r["paragraphs"]]
            gold[tag]={i for i,p in enumerate(r["paragraphs"]) if p["is_supporting"]}
    assert len(gold)==len(official)==12657
    native={a:read("inputs/"+b) for a,b in (("hotpot","beam.json"),("w2","2wiki-beam.json"),("mu","musique-beam.json"))}
    for tag,r in official.items():
        scope,uid=tag
        if scope in native: assert set(r["pred"]["beam"])==set(native[scope][uid])
        for a,p in r["pred"].items():
            assert len(p)==2 and len(set(p))==2 and all(0<=i<len(r["titles"]) for i in p)
            val={r["titles"][i] for i in p} if scope!="mu" else set(p)
            solved=int(val==gold[tag])
            nums[scope,groups[tag],a]+=solved
    s=read("results.json")
    for ss in ("cal","test"):
        for a,v in s[ss]["totals"].items():assert nums["hotpot",ss,a]==v["hits"]
    t=read("transfer_results.json")
    for scope,data in t.items():
        for a,val in data["hits"].items():assert nums[scope,"all",a]==val
    rosters=collections.Counter(a for a,b in official)
    summary={"score_checks":"all available methods vs original context order/official gold",
             "source_prediction_hashes":{p:dig(HERE/p) for p in ("predictions.jsonl.gz","transfer_predictions.jsonl.gz")},
             "question_instances":dict(rosters),"predictions_validated":sum(len(r["pred"]) for r in official.values()),
             "prot_sha256":{p.name:dig(p) for p in HERE.glob("*PROTOCOL.md")}}
    (HERE/"verification.json").write_text(json.dumps(summary,indent=2),encoding="utf8")
    print(summary["question_instances"],summary["predictions_validated"])
if __name__=="__main__": main()

