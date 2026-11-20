"""Secondary locked-order, equal-token check with up to three delivered complete snippets."""
from functools import lru_cache
from collections import defaultdict
import gzip, json
import pyarrow.parquet as pq
from features import TOKENIZER
from io_utils import D,save,read,sha,load_gz,dump,np
from score import contrast
@lru_cache(3000)
def nt(s):return len(TOKENIZER.encode(s,add_special_tokens=False).ids)
def pack(rank,cost,b):
    items=[];spent=0
    for i in rank:
        c=cost[i]+int(bool(items))
        if spent+c<=b:
            spent+=c;items.append(i)
            if len(items)==3:break
    return items,spent
def main():
    total={};budgets=(256,512,1024);transfer={(r[0],r[1]):(r[2],r[-1]) for r in load_gz(D/"transfer_predictions.jsonl.gz")}
    assert sha(D/"transfer_predictions.jsonl.gz")==read("transfer_predictions_lock.json")["sha"]["transfer_predictions.jsonl.gz"]
    with gzip.open(D/"token_packets.jsonl.gz","wt",encoding="utf8") as f:
        for version in ("original","transfer"):
            paths=sorted((D/("inputs" if version=="original" else "transfer_inputs")).glob("*test*.parquet" if version=="original" else "*.parquet"))
            arms=["flat","owner","transition","placebo"]+([] if version=="original" else ["mix","gate"])
            for p in paths:
                if version=="original":
                    pf=D/(p.stem+".pred.jsonl.gz");assert sha(pf)==read("predictions_lock.json")["sha256"][pf.name]
                    order={r[0]:(r[1],r[-1]) for r in load_gz(pf)}
                else:order={i:v for (fn,i),v in transfer.items() if fn==p.name}
                i=-1
                for batch in pq.ParquetFile(p).iter_batches(batch_size=40,columns=["context"]):
                    for obj in batch.to_pylist():
                        i+=1
                        if i not in order:continue
                        docs=obj["context"];cost=[nt(x if isinstance(x,str) else x["snippet"]) for x in docs];repo,ranks=order[i]
                        packs={b:{a:pack(ranks[a],cost,b) for a in arms} for b in budgets}
                        assert all(v[1]<=b and len(v[0])<=3 for b,aa in packs.items() for v in aa.values())
                        dump(f,[version,p.name,i,repo,cost,packs])
    save("token_lock.json",{"protocol":sha(D/"TOKEN_PROTOCOL.md"),"implementation":sha(D/"pack_scores.py"),"predictions":sha(D/"token_packets.jsonl.gz")})
    gold={p.name:pq.read_table(p,columns=["gold_snippet_index"]).column(0).to_pylist() for p in [*sorted((D/"inputs").glob("*test*.parquet")),*sorted((D/"transfer_inputs").glob("*.parquet"))]}
    sub=defaultdict(list);ceiling=defaultdict(int)
    for version,f,i,repo,cs,packs in load_gz(D/"token_packets.jsonl.gz"):
        target=gold[f][i]
        for b,methods in packs.items():
            k=(version,int(b));ceiling[k]+=0<=target<len(cs) and cs[target]<=int(b)
            sub[k].append([f,i,repo,None,{a:1 if target in sel else 999 for a,(sel,cost) in methods.items()},{a:c for a,(sel,c) in methods.items()}])
    for (version,b),rs in sub.items():
        arms=list(rs[0][4]);entry=dict(n=len(rs),oracle=ceiling[version,b],hits={a:sum(r[4][a]==1 for r in rs) for a in arms},spent={a:sum(r[5][a] for r in rs)/len(rs) for a in arms},
          paired=contrast(rs,"transition","owner"))
        if "gate" in arms:entry["gate_vs_mix"]=contrast(rs,"gate","mix")
        total[version+"_"+str(b)]=entry
    save("token_results.json",total)
if __name__=="__main__":main()
