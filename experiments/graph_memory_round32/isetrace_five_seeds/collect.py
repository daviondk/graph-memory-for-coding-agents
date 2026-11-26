"""Export aligned per-question measurements from verified five-seed receipts."""
from pathlib import Path
import gzip,hashlib,json,shutil
HERE=Path(__file__).resolve().parent
SOURCE=HERE.parents[1]/"graph_memory_round21/five_seed"
METRICS=("coverage_512","coverage_1024","coverage_2048","full_support_2048","recall_5","mrr","coverage_auc","full_support_auc")
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def get(p):return json.loads(gzip.decompress(p.read_bytes()) if p.suffix==".gz" else p.read_bytes())
def put(p,data):
    b=(json.dumps(data,sort_keys=True,separators=(",",":"))+"\n").encode()
    p.write_bytes(gzip.compress(b,mtime=0) if p.suffix==".gz" else b)
def main():
    result=get(SOURCE/"five-seed-results.json")
    hashes={k:sha(SOURCE/k) for k in ("plan.json","score.py","study.py","verify.py","five-seed-results.json","PROTOCOL_RU.md")}
    cases=[];cal={}
    for seed in result["seeds"]:
        root=SOURCE/f"seed-{seed}";selection=SOURCE/f"dev580/seed-{seed}/selection.json";link=selection.with_name("test-link.json")
        for p in (root/"metrics.json.gz",root/"forecast-seal.json",root/"results.json",selection,link):
            hashes[p.relative_to(SOURCE).as_posix()]=sha(p)
        record=get(selection);test=get(link)
        assert result["results"][str(seed)]==sha(root/"results.json")
        assert test["results_sha"]==sha(root/"results.json") and test["metrics_sha"]==sha(root/"metrics.json.gz")
        assert record["weight_500"]==record["weight_580"]==test["weight"]
        cal[seed]={k:record[k] for k in ("epoch_500","epoch_580","weight_500","weight_580","metrics")}
        rows=get(root/"metrics.json.gz");assert set(rows["dense"])==set(rows["factor"])
        for q in sorted(rows["dense"]):
            first=rows["dense"][q];second=rows["factor"][q];assert first["t"]==second["t"]
            cases.append([seed,q,first["t"],[first[m] for m in METRICS],[second[m] for m in METRICS]])
    put(HERE/"per-query.json.gz",{"columns":["seed","query","trajectory","dense","factor"],"metrics":METRICS,"rows":cases})
    shutil.copyfile(SOURCE/"five-seed-results.json",HERE/"results.json")
    put(HERE/"source.json",{"source":"../../graph_memory_round21/five_seed","hashes":hashes,"test_weight_selections":cal,
         "rows_sha":sha(HERE/"per-query.json.gz"),"results":sha(HERE/"results.json"),"collector":sha(Path(__file__))})
if __name__=="__main__":main()
