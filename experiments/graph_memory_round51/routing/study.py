"""Fresh HotpotQA holdout for a question-only routing rule."""
from collections import Counter
import argparse
import importlib.util
import json
from pathlib import Path
import re
import sys

D = Path(__file__).resolve().parent
T = D.parent/"transfer"
P = Path("D:/CodexResearch/x20-r51-hotpot-routing")
FIRST = Path("D:/CodexResearch/x20-r51-hotpot-gate")
N = 1280
spec = importlib.util.spec_from_file_location("r51_transfer_study",T/"study.py")
base = importlib.util.module_from_spec(spec)
spec.loader.exec_module(base)
get, put, sha, hexb = base.get, base.put, base.sha, base.hexb
G, SERVER, MODEL, ARMS, EVAL_HASH = base.G, base.SERVER, base.MODEL, base.ARMS, base.EVAL_HASH
FILES = sorted(FIRST.glob("train-?????-of-00002.parquet"))
columns = base.columns
WORDS = set("both either same different than earlier later older younger longer shorter larger smaller taller higher lower more fewer most least".split())
AUX = set("are were do did have has is was".split())


def comparison_flag(question):
    tokens=re.findall(r"[a-z]+",question.lower())
    return bool(WORDS.intersection(tokens) or (tokens and tokens[0] in AUX and {"and","or"}.intersection(tokens)))


def check():
    rec=get(D/"registration.json")
    assert rec["protocol"]==sha(D/"PROTOCOL_RU.md") and rec["code"]==sha(D/"study.py")
    assert rec["transfer"]==sha(T/"SHA256.json") and rec["method_parent"]==sha(G/"manifest.json")


def register():
    assert not (D/"registration.json").exists()
    orig=get(T/"registration.json")
    assert orig["shards"]=={p.name:sha(p) for p in FILES}
    assert orig["evaluator"]==sha(P/"official.py")
    put(D/"registration.json",dict(protocol=sha(D/"PROTOCOL_RU.md"),code=sha(D/"study.py"),
        transfer=sha(T/"SHA256.json"), method_parent=sha(G/"manifest.json"),runtime=orig["runtime"],
        reader=orig["reader"],encoder=orig["encoder"],shards=orig["shards"],evaluator=orig["evaluator"]))
    put(D/"threshold-seal.json",dict(primary=base.THRESHOLD,registration=sha(D/"registration.json")))


def shared(name):
    module=base.shared(name)
    module.D,module.P,module.check=D,P,check
    return module


def select():
    from paths_a import HP, DEV, OLD
    from rewire import tie,catalog
    from panel import norm
    check()
    old_ids,old_q,old_docs=set(),set(),set()
    def remember(q,question,parts):
        old_ids.add(q)
        old_q.add(norm(question))
        old_docs.update(base.doc_hash(t,b) for t,b in parts)
    for q,v in get(HP).items():
        remember(q,v["q"],[(t," ".join(s)) for t,s in zip(v["titles"],v["sentences"],strict=True)])
    for x in columns(DEV,["_id","question","context"]):
        remember(x["_id"],x["question"],[(t," ".join(s)) for t,s in json.loads(x["context"])])
    for hist in [OLD,Path("D:/CodexResearch/x20-r50-adaptive-address"),Path("D:/CodexResearch/x20-r50-gate-confirmation"),FIRST]:
        for q,(question,docs) in get(hist/"visible.json.gz").items():
            remember(q,question,[(t,b) for i,t,b in docs])
    all_ids=[x["id"] for p in FILES for x in columns(p,["id"])]
    assert len(set(all_ids))==len(all_ids)==90447
    all_ids.sort(key=lambda q:hexb(("r51-hotpot-router-confirm-v1|"+q).encode()))
    seen_q,first_hashes,view,overlap,flags,counts=set(),set(),{},{},{},Counter()
    for off in range(0,len(all_ids),4096):
        chunk=all_ids[off:off+4096];roster=set(chunk)
        src={r["id"]:r for p in FILES for r in columns(p,["id","question","context"]) if r["id"] in roster}
        for q in chunk:
            r=src[q];question=r["question"];qn=norm(question)
            if q in old_ids or qn in old_q or qn in seen_q:
                counts["question"]+=1
                continue
            docs=[[i,t," ".join(s)] for i,(t,s) in enumerate(zip(r["context"]["title"],r["context"]["sentences"],strict=True))]
            idx=sorted(range(len(docs)),key=lambda i:tie(q+"|"+docs[i][1]))
            scores=catalog(question,[docs[i][1] for i in idx])[2](question)
            first=idx[max(range(len(scores)),key=scores.__getitem__)]
            hashes=[base.doc_hash(t,b) for i,t,b in docs];h=hashes[first]
            if h in old_docs or h in first_hashes:
                counts["first"]+=1
                continue
            seen_q.add(qn);first_hashes.add(h)
            view[q]=[question,docs]
            flags[q]=comparison_flag(question)
            overlap[q]={"first":h,"historical_other_docs":sorted(old_docs.intersection(hashes))}
            if len(view)==N:break
        if len(view)==N:break
    assert len(view)==len(first_hashes)==len(seen_q)==N
    put(P/"visible.json.gz",view)
    put(D/"flags.json.gz",flags);put(D/"overlap.json.gz",overlap)
    put(D/"panel.json",dict(order=list(view),N=N,source_count=len(all_ids),rejections=counts,unique_first=len(first_hashes),
        historical_ids=len(old_ids),historical_questions=len(old_q),historical_documents=len(old_docs),shared_other_doc_queries=sum(bool(v["historical_other_docs"]) for v in overlap.values()),
        overlap=sha(D/"overlap.json.gz"),flags=sha(D/"flags.json.gz"),visible=sha(P/"visible.json.gz"),registration=sha(D/"registration.json")))
    print("Sealed question-only flags",sum(flags.values()),"of",len(view),flush=True)


def route():
    check()
    assert sha(D/"orders.json.gz")==get(D/"retrieval-seal.json")["orders"]
    assert sha(D/"flags.json.gz")==get(D/"panel.json")["flags"]
    flags,orders=get(D/"flags.json.gz"),get(D/"orders.json.gz")
    choices={q:{"arm":("dense" if f else "linked_dense"),"address":orders[q]["dense" if f else "linked_dense"]} for q,f in flags.items()}
    put(D/"router-choices.json.gz",choices)
    put(D/"route-seal.json",dict(choices=sha(D/"router-choices.json.gz"),flags=sha(D/"flags.json.gz"),
        retrieval=sha(D/"retrieval-seal.json"),code=sha(D/"study.py"),registration=sha(D/"registration.json")))


if __name__=="__main__":
    args=argparse.ArgumentParser()
    args.add_argument("stages",nargs="+")
    for stage in args.parse_args().stages:
        if stage=="register":register()
        elif stage=="select":select()
        elif stage=="route":route()
        elif stage in ("lex_orders","projection","encode","costs"):shared(stage).main()
        else:raise ValueError(stage)
