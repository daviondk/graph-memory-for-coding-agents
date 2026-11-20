"""Use only the preregistered issue & ranking projection and Git records reachable from base."""
from pathlib import Path, PurePosixPath
from collections import Counter, defaultdict
from functools import lru_cache
import gzip,hashlib,itertools,json,math,re,sys,time
from concurrent.futures import ProcessPoolExecutor
ROOT=Path(__file__).resolve().parent
ARMS=("native","flat","direct","event","interaction_off","sharing_off","event_only","placebo","frequency")
STOP={"the","a","an","if","i","is","there","and","or","it","of","to","that","in","for","this","as","be","which","but","when","not","by","the","with","are","from","have","has","we","can","will","was","should","you","on","my","any","with","does","what","then","use","used","about","than","same","after","before","would","now","using","into","its","out","at","were","they","been","these","do","also","me","their","some","how","seems","as","no","more","may","am","error","issue","python","file","line","py","src","lib","init","return"}
DROP={"tests","test","testing","testdata","fixtures","_vendor","vendor","vendored","third_party","generated",
      "docs","doc","docutils","examples","example","migrations","benchmarks","benchmark","build","dist"}
def load(path):return json.loads(gzip.decompress(path.read_bytes()))
def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def safe_file(f):
    p=PurePosixPath(f)
    return (p.suffix==".py" and f.isascii() and not any(v.lower() in DROP for v in p.parts) and
            not p.stem.startswith("test_") and not p.stem.endswith("_test") and p.name not in {"setup.py","conftest.py"})
@lru_cache(maxsize=64000)
def tokens(s):
    s=re.sub(r"([A-Z])([A-Z][a-z])",r"\1 \2",s)
    s=re.sub(r"([a-z0-9])([A-Z])",r"\1 \2",s)
    return tuple(w for w in re.findall("[a-z][a-z0-9]+",s.lower()) if w not in STOP)
def order(score):return sorted((x for x,v in score.items() if v>0),key=lambda x:(-score[x],x))
def fuse(*channels):
    out=Counter()
    for weight,seq in channels:
        for idx,x in enumerate(seq,1):out[x]+=weight/(10+idx)
    return out
def evidence(history,allowed,anchors,text,variant):
    aw={a:1/k for k,a in enumerate(anchors,1)}
    total=sum(aw.values())
    aw={a:v/total for a,v in aw.items()}
    graph={k:Counter() for k in ("direct","event","interaction_off","sharing_off")}
    freq=Counter()
    citations=defaultdict(list)
    for j,(sha,subject,paths) in enumerate(history):
        age=2**(-j/192)
        raw=[p for p in paths if safe_file(p)]
        paths=set(raw)&allowed
        for p in paths:freq[p]+=age
        if not 2<=len(raw)<=24:continue
        matching=sorted(aw[a] for a in paths if a in aw)
        if not matching:continue
        companions=paths-aw.keys()
        if not companions:continue
        mass=sum(matching)
        interaction=sum(v*(len(matching)-i-1) for i,v in enumerate(matching))
        for f in companions:
            graph["direct"][f]+=age*mass
            graph["sharing_off"][f]+=age*(mass+interaction)
            graph["interaction_off"][f]+=age*mass/len(companions)
            weight=age*(mass+interaction)/len(companions)
            graph["event"][f]+=weight
            citations[f].append((weight,sha))
    for k in ("event","interaction_off"):
        for f in graph[k]:graph[k][f]/=math.sqrt(1+freq[f])
    return graph,freq,citations
def rank_one(row):
    start=time.perf_counter()
    base=row["base"]
    result={"id":row["id"],"repo":row["repo"],"base":base,"date":row["date"],"native_len":len(row["native"])}
    native=list(dict.fromkeys(row["native"]))[:5]
    def unchanged(reason):
        result.update(reason=reason,ranks={a:native for a in ARMS},seconds=time.perf_counter()-start)
        return result
    if row["excluded"]:return unchanged("scope")
    doc=load(ROOT/"history"/(base+".json.gz"))
    if doc.get("unavailable"):return unchanged("missing_base")
    if len(native)>=5:return unchanged("native_full")
    allowed={f for f in doc["files"] if safe_file(f)}
    pool=sorted(allowed-set(native))
    docs=doc["events"]
    qt=Counter(tokens(row["question"][:40000]))
    path_terms={f:set(tokens(f)) for f in pool}
    df=Counter(t for docset in path_terms.values() for t in docset)
    # IDF over path postings. Restrict term weight to guard repeated lines in issue text.
    path={f:sum(min(2,qt[t])*math.log(1+(len(pool)-df[t]+.5)/(df[t]+.5)) for t in sorted(ts&qt.keys()))/
          math.sqrt(1+len(ts)) for f,ts in path_terms.items()}
    subjects=[Counter(tokens(subject)) for _,subject,_ in docs]
    db=Counter(w for d in subjects for w in d)
    avg=sum(d.total() for d in subjects)/max(len(subjects),1) or 1
    tf=Counter()
    for j,((sha,_,files),words) in enumerate(zip(docs,subjects)):
        score=0
        for word in sorted(qt.keys()&words.keys()):
            cnt=words[word]
            idf=math.log(1+(len(subjects)-db[word]+.5)/(db[word]+.5))
            score+=min(2,qt[word])*idf*cnt*2.2/(cnt+1.2*(.25+.75*words.total()/avg))
        if score>0:
            candidates=set(files)&allowed
            val=score*2**(-j/192)/math.sqrt(max(len(candidates),1))
            # single strongest similar past subject; no graph-dependent anchor here
            for f in candidates:
                tf[f]=max(tf[f],val)
    anchors=native
    graph,freq,citations=evidence(docs,allowed,anchors,qt,"normal")
    def only_candidates(seq):return [f for f in seq if f in allowed and f not in native]
    flat_score=fuse((1,only_candidates(order(path))),(1,only_candidates(order(tf))),(.25,only_candidates(order(freq))))
    flatlist=order(flat_score)
    flatlist=flatlist+sorted(set(pool)-set(flatlist))
    # Shuffle identities inside marginal-frequency deciles by a deterministic bijection.
    by_freq=sorted(allowed,key=lambda f:(freq[f],f)); bins=defaultdict(list)
    for i,f in enumerate(by_freq):bins[min(9,i*10//max(len(by_freq),1))].append(f)
    perm={}
    for group in bins.values():
        ordered=sorted(group,key=lambda f:hashlib.sha256((base+"|"+f).encode()).digest())
        for i,f in enumerate(ordered):perm[f]=ordered[(i+1)%len(ordered)]
    inv={b:a for a,b in perm.items()}
    false,_,_=evidence(docs,allowed,[perm.get(f,f) for f in native],qt,"placebo")
    graph["placebo"]=Counter({inv[f]:s for f,s in false["event"].items()})
    ranks={"native":native,"flat":native+flatlist[:5-len(native)]}
    for k,counts in graph.items():
        glist=only_candidates(order(counts))
        mix=order(fuse((1,flatlist),(2,glist)))
        ranks[k]=native+mix[:5-len(native)]
        if k=="event":
            alone=glist+[x for x in flatlist if x not in set(glist)]
            ranks["event_only"]=native+alone[:5-len(native)]
    ff=only_candidates(order(freq))
    ranks["frequency"]=native+(ff+[x for x in flatlist if x not in set(ff)])[:5-len(native)]
    assert set(ranks)==set(ARMS)
    assert all(len(set(v))==len(v) and v[:len(native)]==native and len(v)<=5 for v in ranks.values())
    supported={f: [s for _,s in sorted(citations[f],reverse=True)[:4]] for f in ranks["event"][len(native):]}
    result.update(reason="completed",ranks=ranks,source_witness=supported,files=len(pool),history=len(docs),
                  seconds=time.perf_counter()-start)
    return result
def main():
    rows=load(ROOT/"input/questions.json.gz")
    with ProcessPoolExecutor(max_workers=4) as pool:
        out=list(pool.map(rank_one,rows,chunksize=3))
    (ROOT/"predictions.jsonl").write_text("".join(json.dumps(r,ensure_ascii=True,sort_keys=True)+"\n" for r in out),encoding="utf8")
    lock={p:digest(ROOT/p) for p in ("PROTOCOL.md","prepare.py","rank.py","sources.json","predictions.jsonl")}
    (ROOT/"prediction_lock.json").write_text(json.dumps(lock,indent=2),encoding="utf8")
    print(Counter(r["reason"] for r in out),lock["predictions.jsonl"])
if __name__=="__main__":main()

