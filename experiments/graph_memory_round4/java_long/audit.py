"""Verify all logged completed generations and scores without parquet files, model weights or NumPy."""
from collections import Counter
import json
import math
import re

from infer import D, read, save, sha, from_str

def lcs(s, t):
    # Independent bit-vector LCS, checking the two-row implementation in score.py.
    alphabet={}
    for i,char in enumerate(t):
        alphabet[char]=alphabet.get(char,0)|(1<<i)
    state=0
    for char in s:
        tmp=state|alphabet.get(char,0)
        state=tmp & ~(tmp-((state<<1)|1))
    return state.bit_count()

def check():
    immutable=read("long_input_lock.json")
    for n, h in immutable.items(): assert sha((D/n).read_bytes())==h
    decisions=read("long_decisions.json")
    assignments=read("long_assignment.json")
    assert {k+".json.gz" for m in assignments.values() for k in m.values()}==set(decisions)
    receipts={}
    for name,digest in decisions.items():
        file=D/"long_calls"/name
        assert sha(file.read_bytes())==digest
        rec=read(file)
        k=name[:-8]
        assert k==sha(from_str(rec["request"]))
        receipts[k]=rec
    packets={r["id"]:r for r in read("long_packets.json.gz")}
    items=read("long_items.json.gz")
    assert {r["id"] for r in items}==set(packets)==set(assignments) and len(items)==96
    assert set(Counter(r["panel"] for r in items).values())=={24}
    counts=Counter()
    derived=read("long_extended.json")
    for row in items:
        ident=row["id"];p=packets[ident];gold=row["gold"]
        for a,v in row["methods"].items():
            rec=receipts[assignments[ident][a]]
            req=rec["request"];reply=rec["reply"]
            assert req["seed"]==int(sha("r4java|"+ident)[:7],16) and req["temperature"]==0 and req["model"]=="qwen38-27b-ud-q4km"
            expected="External Java fragment:\n"+p["snippets"][a][0]+"\n\nLast lines of current file:\n"+p["ctx"]+"\n\nNext source line:"
            assert expected==req["messages"][-1]["content"]
            text=(reply["choices"][0]["message"].get("content") or "")
            lines=[s.strip() for s in text.splitlines() if s.strip()]
            pred=next((x for x in lines if not x.startswith(chr(96)*3)),"")
            ids,tokens=({*re.findall(r"[A-Za-z_$][\w$]*",s)} for s in (pred,gold))
            f1=2*len(ids&tokens)/(len(ids)+len(tokens)) if ids or tokens else 1.0
            assert v["em"]==int(pred==gold) and v["generated"]==pred
            assert math.isclose(v["id_f1"],f1)
            es=round(200*lcs(pred,gold)/(len(pred)+len(gold))) if pred or gold else 100
            assert v["es"]==es and v["prompt_tokens"]==reply["usage"]["prompt_tokens"]
            assert v["retrieved"]==int(a!="empty" and p["ranks"][a]==p["ranks"]["oracle"])
            counts[a]+=v["em"]
    for a,n in counts.items(): assert n==derived["main"][a]["em"]
    return dict(checked_items=len(items),checked_requests=len(receipts),
                checked_pairs=sum(map(len,assignments.values())),repo_count=len({r["repo"] for r in items}),audited_em=counts)
if __name__=="__main__":
    result=check();save("long_audit.json",result);print(json.dumps(result))
