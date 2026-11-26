"""Static, gold-blind code retrieval replay of the official pre-edit repository snapshots."""
from collections import Counter,defaultdict
from math import log
from pathlib import Path
import json,re
from sources import HERE,S,load,save,archive,hashfile,idhash
from edges import changed_names,ident,parse,connected,words,WORD,KEYS

ARMS=["bm25","repomap","lexical","published_rrf","names","scope","text_vote","graph_vote","reverse_vote"]
def visit_snapshot(t,m,queries,top,out):
    paths={};defs=defaultdict(set);spans=defaultdict(list);anchor_paths={q["anchor_file"] for q in queries}
    commits={q["base_commit"] for q in queries};repos={q["repo"] for q in queries}
    assert len(commits)==len(repos)==1
    repo=next(iter(repos));commit=next(iter(commits))
    for line in t.extractfile(m):
        r=json.loads(line);assert r["base_commit"]==commit and r["repo"]==repo
        path=r["path"]
        if r["kind"]=="file":paths[path]=paths.get(path,"")+"\n"+r["text"]
        else:
            symbol=ident(r["symbol"] or "")
            if len(symbol)>=3 and symbol not in KEYS:
                defs[path].add(symbol)
                if path in anchor_paths:spans[path].append((r["start_line"],r["end_line"],symbol))
    assert set(defs)<=set(paths)
    args={};needed=set()
    for q in queries:
        a=q["anchor_file"];mentioned,declared,lines=changed_names(q["anchor_diff"])
        for i in lines:
            contenders=[v for v in spans[a] if v[0]<=i<=v[1]]
            if contenders:
                size=min(v[1]-v[0] for v in contenders);declared.update(v[2] for v in contenders if v[1]-v[0]==size)
        # Ordinary changed references, without names declared in the anchor itself.
        used=mentioned-defs[a]-declared;args[q["id"]]=(used,declared)
        needed|=used|declared
    scopes={p:parse(p,text,repo) for p,text in paths.items()}
    # Compute exact identifier incidence only; no query-specific top files or gold are used in this pass.
    # A single regex built from the union is cheaper than tokenizing every source function.
    rx=re.compile(r"(?<![A-Za-z0-9_$])(?:"+"|".join(re.escape(x) for x in sorted(needed))+r")(?![A-Za-z0-9_$])") if needed else None
    appearances={p:set(rx.findall(text)) if rx else set() for p,text in paths.items()}
    freq=Counter(t for vals in appearances.values() for t in vals);N=len(paths)
    for q in queries:
        k=q["id"];anchor=q["anchor_file"];used,declared=args[k]
        published={mode:top[mode][k] for mode in ("bm25","repomap","lexical")}
        assert all(len(v)==len(set(v)) and set(v)<=set(paths) for v in published.values())
        base={mode:[p for p in v if p!=anchor] for mode,v in published.items()}
        pos={mode:{v:i for i,v in enumerate(rank,1)} for mode,rank in base.items()}
        pool=sorted(set(paths)-{anchor})
        def prior(p):return(pos["bm25"].get(p,10**6),pos["repomap"].get(p,10**6),p)
        gains={"names":{},"scope":{},"reverse":{}}
        support={};flags=Counter()
        for p in pool:
            forward=used&defs[p];back=declared&(appearances[p]-defs[p])
            if not (forward or back):continue
            weight=lambda ns:sum(1+log((N+1)/(1+freq[n])) for n in sorted(ns))
            ff,bb=weight(forward),weight(back)
            fs=connected(scopes[anchor],scopes[p],repo) if anchor in scopes else ""
            bs=connected(scopes[p],scopes[anchor],repo) if anchor in scopes else ""
            gains["names"][p]=ff+bb;gains["scope"][p]=ff+bb+(ff if fs else 0)+(bb if bs else 0)
            gains["reverse"][p]=ff+bb+(bb if fs else 0)+(ff if bs else 0)
            if ff and fs:flags["forward:"+fs]+=1
            if bb and bs:flags["backward:"+bs]+=1
            support[p]=[len(forward),len(back),fs,bs,*[round(gains[u][p],6) for u in ("names","scope","reverse")]]
        lexical_rank={}
        for g,ranks in gains.items():
            order=sorted(ranks,key=lambda p:(-ranks[p],prior(p)))
            lexical_rank[g]={v:i for i,v in enumerate(order,1)}
        def vote(m,p):return 1/(20+m[p]) if p in m else 0
        def fused(p,extra):
            score=vote(pos["bm25"],p)+vote(pos["repomap"],p)
            if extra:score+=vote(lexical_rank["names"],p)+vote(lexical_rank[extra],p)
            return score
        final={}
        # All submitted variants return 20 distinct paths; remove the given anchor uniformly and break tail ties deterministically.
        for g in base:final[g]=(base[g]+[p for p in pool if p not in pos[g]])[:20]
        for g,extra in (("published_rrf",None),("text_vote","names"),("graph_vote","scope"),("reverse_vote","reverse")):
            final[g]=sorted(pool,key=lambda p:(-fused(p,extra),prior(p)))[:20]
        for g in ("names","scope"):final[g]=sorted(pool,key=lambda p:(-gains[g].get(p,0),prior(p)))[:20]
        assert set(final)==set(ARMS) and all(len(v)==20 and len(set(v))==20 and anchor not in v for v in final.values())
        selected={p for a in final.values() for p in a}
        out[k]={"repo":repo,"commit":commit,"anchor":anchor,"anchor_exists":anchor in paths,"pool_size":len(pool),
                "mentioned_names":len(used),"anchor_symbols":len(declared),"symbol_candidate_files":len(support),"edge_events":flags,
                "predictions":final,"case_features":{p:support[p] for p in selected if p in support},
                "published_raw":published}
def main():
    src=load(HERE/"source.json");assert hashfile(HERE/"PROTOCOL_RU.md")==src["protocol"]
    queries=load(S/"actor-input.json.gz");top=load(S/"author-top20.json.gz")
    assert hashfile(S/"actor-input.json.gz")==src["query"] and hashfile(S/"author-top20.json.gz")==src["published_top"]
    groups=defaultdict(list);out={}
    for q in queries.values():groups[(q["repo"].replace("/","__"),q["base_commit"])].append(q)
    with archive() as t:
        for m in t:
            if not m.name.startswith("./corpus/") or not m.name.endswith(".chunks.jsonl"):continue
            key=(m.name.split("/")[-2],m.name.split("/")[-1].split(".")[0])
            if key in groups:visit_snapshot(t,m,groups[key],top,out)
    assert set(out)==set(queries)
    save(HERE/"forecasts.json.gz",out)
    files=["PROTOCOL_RU.md","source.json","download.py","sources.py","edges.py","predict.py","forecasts.json.gz"]
    save(HERE/"prediction-seal.json",dict(arms=ARMS,n=len(out),snapshots=len(groups),files={f:hashfile(HERE/f) for f in files}))
    print("SEALED",len(out),len(groups),hashfile(HERE/"prediction-seal.json"))
if __name__=="__main__":main()

