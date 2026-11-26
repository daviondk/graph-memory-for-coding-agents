"""Rank candidate test paths without reference labels or target-PR data."""
from collections import Counter,defaultdict
from functools import lru_cache
import math
from pathlib import PurePosixPath
import re
from source import HERE,OLD_CACHE,R55,read,save,digest
CODE=set("bash c cc cpp cs cxx fish go h hpp java js jsx kt kts m mm php proto py pyi rb rs scala sh swift ts tsx zsh".split())
DIRS=set("__tests__ test tests testing testdata testsuite testsuites".split())
SUFFIXES=("_test.go","_test.py","_test.rs","_test.cc","_test.cpp",".spec.js",".spec.jsx",".spec.ts",".spec.tsx",
          ".test.js",".test.jsx",".test.ts",".test.tsx","test.java","tests.java")
STOP=DIRS|set("src lib main app java org com package packages resources spec specs unit integration internal".split())
@lru_cache(maxsize=100000)
def is_test(path):
    p=PurePosixPath(path.lower().replace("\\","/"))
    return p.suffix[1:] in CODE and (bool(set(p.parts)&DIRS) or p.name.startswith("test_") or p.name.endswith(SUFFIXES))

def tokens(text):
    return re.findall("[a-z0-9]+",re.sub(r"([a-z0-9])([A-Z])",r"\1_\2",text).lower())

@lru_cache(maxsize=100000)
def features(path):
    p=PurePosixPath(path);name=[x for x in tokens(p.stem) if x not in STOP]
    return "".join(name),frozenset(name),frozenset(tokens(str(p.parent)))-STOP

def sim(a,b):
    return len(a&b)/len(a|b) if a or b else 0
def name_score(path,anchors):
    base,tok,parent=features(path)
    return max((int(bool(base) and base==s),sim(tok,t),sim(parent,parents)) for s,t,parents in anchors)

def community(rows,catalog):
    src=read(R55/"community-seal.json")["sources"]
    out=defaultdict(dict)
    for arm in ("codenib_dense","codenib_hybrid","oko1","oko2","oko3"):
        url,hash_=src[arm]
        p=OLD_CACHE/url.rsplit("/",1)[-1]
        assert digest(p)==hash_
        if p.suffix==".gz":
            raw=read(p)
        else:
            import json
            raw=[json.loads(line) for line in p.read_bytes().splitlines()]
        for r in raw:
            q=r["sample_id"]
            if q in rows:
                base=rows[q]["base"]
                assert base==r["base_commit"] and rows[q]["repo"]==r["repo"]
                out[q][arm]=[p for p in dict.fromkeys(r["ranked_files"]) if p in catalog[base]][:28]
    assert set(out)==set(rows) and all(len(m)==5 for m in out.values())
    return out

def past_groups(stream,anchors,mode):
    groups=[];seen=Counter()
    for age,(sha,m,paths) in enumerate(stream[:32] if mode=="g32" else stream):
        if not paths:continue
        touched=anchors.intersection(paths)
        if not touched:continue
        if mode!="local8" or any(seen[a]<8 for a in touched):
            groups.append((age,sha,m,paths))
        seen.update(touched)
    return groups

def temporal(groups,anchors,available,confirms):
    votes=Counter();count=Counter();joint=Counter();age_by={}
    for age,sha,m,paths in groups:
        corroborated=bool((confirms-anchors).intersection(paths))
        for p in paths:
            if p in anchors or p not in available:continue
            votes[p]+=1/(m-1);count[p]+=1;joint[p]+=int(corroborated);age_by.setdefault(p,age)
    full=sorted(votes,key=lambda p:(-votes[p],-joint[p],age_by[p],p))
    return full,{p:(count[p],joint[p]) for p in full}

def run_case(row,pool,published,other,stream):
    anchors=set(row["anchors"]);test_pool={p for p in pool if is_test(p)}
    known=[features(a) for a in anchors]
    scores={p:name_score(p,known) for p in test_pool}
    name=sorted(test_pool,key=lambda p:(tuple(-val for val in scores[p]),p))
    groups={m:past_groups(stream,anchors,m) for m in ("local8","g32","g64")}
    freq=Counter()
    for _,m,paths in stream:
        for p in paths:
            if p in test_pool and p not in anchors:freq[p]+=1/(m-1)
    freq_rank=sorted(freq,key=lambda p:(-freq[p],p))
    evidence={};out={}
    for budget in ("original","new"):
        blocked=anchors if budget=="new" else set()
        def filtered(seq):
            return [p for p in seq if p not in blocked]
        fallback=filtered(sorted(pool))
        def fill(*lists,size):
            chosen=[];seen=set()
            for seq in lists:
                for p in seq:
                    if p not in seen and p not in blocked:
                        chosen.append(p);seen.add(p)
                        if len(chosen)>=size:return chosen
            return chosen
        bp={m:filtered(paths) for m,paths in published.items()}
        role={m:fill((p for p in seq if p in test_pool),name,seq,fallback,size=20) for m,seq in bp.items()}
        out[budget]={m:fill(seq,fallback,size=5) for m,seq in bp.items()}
        out[budget].update({m:fill(paths,fallback,size=5) for m,paths in other.items()})
        out[budget]["name"]=fill(name,bp["embed4"],fallback,size=5)
        for m in role:out[budget]["role_"+m]=role[m][:5]
        info={}
        for m in ("embed4","lexical","repomap"):
            for kind,order in (("raw",fill(bp[m],fallback,size=20)),("role",role[m])):
                allowed=(test_pool if kind=="role" else pool)-anchors
                ext=allowed-set(order)
                primary=[]
                for time in ("local8","g32","g64"):
                    indexed,obs=temporal(groups[time],anchors,ext,set(order[:4]))
                    admit=[p for p in indexed if obs[p][0]>=2 or obs[p][1]]
                    stem=f"{kind}_{m}_{time}"
                    out[budget][stem]=order[:4]+(admit[:1] or order[4:5])
                    if time=="local8" and kind=="role" and m=="embed4":
                        primary=admit
                        out[budget]["role_embed4_once"]=order[:4]+(indexed[:1] or order[4:5])
                        info.update(primary_support=len(admit),any_support=len(indexed),qualified=admit,
                                    all20=order,changed=bool(admit))
                if kind=="role" and m=="embed4":
                    pop=[p for p in freq_rank if p in ext]
                    out[budget]["role_embed4_pop"]=order[:4]+(pop[:1] if primary and pop else order[4:5])
        def fuse(extra):
            seqs=[[p for p in bp[m] if p in test_pool] for m in ("embed4","lexical","repomap")]+[filtered(name),extra]
            rank=Counter()
            for seq in seqs:
                for i,p in enumerate(seq[:20],1):rank[p]+=1/(10+i)
            return fill(sorted(rank,key=lambda p:(-rank[p],p)),bp["embed4"],fallback,size=5)
        # For this separate fixed-rank fusion the base top four must not count as corroborating paths.
        for m in ("local8","g32","g64"):
            idx,_=temporal(groups[m],anchors,test_pool,set())
            out[budget]["fusion_"+m]=fuse(idx)
        out[budget]["fusion_embed8"]=fuse([p for p in bp["embed8"] if p in test_pool])
        out[budget]["fusion_pop"]=fuse(freq_rank)
        out[budget]["fusion"]=fuse([])
        evidence[budget]=info
        assert all(len(v)==len(set(v))==5 and set(v)<=pool and not set(v)&blocked for v in out[budget].values())
    return dict(base=row["base"],repo=row["repo"],anchor_count=len(anchors),seen_anchor=len(anchors&pool),catalog=len(pool),
                is_test_anchor=len(anchors&test_pool),test_paths=len(test_pool),history=len(stream),
                consulted={m:len(v) for m,v in groups.items()},evidence=evidence,ranked=out)

def main():
    seal=read(HERE/"input-seal.json")
    assert all(digest(HERE/n)==h for n,h in seal["sources"].items())
    rows=read(HERE/"roster.json");catalog={k:set(v) for k,v in read(HERE/"catalog.json.gz").items()}
    controls=community(rows,catalog);published=read(HERE/"publisher.json.gz");past=read(HERE/"histories.json.gz")
    save(HERE/"community.json.gz",controls)
    out={}
    for q,r in rows.items():
        if r["eligible"]:
            stream=past[r["base"]]
            assert stream["repo"]==r["repo"]
            out[q]=run_case(r,catalog[r["base"]],published[q],controls[q],stream["history"])
    save(HERE/"predictions.json.gz",out)
    names=("source.py","history.py","rank.py","PROTOCOL_RU.md","FUSION_RU.md","input-seal.json",
           "roster.json","catalog.json.gz","histories.json.gz","publisher.json.gz","community.json.gz","predictions.json.gz")
    save(HERE/"prediction-seal.json",{n:digest(HERE/n) for n in names})
    print("sealed",len(out),len(next(iter(out.values()))["ranked"]["new"]))
if __name__=="__main__":main()
