"""Check the five-seed aggregate, align query types and reconstruct the published ablation."""
from pathlib import Path
from collections import defaultdict,Counter
from statistics import mean,stdev
import json,hashlib,gzip
D=Path(__file__).resolve().parent
OTHER=D.parent/"isetrace_five_seeds"
META=Path("D:/CodexResearch/x20-isetrace-runtime/inputs/query-authoring/isetrace-v7-raw.jsonl.metadata.jsonl")
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    src=json.loads((OTHER/"source.json").read_bytes());p=OTHER/"per-query.json.gz"
    assert sha(p)==src["rows_sha"];doc=json.loads(gzip.decompress(p.read_bytes()));i=doc["metrics"].index("full_support_2048")
    types={a["query_id"]:a for a in map(json.loads,META.open(encoding="utf8"))}
    values=defaultdict(lambda:defaultdict(list));ids=defaultdict(set);tr=set()
    for s,q,t,b,f in doc["rows"]:
        assert q not in ids[s] and t==types[q]["trajectory_id"] and b[i] in [0,1] and f[i] in [0,1];ids[s].add(q);tr.add(t)
        for k in (types[q]["memory_mode"],"all"):
            values[k][s].append((b[i],f[i]))
    assert len(tr)==1207 and list(sorted(ids))==[13,17,29,37,41] and all(v==ids[13] for v in ids.values()) and len(ids[13])==2000
    reference={"direct_recall":[84.43,85.52],"linked_recall":[79.85,81.99],"multi_fact_recall":[62.25,61.99]}
    rows={}
    for k,byseed in values.items():
        means=[[100*mean(z[j] for z in byseed[s]) for s in sorted(byseed)] for j in (0,1)]
        rows[k]=dict(n=len(byseed[13]),dense_mean=mean(means[0]),factor_mean=mean(means[1]),sample_sd=[stdev(y) for y in means],dense_by_seed=means[0],factor_by_seed=means[1])
    marg=[sum(rows[k]["n"]*vals[j]/2000 for k,vals in reference.items()) for j in (0,1)]
    assert round(marg[0],2)==77.33 and round(marg[1],2)==78.59 and abs(marg[1]-77.33-1.26)<.01
    assert all(x["epoch_500"]==x["epoch_580"]==1 and x["weight_500"]==x["weight_580"] for x in src["test_weight_selections"].values())
    out={"rows_sha":sha(p),"metadata_sha":sha(META),"source_sha":sha(OTHER/"source.json"),"cohorts":rows,"published_table3_percent":reference,"published_weighted":marg,"trajectories":len(tr)}
    (D/"audit.json").write_text(json.dumps(out,sort_keys=True,indent=2)+'\n',encoding='utf8')
    for k,r in rows.items():print(k,r['n'],round(r['dense_mean'],2),round(r['factor_mean'],2),r['factor_by_seed'])
    print(marg)
if __name__=="__main__":main()