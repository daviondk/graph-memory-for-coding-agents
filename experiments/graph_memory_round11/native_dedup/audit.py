"""Replay the R11 visible-context rule locally and score the captured upstream bytes."""
from collections import Counter,defaultdict
from functools import lru_cache
from random import Random
from statistics import median
from tokenizers import Tokenizer
from exercise import ROOT,READ,REF,sha,load,put,raw

info=load(READ/"receipt.json");tokpath=READ.parents[1]/"memory_session5/live/tokenizer.json"
assert sha(tokpath.read_bytes())==info["tokenizer_sha"]
tokenizer=Tokenizer.from_file(str(tokpath))
@lru_cache(maxsize=3000)
def nt(s):return len(tokenizer.encode(s,add_special_tokens=False).ids)
def packet(turn,s):return nt(f"[view {turn}]\n"+s)

def ci(items):
    if not sum(x["raw"] for x in items):return None
    rng=Random(11226);samples=[]
    for _ in range(5000):
        a=rng.choices(items,k=len(items));n=sum(i["raw"] for i in a)
        if n:samples.append(100*sum(i["strict"]-i["union"] for i in a)/n)
    samples.sort()
    return [samples[int(q*(len(samples)-1))] for q in (.025,.975)]

def main():
    lock=load(ROOT/"protocol-lock.json");assert all(sha((ROOT/n).read_bytes())==h for n,h in lock["files"].items())
    assert sha((READ/"views.gz").read_bytes())==lock["views"]
    cache=load(ROOT/"native-receipts.gz");data=load(READ/"views.gz")
    base=defaultdict(dict)
    for x in load(READ/"rows.gz"):
        if x["mode"]=="visible" and x["window"]==8:base[x["task"]][x["method"]]=x["tokens"]
    rows=[];tasks=[]
    for task,x in sorted(data.items()):
        seen=[];total=Counter(dict.fromkeys(["strict","native","raw_stdout","expand_if_requested","messages","ref","backup","invalid","strict_ref","stderr_tokens"],0))
        for v,r in zip(x["views"],cache[task]["records"],strict=True):
            turn,path=v["turn"],v["path"];actual=raw(v);res=r["compression"];out=res["out"];ref=REF.fullmatch(out)
            assert (turn,path,sha(actual.encode()))==(r["turn"],r["path"],r["sha"])
            called=r["expansion"];err=res["err"];reason="literal";anchor=None
            verified=res["code"]==0 and out==actual
            if ref:
                verified=bool(res["code"]==0 and called and called["code"]==0 and called["out"]==actual)
                candidates=[]
                for b in seen:
                    if b["path"]!=path or turn-b["turn"]>8 or not b["hash"].startswith(ref[1]):continue
                    linebytes=b["raw"].split("\n")[:-1]
                    view=b["raw"] if ref[2] is None else "".join(t+"\n" for t in linebytes[int(ref[2])-1:int(ref[3])])
                    if view==actual:candidates.append(b["turn"])
                anchor=max(candidates,default=None)
                reason="ref_visible" if anchor is not None else "ref_needs_db"
            if not verified:reason="fallback_unverified"
            strict=out if verified and (not ref or anchor is not None) else actual
            native=out if verified else actual
            if strict==actual:seen.append(dict(path=path,turn=turn,hash=sha(actual.encode()),raw=actual))
            delta=dict(strict=packet(turn,strict),native=packet(turn,native),raw_stdout=packet(turn,out),
                      expand_if_requested=(nt(called["out"]) if ref and verified else 0),messages=1,ref=int(bool(ref)),strict_ref=int(reason=="ref_visible"),
                      backup=int(strict!=out),invalid=int(not verified),stderr_tokens=nt(err))
            total.update(delta)
            rows.append(dict(task=task,panel=x["panel"],turn=turn,kind="range" if ref and ref[2] else ("exact" if ref else "literal"),
                             reason=reason,anchor=anchor,**delta))
        tasks.append(dict(task=task,panel=x["panel"],db_bytes=cache[task]["db_bytes"],**total,**base[task]))
    put(ROOT/"scored.gz",rows);put(ROOT/"by-task.json",tasks)
    counts={}
    for panel in ["all",*sorted({t["panel"] for t in tasks})]:
        subset=tasks if panel=="all" else [t for t in tasks if t["panel"]==panel]
        c=Counter()
        for t in subset:c.update({k:v for k,v in t.items() if type(v)==int})
        fields=["raw","whole","single","union","strict","native","raw_stdout","expand_if_requested","messages","ref","strict_ref","backup","invalid","stderr_tokens","db_bytes"]
        ids={t["task"] for t in subset}
        counts[panel]=dict(n=len(subset),totals={k:c[k] for k in fields},types=dict(Counter(r["kind"] for r in rows if r["task"] in ids)),
             delta_strict_union=c["strict"]-c["union"],points=100*(c["strict"]-c["union"])/c["raw"] if c["raw"] else None,ci95=ci(subset),
             union_wins=sum(t["strict"]>t["union"] for t in subset),union_losses=sum(t["strict"]<t["union"] for t in subset),
             db_median_nonempty=median([t["db_bytes"] for t in subset if t["messages"]]) if c["messages"] else None)
    put(ROOT/"results.json",counts)
    smoke=load(ROOT/"control.json");verified=[]
    for i,(inp,r) in enumerate(zip(smoke["source"],smoke["records"])):
        recovered=r["expansion"]["out"] if r["expansion"] else r["compression"]["out"]
        assert recovered==inp and r["compression"]["code"]==0
        verified.append(i)
    put(ROOT/"verification.json",dict(smoke=verified,files={n:sha((ROOT/n).read_bytes()) for n in ["audit.py","control.json","scored.gz","native-receipts.gz","results.json","by-task.json","protocol-lock.json"]}))
    print(counts)
if __name__=="__main__":main()
