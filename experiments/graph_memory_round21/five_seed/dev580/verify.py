"""Validate every sealed checkpoint decision and input pairing without ML dependencies."""
from pathlib import Path
import gzip
import hashlib
import json
from statistics import mean

HERE=Path(__file__).resolve().parent
def read(p):return json.loads(gzip.decompress(p.read_bytes()) if p.suffix==".gz" else p.read_bytes())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    full=HERE.parents[2]/"graph_memory_round22/native_multiseed/official580/split.json.gz"
    ids=[r["q"] for r in read(full)["dev"]]
    plan=read(HERE/"plan.json")
    assert [len(ids[:500]),len(ids),len(set(ids))]==[500,580,580]
    complete=[];links=[]
    for s in plan["seeds"]:
        o=HERE/f"seed-{s}";p=o/"selection.json"
        if not p.exists():continue
        r=read(p)
        assert r["seed"]==s and sha(full)==r["split"] and sha(HERE/"plan.json") in r["plans"]
        for n in (500,580):
            scores=[]
            for ep in (0,1):
                name=f"dev{n}-e{ep}-rows.json.gz";rp=o/name;m=read(o/f"dev{n}-e{ep}.json")
                assert sha(rp)==m["rows"]==r["per_query"][name]
                rows=read(rp);assert set(rows)==set(ids[:n]) and m["n"]==len(rows)
                assert m["ordered_q_sha"]==hashlib.sha256(("\n".join(ids[:n])+"\n").encode()).hexdigest()
                for k in ("recall_at_2","recall_at_5","recall_at_10","mrr"):
                    vs=[rows[q][k] for q in ids[:n]];assert all(0<=v<=1 for v in vs)
                    assert abs(mean(vs)-r["metrics"][str(n)][ep]["dev_"+k])<1e-12
                    assert r["metrics"][str(n)][ep]["dev_"+k]==m["means"]["dev_"+k]
                scores.append(m["means"]["dev_recall_at_5"])
            assert r[f"epoch_{n}"]==int(scores[1]>scores[0])
        assert r["same_choice"]==(r["epoch_500"]==r["epoch_580"])
        if r["same_choice"]:assert r["weight_500"]==r["weight_580"]
        if (o/"test-link.json").exists():
            l=read(o/"test-link.json");assert l["n"]==2000 and l["selection_sha"]==sha(p) and l["weight"]==r["weight_580"]
            d=HERE.parent/f"seed-{s}" if l["status"]=="shared-weights" else HERE/"alternative"/(f"seed-{s}" if s!=13 else "seed-113")
            assert l["metrics_sha"]==sha(d/"metrics.json.gz") and l["results_sha"]==sha(d/"results.json")
            links.append(s)
        complete.append(s)
    print("validated checkpoint selections",complete,"test receipts",links,"pending",sorted(set(plan["seeds"])-set(complete)))
if __name__=="__main__":main()

