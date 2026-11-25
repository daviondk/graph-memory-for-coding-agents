"""Keep every original repeated quotation and fill only genuine remaining space."""
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor
import sys
import time
from pack import ROOT,CACHE,CAP,TOKENIZER,Tokenizer,Episode,rankpath,content_tokens,load,put,sha,merge,gaps,includes


def keep_duplicates(ep,row):
    by={n["node_id"]:n for n in row["rr"]}
    rank=list(by);origin=row["arms"]["skip"];parts=[];seen=defaultdict(list)
    def render(records):
        s="\n".join(ep.fields[e][a:b] for e,p,a,b,c in records)
        return len(ep.tok.encode(s,add_special_tokens=False).ids)
    for nid in origin:
        k,a,b=ep.spans[nid];parts.append([*k,a,b,ep.cost(k,a,b)]);seen[k].append((a,b))
    seen={k:merge(v) for k,v in seen.items()}
    spent=render(parts);assert spent==sum(x[4] for x in parts)
    if spent>CAP or any(x[4]<=0 for x in parts):
        native=[[*ep.spans[nid][0],*ep.spans[nid][1:],by[nid]["token_count"]] for nid in origin]
        return dict(W0=native,F0=native),True
    def append(k,new):
        nonlocal spent
        if not new:return False
        vals=[[ *k,a,b,ep.cost(k,a,b)] for a,b in new]
        if any(v[4]<=0 for v in vals) or spent+sum(v[4] for v in vals)>CAP:return False
        parts.extend(vals);seen[k]=merge(seen.get(k,[])+new);spent+=sum(v[4] for v in vals)
        return True
    for nid in rank:
        k,a,b=ep.spans[nid];append(k,list(gaps(a,b,seen.get(k,[]))))
    w=list(parts);assert render(w)==spent<=CAP
    query=set(content_tokens(ep.q[row["q"]]))
    for nid in rank:
        if spent==CAP:break
        k,a,b=ep.spans[nid];width=min(64,CAP-spent);candidates=[]
        for start,end in gaps(a,b,seen.get(k,[])):
            for i,j in ep.windows(k,start,end,width):
                overlap=len(query&set(content_tokens(ep.fields[k[0]][i:j])))
                candidates.append((-overlap,i,j))
        for _,i,j in sorted(set(candidates)):
            if append(k,[(i,j)]):break
    assert render(parts)==spent<=CAP
    return dict(W0=w,F0=parts),False


def shard(args):
    model,i=args;src=rankpath(model,i);rf=load(ROOT/(model+"-plan.json"))
    assert sha(src)==rf["ranks"][src.name]
    grouped=defaultdict(list)
    for row in load(src):grouped[row["t"]].append(row)
    records=[];tok=Tokenizer.from_file(str(TOKENIZER));tok.no_truncation();tok.no_padding()
    start=time.process_time()
    for t,rows in sorted(grouped.items()):
        ep=Episode(load(CACHE/f"{i}-{t}.json.gz"),tok)
        for row in rows:
            arms,infeasible=keep_duplicates(ep,row)
            records.append(dict(t=t,q=row["q"],arms=arms,infeasible=infeasible))
    dest=ROOT/f"{model}-dup-{i}.json.gz";put(dest,records)
    return dict(file=dest.name,sha=sha(dest),n=len(records),cpu=time.process_time()-start)


def main():
    model=sys.argv[2];plan=ROOT/f"{model}-duplicate-plan.json"
    if sys.argv[1]=="plan":
        put(plan,dict(protocol=sha(ROOT/"OVERLAP_CONTROL_RU.md"),code=sha(ROOT/"overlap_control.py"),
            main=sha(ROOT/(model+"-plan.json")),pack=sha(ROOT/"pack.py")))
        return
    cfg=load(plan);assert cfg["code"]==sha(ROOT/"overlap_control.py") and cfg["pack"]==sha(ROOT/"pack.py")
    assert cfg["main"]==sha(ROOT/(model+"-plan.json"))
    st=time.perf_counter()
    with ProcessPoolExecutor(max_workers=3) as pool:
        sums=list(pool.map(shard,[(model,i) for i in range(8)]))
    assert sum(x["n"] for x in sums)==2000
    put(ROOT/f"{model}-duplicate-seal.json",dict(plan=sha(plan),shards=sums,wall=time.perf_counter()-st,
        cpu=sum(v["cpu"] for v in sums)))


if __name__=="__main__":main()
