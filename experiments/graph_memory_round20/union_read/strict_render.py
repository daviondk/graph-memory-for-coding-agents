"""Apply an identical literal text cap to every prepared layout."""
from collections import defaultdict,Counter
from concurrent.futures import ProcessPoolExecutor
from statistics import mean
import sys
import time
from pack import ROOT,CAP,TOKENIZER,CACHE,OFF,Tokenizer,load,put,sha,includes


def cut(pieces,fields,tok):
    def size(ss):return len(tok.encode(ss,add_special_tokens=False).ids)
    def joined(seq):return "\n".join(fields[e][a:b] for e,p,a,b,c in seq)
    result=[[e,p,a,b,size(fields[e][a:b])] for e,p,a,b,_ in pieces]
    before=sum(x[4] for x in result)
    assert before==size(joined(result))
    if all(x[4]>0 for x in result) and before<=CAP:return result,before
    result=[x for x in result if x[4]>0]
    while result and size(joined(result))>CAP:
        e,p,a,b,c=result.pop();text=fields[e][a:b]
        offsets=tok.encode(text,add_special_tokens=False).offsets
        for i in sorted({left for left,right in offsets if 0<left<len(text)},reverse=True):
            nc=size(text[:i])
            if nc==0:continue
            candidate=[*result,[e,p,a,a+i,nc]]
            if size(joined(candidate))<=CAP:
                result=candidate
                break
    assert sum(x[4] for x in result)==size(joined(result))<=CAP
    return result,before


def shard(args):
    model,i=args;tok=Tokenizer.from_file(str(TOKENIZER));tok.no_padding();tok.no_truncation()
    by=defaultdict(list)
    forecasts=load(ROOT/f"{model}-pred-{i}.json.gz")
    duplicate={r["q"]:r for r in load(ROOT/f"{model}-dup-{i}.json.gz")}
    for row in forecasts:by[row["t"]].append(row)
    out=[]
    for t,rows in by.items():
        fields=load(CACHE/f"{i}-{t}.json.gz")["fields"]
        for r in rows:
            before={**r["arms"],**duplicate[r["q"]]["arms"]}
            after={};info={}
            for arm,parts in before.items():
                fixed,raw_cost=cut(parts,fields,tok)
                after[arm]=fixed
                info[arm]=dict(old_cost=raw_cost,new_cost=sum(x[4] for x in fixed),
                    cut_chars=sum(b-a for e,p,a,b,c in parts)-sum(b-a for e,p,a,b,c in fixed))
            out.append(dict(q=r["q"],t=t,a=after,info=info))
    p=ROOT/f"{model}-strict-{i}.json.gz";put(p,out)
    return dict(file=p.name,sha=sha(p),n=len(out))


def forecasts(model):
    cfg=load(ROOT/"strict-plan.json")
    assert cfg["code"]==sha(ROOT/"strict_render.py") and cfg["protocol"]==sha(ROOT/"STRICT_RENDER_RU.md")
    local=[ROOT/f"{model}-forecast-seal.json",ROOT/f"{model}-duplicate-seal.json"]
    for p in local:
        assert all(sha(ROOT/x["file"])==x["sha"] for x in load(p)["shards"])
    st=time.perf_counter()
    with ProcessPoolExecutor(max_workers=3) as pool:
        shards=list(pool.map(shard,[(model,i) for i in range(8)]))
    assert sum(v["n"] for v in shards)==2000
    put(ROOT/f"{model}-strict-seal.json",dict(shards=shards,inputs={p.name:sha(p) for p in local},
        plan=sha(ROOT/"strict-plan.json"),wall=time.perf_counter()-st))


def evaluate(model):
    from score import calc,paired,signature
    seal=load(ROOT/f"{model}-strict-seal.json");assert seal["plan"]==sha(ROOT/"strict-plan.json")
    assert all(sha(ROOT/x["file"])==x["sha"] for x in seal["shards"])
    prior={r["q"]:r for r in load(ROOT/f"{model}-outcomes.json.gz")};gold=load(OFF/"gold-spans.json.gz")
    rows=[];failed=Counter();changed=Counter();fs_changes=defaultdict(list)
    for shard_ in seal["shards"]:
        for r in load(ROOT/shard_["file"]):
            q=r["q"];m={a:signature(parts) for a,parts in r["a"].items()}
            for a,b in [("skip","U"),("U","W"),("W","F"),("skip","W0"),("W0","F0"),("skip","F")]:
                failed[a+"-in-"+b]+=int(not includes(m[a],m[b]))
            metric={}
            for a,parts in r["a"].items():
                v=calc(parts,gold[q]);metric[a]=v
                assert v["tokens"]==r["info"][a]["new_cost"]<=CAP
                if r["info"][a]["cut_chars"]:changed[a]+=1
                before=prior[q]["a"][a]
                if v["full_support"]!=before["full_support"]:fs_changes[a].append(q)
            rows.append(dict(q=q,t=r["t"],a=metric,info=r["info"]))
    assert len(rows)==len(gold)==2000 and len({r["q"] for r in rows})==2000
    arms=rows[0]["a"]
    stats={a:dict(fs=int(sum(r["a"][a]["full_support"] for r in rows)),max_tokens=max(r["a"][a]["tokens"] for r in rows),
        tokens=mean(r["a"][a]["tokens"] for r in rows),coverage=mean(r["a"][a]["coverage"] for r in rows),
        density=mean(r["a"][a]["density"] for r in rows),affected=changed[a],fs_changed=fs_changes[a]) for a in arms}
    ctr={a+"-"+b:paired(rows,a,b) for a,b in [("F","skip"),("F","F0"),("W","skip")]}
    put(ROOT/f"{model}-strict-outcomes.json.gz",rows)
    put(ROOT/f"{model}-strict-results.json",dict(stats=stats,paired=ctr,inclusion_violations=failed,
        seal=sha(ROOT/f"{model}-strict-seal.json"),gold=sha(OFF/"gold-spans.json.gz")))
    print(model,{a:(x["fs"],x["max_tokens"],x["affected"]) for a,x in stats.items()},dict(failed))


if __name__=="__main__":
    if sys.argv[1]=="plan":
        put(ROOT/"strict-plan.json",dict(code=sha(ROOT/"strict_render.py"),protocol=sha(ROOT/"STRICT_RENDER_RU.md"),
            main=sha(ROOT/"design-lock.json"),dense_observed=sha(ROOT/"dense-results.json")))
    else:{"predict":forecasts,"score":evaluate}[sys.argv[1]](sys.argv[2])
