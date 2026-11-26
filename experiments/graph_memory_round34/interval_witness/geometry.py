"""Recompute native interval witnesses. Export only numerical geometry and hashed addresses."""
import gzip,hashlib,json,os,re,sqlite3,sys
from collections import Counter,defaultdict
from pathlib import Path
for k in ("OPENBLAS_NUM_THREADS","MKL_NUM_THREADS","OMP_NUM_THREADS"):os.environ[k]="1"
D=Path(__file__).resolve().parent
W=D.parents[1];B=W/"graph_memory_round33/budget_loss";C=D.parent/"cost_push"
sys.path.insert(0,str(B))
import data as old
import numpy as np
load,save,sha=old.load,old.save,old.sha
def feature(stage):
    path=old.PRIVATE/(stage+".json.gz");assert sha(path)==load(B/(stage+"-input.json"))["features"]
    return load(path)
def key(span):return span["event_id"],span["json_pointer"]
def atomize(ordered,truth):
    gold=defaultdict(list);candidate=defaultdict(list)
    for s in truth:gold[key(s)].append((s["char_start"],s["char_end"]))
    for i,spans in enumerate(ordered):
        for s in spans:
            if key(s) in gold:candidate[key(s)].append((s["char_start"],s["char_end"],i))
    result=[]
    for addr in sorted(gold):
        intervals=[]
        for l,r in sorted(gold[addr]):
            if intervals and l<=intervals[-1][1]:intervals[-1][1]=max(intervals[-1][1],r)
            else:intervals.append([l,r])
        field=hashlib.sha256(json.dumps(addr,ensure_ascii=False).encode()).hexdigest()[:16]
        for l,r in intervals:
            touching=[(a,b,i) for a,b,i in candidate[addr] if a<r and l<b]
            cuts=sorted({l,r,*[v for a,b,i in touching for v in (a,b) if l<v<r]})
            for u,v in zip(cuts,cuts[1:]):
                indices=sorted({i for a,b,i in touching if a<=u and b>=v})
                if result and result[-1][0]==field and result[-1][2]==u and result[-1][3]==indices:result[-1][2]=v
                else:result.append([field,u,v,indices])
    assert result and all(l<r for _,l,r,_ in result)
    return result
def buckets(atoms):
    groups={frozenset(ids) for _,_,_,ids in atoms}
    return sorted([sorted(g) for g in groups if not any(h<g for h in groups)],key=lambda g:(len(g),g))
def ranks(scores):return np.argsort(-np.asarray(scores),kind="stable")
def inspect(rows,records):
    count=Counter();dyn=Counter()
    for q,atoms in rows.items():
        groups=buckets(atoms);sets=[i for *_,i in atoms]
        count["questions"]+=1;count["atoms"]+=len(atoms);count["distinct_minimal_groups"]+=len(groups)
        count["any_multi_atom"]+=any(len(s)>1 for s in sets);count["any_empty"]+=any(not s for s in sets)
        count["any_multi_minimal_group"]+=any(len(s)>1 for s in groups)
        pos=set().union(*map(set,sets));sing={g[0] for g in groups if len(g)==1}
        count["any_nonessential_positive"]+=bool(pos-sing);count["nonessential_positives"]+=len(pos-sing)
        count["positive_nodes"]+=len(pos);dyn[len(groups)]+=1
        if all(sets):
            rank=np.argsort(ranks(records[q]["o"]));finish=max(min(rank[i] for i in g) for g in groups)
            count["frozen_completes_before_last_positive"]+=int(finish<max(rank[i] for i in pos))
    return dict(count),dict(dyn)
def native_train(rows):
    sys.path.insert(0,str(W/"graph_memory_round19/trained_rank"))
    # Full path avoids a module-name collision with other imported projection helpers.
    import importlib.util
    spec=importlib.util.spec_from_file_location("atom_native_prepare",W/"graph_memory_round19/trained_rank/prepare.py")
    p=importlib.util.module_from_spec(spec);spec.loader.exec_module(p)
    by=defaultdict(set)
    for q,r in rows.items():by[r["t"]].add(q)
    examples={r["id"]:p.N._QUERY_ADAPTER.validate_python(r) for _,r in p.pilot.stream(p.pilot.Q) if r["id"] in rows}
    locks={v["path"]:v["sha256"] for v in load(p.OFF/"source-lock.json")}
    # Check native query file independently of its directory prefix.
    qs_sha=sha(p.pilot.Q);assert qs_sha in set(locks.values()),qs_sha
    out={};hashes={};pattern=re.compile(rb'"session_id"\s*:\s*"(traj_[^"]+)"')
    db=sqlite3.connect(Path("D:/CodexResearch/x20-isetrace-residual/vectors.sqlite3").as_uri()+"?mode=ro",uri=True)
    reader=old.f.DenseTaskRetriever(encoder=old.f.Lookup(db,"ft"),device="cpu")
    old_evidence=load(W/"graph_memory_round19/write_learned/train-evidence.json.gz")
    common=0
    for shard in range(8):
        path=p.RAW/f"trajectories-{shard:05d}.jsonl";hashes[path.name]=sha(path);assert hashes[path.name]==locks["trajectories/"+path.name]
        with path.open("rb") as fp:
            for buf in fp:
                t=pattern.search(buf).group(1).decode()
                if t not in by:continue
                proj=load(old.PROJ/"train"/(t+".json.gz"));assert hashlib.sha256(buf).hexdigest()==proj["digest"]
                tr=p.adapt_isetrace_record(p.parse_isetrace_record(json.loads(buf)),source_revision=p.pilot.RAW[1])
                candidates=tuple(old.f.TextCandidate.model_validate(v) for v in proj["pool"])
                sp={v["item_id"]:v["source_spans"] for v in proj["pool"]}
                for v in proj["qs"]:
                    q=v["q"];assert q in by[t]
                    ex=examples[q];m=p.N._match_task_text(ex,tr);assert m is not None
                    truth=[s.model_dump(mode="json") for s in p.N._resolve_gold_spans(ex,m)]
                    if t in old_evidence:assert old_evidence[t]["q"][q]==truth;common+=1
                    ranked=reader.rank(old.f.TextRankingRequest(task_id=q,query_text=v["text"],candidates=candidates))
                    ids=[r.node_id for r in ranked];at=atomize([sp[i] for i in ids],truth)
                    flag=sorted(set(i for *_,g in at for i in g))
                    assert flag==rows[q]["y"]==[i for i,k in enumerate(ids) if k in v["positive"]]
                    out[q]=at
        print("native shard",shard,len(out),flush=True)
    db.close();assert set(out)==set(rows)
    return out,dict(raw_shards=hashes,queries_sha=qs_sha,snapshot=p.pilot.RAW[1],match_cached_native=common)
def collect(stage):
    rows={r["q"]:r for r in feature(stage)}
    if stage=="train":atoms,meta=native_train(rows)
    else:
        if stage=="test":assert (D/"selection.json").exists() and (D/"test-rank-seal.json").exists()
        ref=old.R19/"write_transfer/gold-spans.json.gz" if stage=="dev" else old.nm.OFF/"gold-spans.json.gz"
        gold=load(ref);atoms={};meta={"native_gold_sha":sha(ref),"candidate_sources":{}}
        for path in old.sources(stage):
            meta["candidate_sources"][str(path)]=sha(path)
            for ex in load(path):
                q=ex["q"];assert rows[q]["c"]==[n["token_count"] for n in ex["rr"]]
                atoms[q]=atomize([v["source_spans"] for v in ex["rr"]],gold[q])
    assert set(atoms)==set(rows);p=D/(stage+"-atoms.json.gz");save(p,atoms)
    c,h=inspect(atoms,rows)
    save(D/(stage+"-geometry.json"),dict(counts=c,min_groups_hist=h,source=meta,atoms=sha(p),protocol=sha(D/"PROTOCOL_RU.md")))
    print(stage,c,flush=True)
if __name__=="__main__":collect(sys.argv[1])