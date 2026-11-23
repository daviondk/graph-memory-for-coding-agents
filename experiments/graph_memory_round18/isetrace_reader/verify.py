"""Stand-alone, standard-library audit of all received actions and their actual evidence coverage."""
from collections import defaultdict
from pathlib import Path
import gzip
import hashlib
import json
from statistics import mean

D=Path(__file__).resolve().parent
def load(p):
    b=p.read_bytes();return json.loads(gzip.decompress(b) if p.suffix==".gz" else b)
def sha(p):
    with p.open("rb") as f:return hashlib.file_digest(f,"sha256").hexdigest()
def union(spans):
    fields=defaultdict(list)
    for s in spans:fields[s["event_id"],s["json_pointer"]].append((s["char_start"],s["char_end"]))
    out={}
    for k,parts in fields.items():
        merged=[]
        for a,b in sorted(parts):
            if merged and a<=merged[-1][1]:merged[-1]=(merged[-1][0],max(merged[-1][1],b))
            else:merged.append((a,b))
        out[k]=merged
    return out
def metrics(gold,records):
    spans=[s for r in records for s in r["spans"]];g=union(gold);v=union(spans)
    needed=sum(b-a for p in g.values() for a,b in p)
    overlap=sum(max(0,min(b,y)-max(a,x)) for k,p in g.items() for a,b in p for x,y in v.get(k,[]))
    total=sum(s["char_end"]-s["char_start"] for s in spans)
    return dict(full_support=int(needed==overlap),coverage=overlap/needed,density=overlap/total if total else 0)
def main():
    for f,digest in load(D/"MANIFEST_SHA256.json").items():assert sha(D/f)==digest
    gold=load(D/"gold-panel-spans.json.gz");outcomes=load(D/"outcomes.json.gz");summary=load(D/"results.json")
    unique=set();qs=set();ts=set()
    parts={}
    for name,path in (("different",D),("same",D/"matched_controls")):
        panel=load(path/"panel.json.gz");receipt=load(path/"response-lock.json")
        assert receipt["responses"]==sha(path/"open-receipts.jsonl")
        rows=[json.loads(line) for line in (path/"open-receipts.jsonl").read_bytes().splitlines()]
        calls={a["prompt_sha256"]:a for a in rows};assert len(calls)==receipt["attempts"]==len(rows)
        assert unique.isdisjoint(calls);unique.update(calls)
        for q,entry in panel.items():
            assert q not in qs and entry["t"] not in ts
            qs.add(q);ts.add(entry["t"])
            shown={}
            for arm,meta in entry["arms"].items():
                pred=calls[meta["prompt_sha256"]];ids={z["id"]:z for z in meta["fragments"]}
                assert sorted(ids)==list(ids) and len(ids)==len(meta["fragments"])
                assert 0<sum(z["token_count"] for z in ids.values())==meta["e5_tokens"]<=2048
                chosen=[ids[pred["selected"]]] if pred["valid"] else [];visible=list(ids.values());shown[arm]=set(ids)
                if chosen:assert chosen[0]["text_sha256"]==pred["opened_sha256"] and pred["opened_bytes"]>0
                allstats=[metrics(gold[q],[z]) for z in visible]
                methods={"qwen":metrics(gold[q],chosen),"bm25":metrics(gold[q],[ids[meta["bm25_id"]]]),"all_fragments":metrics(gold[q],visible),
                         "oracle_one":max(allstats,key=lambda v:(v["full_support"],v["coverage"],v["density"]))}
                for m,val in methods.items():
                    for k,x in val.items():assert abs(x-outcomes[q]["arms"][arm][m][k])<1e-12
            assert (shown["related"]==shown["value"])==(name=="same")
        parts[name]=set(panel)
    assert len(unique)==63 and len(ts)==len(qs)==len(gold)==len(outcomes)==36
    parts["combined"]=qs
    for p,keys in parts.items():
        s=summary[p];assert s["n"]==len(keys)
        for arm in ("related","value"):
            for m in ("qwen","bm25","oracle_one","all_fragments"):
                count=sum(outcomes[q]["arms"][arm][m]["full_support"] for q in keys)
                assert count==s["metrics"][arm][m]["full_count"]
    print("verified",len(unique),"native decisions;",len(qs),"questions;",len(qs)*2,"reader arms and all oracle outcomes")
if __name__=="__main__":main()
