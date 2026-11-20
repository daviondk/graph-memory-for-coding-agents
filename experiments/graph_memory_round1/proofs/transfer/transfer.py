"""Transport the frozen protocol and test active checks on the graph of saved edges."""
from collections import deque
from concurrent.futures import ProcessPoolExecutor
import gzip, hashlib, json, random, statistics, sys, time
from pathlib import Path
DEST=Path(__file__).resolve().parent
sys.path.insert(0,str(DEST.parent))
import run
import score

def extra_paths(proofs):
    adj={}
    for path in proofs:
        for u,v in zip(path,path[1:]):
            adj.setdefault(u,set()).add(v)
    s,t=proofs[0][0],proofs[0][-1]
    queue=deque([(s,)])
    candidates=[]
    while queue:
        p=queue.popleft()
        if p[-1]==t:
            candidates.append(p)
        elif len(p)<=4:
            for n in sorted(adj.get(p[-1],())):
                if n not in p:
                    queue.append(p+(n,))
    return candidates

def verify_arm(proofs, mode, old,new,adj,truth):
    start,end=proofs[0][0],proofs[0][-1]
    alternatives=extra_paths(proofs) if mode=="union" else [tuple(p) for p in proofs]
    possible=[p for p in alternatives if all(n in new and new[n][0]==old[n][0] for n in p)]
    unresolved={u for p in possible for u in p[:-1] if old[u][1]!=new[u][1]}
    seen=set()

    def pending(path):
        return [u for u in path[:-1] if u in unresolved and u not in seen]

    def viable(path):
        return all(u not in seen or v in adj[u] for u,v in zip(path,path[1:]))

    def order(path):
        return (len(pending(path)),len(path),path)

    certified=False
    if mode=="sorted":
        # Ordered once, but the evidence acquired during previous failures remains valid.
        for path in sorted(possible,key=order):
            if not viable(path):
                continue
            for u,v in zip(path,path[1:]):
                if u in unresolved:
                    seen.add(u)
                    if v not in adj[u]:
                        break
            else:
                certified=True
                break
    else:
        while True:
            viable_paths=[p for p in possible if viable(p)]
            if not viable_paths:
                break
            need=pending(min(viable_paths,key=order))
            if not need:
                certified=True
                break
            seen.add(need[0])
    found=certified
    if not found and start in new and end in new:
        todo=deque([(start,0)])
        entered={start}
        while todo and not found:
            u,level=todo.popleft()
            if level>=4:
                continue
            seen.add(u)
            for v in adj[u]:
                if v==end:
                    found=True
                    break
                if v not in entered:
                    entered.add(v)
                    todo.append((v,level+1))
    assert found==truth
    return {"reads":len(seen),"certified":int(certified),"paths":len(alternatives),"answer":int(found)}

def project(entry):
    # Lock retains the G1b provenance path. Byte-identical SHA objects are served from the
    # fully populated local mirror to avoid individual network calls by blobless Git.
    entry = list(entry)
    local = DEST/"content_mirrors"/entry[0]
    if local.exists():
        assert run.git(local, "rev-parse", entry[3]).decode().strip() == entry[3]
        entry[2] = str(local)
    run.ROOT=DEST
    summary=run.process(entry)
    name,_,directory,head,ids=entry
    repo=Path(directory)
    indices=list(range(0,min(6,(len(ids)-1)//12)*12+1,12))
    trees=[run.tree(repo,ids[i]) for i in indices]
    graphs,_,_=run.populate(repo,trees)
    snapshot={ids[i]:(trees[j],graphs[j]) for j,i in enumerate(indices)}
    source=DEST/"shards"/(name+".jsonl.gz")
    out=[]
    for row in (json.loads(x) for x in gzip.decompress(source.read_bytes()).splitlines() if x):
        old,_=snapshot[row["before"]]; new,adj=snapshot[row["after"]]
        truth=bool(row["truth"])
        selected=row["historical"]["proofs"]
        item={k:row[k] for k in ("repo","before","after","s","t","truth")}
        item["fixed"]={k:row["historical"][k] for k in ("reads","validated")}
        for a in ("sorted","adaptive","union"):
            item[a]=verify_arm(selected,a,old,new,adj,truth)
        out.append(item)
    where=DEST/"reading";where.mkdir(exist_ok=True)
    shard=where/(name+".jsonl.gz")
    shard.write_bytes(gzip.compress(("\n".join(json.dumps(x,separators=(",",":")) for x in out)+"\n").encode(),mtime=0))
    summary["reading_sha256"]=hashlib.sha256(shard.read_bytes()).hexdigest()
    return summary

def main():
    pins=json.loads((DEST.parents[1]/"git_prediction/transfer_pins.json").read_text(encoding="utf-8-sig"))
    source=DEST.parents[1]/"git_prediction/transfer_mirrors"
    entries=[]
    for pin in pins:
        name=pin["repo"]
        if name in {"psf__black","sphinx-doc__sphinx"}:
            continue
        repo=source/name
        ids=run.git(repo,"rev-list","--first-parent","--max-count=97",pin["sha"]).decode().splitlines()
        assert ids[0]==pin["sha"]
        entries.append([name,"C",str(repo),pin["sha"],ids])
    assert len(entries)==8
    lock=DEST/"input_lock.json"
    if lock.exists():
        assert json.loads(lock.read_text(encoding="utf-8"))==entries
    else:
        lock.write_text(json.dumps(entries,indent=2),encoding="utf-8")
    start=time.perf_counter()
    with ProcessPoolExecutor(max_workers=3) as workers:
        meta=list(workers.map(project,entries))
    out={"python":sys.version,"runtime_s":time.perf_counter()-start,"repositories":meta}
    (DEST/"receipt.json").write_text(json.dumps(out,indent=2),encoding="utf-8")
    repos={}
    for m in meta:
        def load(folder):
            return [json.loads(line) for line in gzip.decompress((DEST/folder/(m["repo"]+".jsonl.gz")).read_bytes()).splitlines() if line]
        rows=load("shards");rr=load("reading")
        assert len(rows)==len(rr)==m["rows"]
        if not rows:
            continue
        def summ(a,k):
            return sum(r[a][k] for r in rows)
        n=len(rows)
        repos[m["repo"]]={"n":n,"lost":sum(not r["truth"] for r in rows),"fast":{a:summ(a,"fast") for a in run.ARMS},
            "read":{a:sum(r[a]["reads"] for r in rr) for a in ("fixed","sorted","adaptive","union")},
            "more_paths":sum(r["union"]["paths"]>r["adaptive"]["paths"] for r in rr),
            "union_wins":sum(r["union"]["reads"]<r["sorted"]["reads"] for r in rr),
            "union_losses":sum(r["union"]["reads"]>r["sorted"]["reads"] for r in rr),
            "read_dist":dict((str(i),sum(r["union"]["reads"]-r["sorted"]["reads"]==i for r in rr)) for i in sorted({r["union"]["reads"]-r["sorted"]["reads"] for r in rr})),
            "history_wins":sum(r["historical"]["fast"]>r["short3"]["fast"] for r in rows),
            "history_losses":sum(r["historical"]["fast"]<r["short3"]["fast"] for r in rows)}
    def effect(f,a,b):
        ds=[(r[f][a]-r[f][b])/r["n"] for r in repos.values()]
        rng=random.Random(261118)
        boot=sorted(statistics.mean(rng.choices(ds,k=len(ds))) for _ in range(10000))
        return {"mean":statistics.mean(ds),"ci":[score.quantile(boot,.025),score.quantile(boot,.975)]}
    sums={"n":sum(r["n"] for r in repos.values()),"lost":sum(r["lost"] for r in repos.values()),
          "fast":{a:sum(r["fast"][a] for r in repos.values()) for a in run.ARMS},
          "reads":{a:sum(r["read"][a] for r in repos.values()) for a in ("fixed","sorted","adaptive","union")}}
    for k in ("more_paths","union_wins","union_losses","history_wins","history_losses"):
        sums[k]=sum(r[k] for r in repos.values())
    res={"totals":sums,"per_repo":repos,"transfer_effect":effect("fast","historical","short3"),
         "reading_effect":effect("read","union","sorted"),"adaptive_effect":effect("read","adaptive","sorted"),
         "simple_sorting":effect("read","sorted","fixed")}
    print(json.dumps({k:v for k,v in res.items() if k!="per_repo"},indent=2))
    (DEST/"results.json").write_text(json.dumps(res,indent=2),encoding="utf-8")
if __name__=="__main__":
    main()


