"""Re-rank all common provenance units with equally weighted, exact reciprocal ranks."""
from collections import Counter
from fractions import Fraction
from pathlib import Path
import gzip
import hashlib
import json
import sys
import time

HERE=Path(__file__).resolve().parent
OFF=HERE.parents[1]/"isetrace_official"
E5=HERE.parents[1]/"isetrace_e5"
K=60
B=2048
POLICIES=("prefix","skip","related","value")

def load(path):
    raw=path.read_bytes()
    return json.loads(gzip.decompress(raw) if path.suffix==".gz" else raw)

def digest(path):
    with path.open("rb") as handle:return hashlib.file_digest(handle,"sha256").hexdigest()

def save(name,value):
    data=json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(",",":")).encode()+b"\n"
    path=HERE/name
    if path.suffix==".gz":data=gzip.compress(data,mtime=0)
    if path.is_file():
        assert path.read_bytes()==data, name
        return
    tmp=path.with_suffix(".tmp")
    tmp.write_bytes(data);tmp.replace(path)

def lock():
    assert not (E5/"forecast-seal.json").exists() and not (E5/"results.json").exists()
    save("plan-seal.json",{"protocol":digest(HERE/"PROTOCOL_RU.md"),"predict":digest(Path(__file__)),
        "bm25_forecast_seal":digest(OFF/"forecast-lock.json"),"e5_plan_seal":digest(E5/"plan-seal.json"),
        "metadata":digest(OFF/"placebo-event-metadata.json.gz"),"cohort":digest(OFF/"cohort.json")})

def check_plan():
    frozen=load(HERE/"plan-seal.json")
    assert frozen=={"protocol":digest(HERE/"PROTOCOL_RU.md"),"predict":digest(Path(__file__)),
        "bm25_forecast_seal":digest(OFF/"forecast-lock.json"),"e5_plan_seal":digest(E5/"plan-seal.json"),
        "metadata":digest(OFF/"placebo-event-metadata.json.gz"),"cohort":digest(OFF/"cohort.json")}
    assert load(OFF/"placebo-forecast-lock.json")["placebo-event-metadata.json.gz"]==frozen["metadata"]
    for base,key in ((OFF,"forecast-lock.json"),(E5,"forecast-seal.json")):
        seal=load(base/key)
        assert seal["plan"]==digest(base/("ranking-plan.json" if base==OFF else "plan-seal.json"))
        for n,h in seal["forecasts"].items():assert digest(base/n)==h,n

def bm_shard(i):
    with gzip.open(OFF/f"forecasts-shard-{i}.jsonl.gz","rb") as rows:
        for line in rows:
            r=json.loads(line)
            for q,v in r["queries"].items():
                yield q,r["trajectory_id"],v["provenance"]

def rr(rrs):
    out=[n["node_id"] for n in rrs]
    assert len(set(out))==len(out)
    return out

def pack(order,score,sizes,event):
    prefix=[];remaining=B
    for n in order:
        if sizes[n]>remaining:break
        prefix.append(n);remaining-=sizes[n]
    tails=order[len(prefix):]
    keep={event[n] for n in prefix if event[n][0]>=0}
    def related(n):
        cid,role=event[n]
        return (cid,{"a":"o","o":"a"}[role]) in keep
    suffix={"skip":tails,"related":sorted(tails,key=lambda n:not related(n)),
        "value":sorted(tails,key=lambda n:(-(score[n]**2/sizes[n]),n))}
    chosen={"prefix":prefix}
    for name,tail in suffix.items():
        chosen[name]=list(prefix);rest=remaining
        for n in tail:
            if sizes[n]<=rest:
                chosen[name].append(n);rest-=sizes[n]
    return chosen

def predict():
    check_plan()
    split={r["query_id"]:r["trajectory_id"] for r in load(OFF/"cohort.json")}
    meta=load(OFF/"placebo-event-metadata.json.gz")
    records=[];seen=set();counts=Counter();pairs=Counter();start=time.perf_counter()
    for i in range(8):
        dense={r["q"]:r for r in load(E5/f"forecasts-main-{i}.json.gz")}
        for q,t,view in bm_shard(i):
            ds=dense.pop(q);assert t==ds["t"]==split[q] and q not in seen;seen.add(q)
            border=rr(view["ranked"]);dorder=rr(ds["rr"])
            assert set(border)==set(dorder)
            dp={n["node_id"]:n for n in ds["rr"]}
            rankb={n:j for j,n in enumerate(border,1)};rankd={n:j for j,n in enumerate(dorder,1)}
            sizes={};event={}
            for n in view["ranked"]:
                k=n["node_id"]
                assert n["source_spans"]==dp[k]["source_spans"] and len(n["source_spans"])==1
                sizes[k]=n["token_count"];assert sizes[k]==dp[k]["token_count"] and sizes[k]>0
                sp=n["source_spans"][0];cid,role,_=meta[t][sp["event_id"]]
                assert sp["json_pointer"]=={"a":"/raw_arguments","o":"/content"}[role]
                event[k]=(cid,role)
            scores={n:Fraction(1,K+rankb[n])+Fraction(1,K+rankd[n]) for n in border}
            order=sorted(border,key=lambda n:(-scores[n],n))
            choices=pack(order,scores,sizes,event)
            keys=sorted(border);idx={n:j for j,n in enumerate(keys)}
            records.append({"q":q,"t":t,"shard":i,"rank_sha":hashlib.sha256("\n".join(order).encode()).hexdigest(),
                "arms":{k:[idx[n] for n in val] for k,val in choices.items()}})
            counts["queries"]+=1;counts["candidate_instances"]+=len(keys)
            counts["queries_with_any_equal_rrf_score"]+=len(set(scores.values()))<len(scores)
        assert not dense
    assert seen==set(split) and len(seen)==2000
    save("forecasts.json.gz",records)
    save("forecast-seal.json",{"plan":digest(HERE/"plan-seal.json"),"forecasts":digest(HERE/"forecasts.json.gz"),
        "bm25_seal":digest(OFF/"forecast-lock.json"),"dense_seal":digest(E5/"forecast-seal.json"),
        "counts":dict(counts)})
    print("sealed",counts,"pairing, sorting, IO and forecast writing seconds",round(time.perf_counter()-start,3))
if __name__=="__main__":{"lock":lock,"predict":predict}[sys.argv[1]]()
