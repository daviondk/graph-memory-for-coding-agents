"""Frozen transfer of the R50 reader to the HotpotQA training split."""
from collections import Counter
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

D = Path(__file__).resolve().parent
G = D.parents[1] / "graph_memory_round50/gate_confirmation"
P = Path("D:/CodexResearch/x20-r51-hotpot-gate")
FILES = sorted(P.glob("train-?????-of-00002.parquet"))
sys.path.insert(0, str(G))
from paths_a import get, put, sha, hexb, ENCODER, MODEL, SERVER, DIGEST
from common import R46, R47
from rewire import catalog, tie
from panel import norm

N = 640
ARMS = ("adaptive", "linked_dense", "dense")
THRESHOLD = 0.04178261756896973
RUNTIME = G / "runtime.py"
EVAL_HASH = "d35fc91a6db21d791dbdda11daf3856e9359f5701d54e3eefba20d88fecc02c0"

def shared(name):
    """Reuse a pinned historical implementation with study-local input/output paths."""
    path = G / (name + ".py")
    if not path.exists():
        path = D.parents[1] / "graph_memory_round49/qa_transfer" / (name + ".py")
    spec = importlib.util.spec_from_file_location("archived_" + name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.D, module.P, module.check = D, P, check
    return module

def check():
    reg = get(D/"registration.json")
    assert sha(D/"PROTOCOL_RU.md") == reg["protocol"]
    assert sha(G/"manifest.json") == reg["parent"]
    assert sha(G/"threshold-seal.json") == reg["threshold"]
    assert get(G/"threshold-seal.json")["primary"] == THRESHOLD

def register():
    assert len(FILES) == 2 and not (D/"registration.json").exists()
    assert sha(ENCODER) == DIGEST and sha(P/"official.py") == EVAL_HASH
    meta = get(G/"registration.json")
    assert sha(SERVER) == meta["runtime"]
    put(D/"registration.json", dict(protocol=sha(D/"PROTOCOL_RU.md"),parent=sha(G/"manifest.json"),
        runtime=meta["runtime"],reader=sha(MODEL),encoder=DIGEST,threshold=sha(G/"threshold-seal.json"),
        shards={p.name:sha(p) for p in FILES},evaluator=EVAL_HASH))
    put(D/"threshold-seal.json", dict(primary=THRESHOLD, registration=sha(D/"registration.json")))
    
def columns(path, fields):
    import pyarrow.parquet as pq
    for batch in pq.ParquetFile(path).iter_batches(batch_size=512,columns=fields):
        yield from batch.to_pylist()

def doc_hash(t, b):
    return hexb((t+"\0"+b).encode())

def select():
    check()
    from paths_a import HP, DEV, OLD
    visited_q, visited_id, visited_doc = set(), set(), set()
    def record(q, question, docs):
        visited_q.add(norm(question))
        visited_id.add(q)
        visited_doc.update(doc_hash(t,b) for t,b in docs)
    for q,r in get(HP).items():
        record(q,r["q"],[(t," ".join(ss)) for t,ss in zip(r["titles"],r["sentences"],strict=True)])
    for x in columns(DEV,["_id","question","context"]):
        record(x["_id"],x["question"],[(t," ".join(ss)) for t,ss in json.loads(x["context"])])
    for prior in (OLD, Path("D:/CodexResearch/x20-r50-adaptive-address"),Path("D:/CodexResearch/x20-r50-gate-confirmation")):
        for q,(question,docs) in get(prior/"visible.json.gz").items():
            record(q,question,[(t,b) for i,t,b in docs])
    ids = [x["id"] for p in FILES for x in columns(p, ["id"])]
    assert len(set(ids)) == len(ids) == 90447
    ids.sort(key=lambda q: hexb(("r51-hotpot-gate-v1|"+q).encode()))
    seen_first, seen_q, overlap, visible, examined = set(), set(), {}, {}, Counter()
    for off in range(0,len(ids),4096):
        chunk=ids[off:off+4096]
        eligible=set(chunk)
        records={r["id"]:r for p in FILES for r in columns(p,["id","question","context"]) if r["id"] in eligible}
        for q in chunk:
            x=records[q]
            question=x["question"]
            text=norm(question)
            if q in visited_id or text in visited_q or text in seen_q:
                examined["question"]+=1
                continue
            docset=[[i,t," ".join(sent)] for i,(t,sent) in enumerate(zip(x["context"]["title"],x["context"]["sentences"],strict=True))]
            idx=sorted(range(len(docset)),key=lambda i:tie(q+"|"+docset[i][1]))
            vals=catalog(question,[docset[i][1] for i in idx])[2](question)
            seed = idx[max(range(len(vals)),key=vals.__getitem__)]
            hashes=[doc_hash(t,b) for i,t,b in docset]
            if hashes[seed] in visited_doc or hashes[seed] in seen_first:
                examined["first"]+=1
                continue
            overlap[q]={"first":hashes[seed],"historical_other_docs":sorted(visited_doc.intersection(hashes))}
            seen_q.add(text)
            seen_first.add(hashes[seed])
            visible[q]=[question,docset]
            if len(visible)==N:break
        if len(visible)==N:break
    assert len(seen_q)==len(seen_first)==len(visible)==N
    put(P/"visible.json.gz",visible)
    put(D/"overlap.json.gz",overlap)
    put(D/"panel.json",dict(order=list(visible),N=N,source_count=len(ids),rejections=examined,
        history_questions=len(visited_q),history_ids=len(visited_id),history_docs=len(visited_doc),
        historical_first_overlaps=0,historical_id_overlaps=0,historical_question_overlaps=0,
        shared_other_doc_queries=sum(bool(v["historical_other_docs"]) for v in overlap.values()),
        unique_first=len(seen_first),visible=sha(P/"visible.json.gz"),registration=sha(D/"registration.json")))
    print("Frozen Hotpot panel",len(visible),examined,flush=True)

def run(stage):
    if stage=="register":register()
    elif stage=="select":select()
    elif stage in ("lex_orders","projection","encode","inputs_sem","reader_tokens","generate","costs"):
        check()
        shared(stage).main()
    else:raise ValueError(stage)

if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("stages",nargs="+")
    for stage in parser.parse_args().stages:run(stage)
