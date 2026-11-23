"""Score dev transfer and the size-charged policy after the 16 prediction files are sealed."""
from collections import defaultdict
import gzip
import json
from statistics import mean
from features import ROOT,load,save,sha
from transfer_write import DEV,original
from evaluate_write import GOLD,SourceSpan,RankedNodeRecord,take,ci
def main():
    se=load(ROOT/"transfer-forecast-seal.json")
    assert se["design"]==sha(ROOT/"transfer-plan.json") and all(sha(ROOT/n)==v for n,v in se["forecasts"].items())
    summary={};rowsall=[];storage_rows=[]
    for stage in ("dev","test"):
        truth={q:tuple(SourceSpan(**s) for s in spans) for q,spans in load(DEV/"gold-spans.json.gz" if stage=="dev" else GOLD).items()}
        old={r["q"]:r for r in load(ROOT/"outcomes.json.gz")} if stage=="test" else None
        old_storage={r["t"]:r for r in load(ROOT/"storage.json.gz")} if stage=="test" else None
        rows=[];by_t=[]
        for i in range(8):
            with gzip.open(original(stage,i)) as ab,gzip.open(ROOT/f"transfer-{stage}-{i}.jsonl.gz") as pred:
                for la,lb in zip(ab,pred,strict=True):
                    raw,r=json.loads(la),json.loads(lb);t=r["t"];assert raw["t"]==t
                    nodes=[]
                    for j,(ev,a,b,c,n) in enumerate(raw["blocks"]):
                        eid,ptr=raw["addresses"][ev]
                        nodes.append(RankedNodeRecord(node_id=str(j),score=0,token_count=c,source_spans=(SourceSpan(event_id=eid,json_pointer=ptr,char_start=a,char_end=b),)))
                    estimate={};costs={}
                    for arm,(keep,reads,store) in r["a"].items():
                        left=set(keep);assert len(left)==len(keep)
                        st=[nodes[j] for j in keep];assert store["tokens"]==sum(n.token_count for n in st)
                        alloc=3911 if arm=="paid/full" else 0
                        if arm.startswith(("bytes/","paid/")):assert store["bytes"]+alloc<=32768
                        else:assert store["tokens"]<=8192
                        costs[arm]={"bytes":store["bytes"],"charged_bytes":store["bytes"]+alloc,"tokens":store["tokens"]}
                        for q,ids in reads.items():
                            assert set(ids)<=left and len(set(ids))==len(ids)
                            rd=[nodes[j] for j in ids];tok=sum(n.token_count for n in rd);assert tok<=2048
                            w=take(st,truth[q],True);v=take(rd,truth[q],True)
                            assert v[0]<=w[0] and v[1]<=w[1]+1e-12
                            estimate.setdefault(q,{})[arm]=w+v+[tok]
                    if stage=="test":
                        for q,metrics in estimate.items():metrics.update(old[q]["a"])
                        for arm,v in old_storage[t]["c"].items():
                            costs[arm]={"bytes":v["binary_bytes"],"charged_bytes":v["binary_bytes"],"tokens":v["stored_tokens"]}
                    rows.extend(dict(q=q,t=t,a=a,split=stage) for q,a in estimate.items())
                    by_t.append({"t":t,"split":stage,"costs":costs})
        assert set(truth)=={r["q"] for r in rows} and len(rows)==len(truth)
        assert len(by_t)==(352 if stage=="dev" else 1207)
        groups={};comp={}
        for arm in rows[0]["a"]:
            groups[arm]={"write":sum(r["a"][arm][0] for r in rows),"read":sum(r["a"][arm][3] for r in rows),"read_tokens":mean(r["a"][arm][6] for r in rows),
                 **{f"stored_{k}":mean(v["costs"][arm][k] for v in by_t) for k in ("tokens","bytes","charged_bytes")}}
        terms=[(f"{mode}/full",f"{mode}/{right}") for mode in ("tokens","bytes") for right in ("output_head","positional","fifo")]
        terms.extend(("paid/full","bytes/"+other) for other in ("output_head","positional","fifo","full"))
        for a,b in terms:
            out={}
            for field,k in (("read",3),("write",0)):
                vals=[r["a"][a][k]-r["a"][b][k] for r in rows]
                out[field]={"wins":sum(v>0 for v in vals),"losses":sum(v<0 for v in vals),"ci":ci(rows,(a,b),k)}
            comp[a+" - "+b]=out
        summary[stage]={"q":len(rows),"t":len(by_t),"arms":groups,"contrasts":comp}
        rowsall.extend(rows);storage_rows.extend(by_t)
    save(ROOT/"transfer-outcomes.json.gz",rowsall);save(ROOT/"transfer-storage.json.gz",storage_rows);save(ROOT/"transfer-results.json",summary)
    for part,s in summary.items():print(part,[(a,b["write"],b["read"]) for a,b in s["arms"].items()])
if __name__=="__main__":main()
