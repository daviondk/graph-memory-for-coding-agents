"""Prepare question-only hash sample, then remove earlier titles, before inspecting any label."""
from pathlib import Path
import hashlib
import os
import sys
import unicodedata
import re

HERE=Path(__file__).resolve().parent
GT=HERE.parent/"global_titles"
GP=HERE.parent/"global_policy"
sys.path.insert(0,str(GT))
from corpus import read,save,hashfile
from lexicon import tokens
S=Path("D:/CodexResearch/x20-r52-directory-confirm")
DEV=Path("D:/CodexResearch/x20-r52-wiki-directory")
R50=HERE.parents[1]/"graph_memory_round50/qa_replication"
P50=Path("D:/CodexResearch/x20-r50-qa-replication")
PAR=P50/"train.parquet"
def canon(q):
    return " ".join(re.findall(r"[^\W_]+", unicodedata.normalize("NFKC",q).casefold()))
def sig(q):
    return hashlib.sha256(("r52-disjoint-confirm-v1|"+q).encode()).hexdigest()

def candidate():
    import pyarrow.parquet as pq
    S.mkdir(exist_ok=True)
    for n in ("lex.bin","stop.bin","vocab.txt","titles.txt","para_with_hyperlink.zip"):
        if not (S/n).exists():
            os.link(DEV/n,S/n)
        assert os.path.samefile(DEV/n,S/n)
    assert hashfile(PAR)==read(R50/"registration.json")["train"]
    dev=read(DEV/"questions.json.gz")
    old=read(P50/"visible.json.gz");order=read(R50/"orders.json.gz")
    old_ids=set(old)|set(dev)
    old_questions=set(map(canon,dev.values()))|{canon(x[0]) for x in old.values()}
    allq={r["_id"]:r["question"] for b in pq.ParquetFile(PAR).iter_batches(columns=["_id","question"]) for r in b.to_pylist()}
    assert len(allq)==167454
    keep={};seen=set(old_questions);idskip=textskip=0
    for q in sorted(allq,key=sig):
        if q in old_ids:
            idskip+=1;continue
        key=canon(allq[q])
        if key in seen:
            textskip+=1;continue
        seen.add(key);keep[q]=allq[q]
        if len(keep)==4500:break
    words={s.rstrip("\n"):i for i,s in enumerate((S/"vocab.txt").open(encoding="utf8"))}
    with (S/"candidate.in").open("w",encoding="ascii",newline="\n") as f:
        for q in sorted(keep,key=sig):
            f.write(q+" "+" ".join(str(words.get(t,0)) for t in tokens(keep[q]))+"\n")
    save(S/"candidate-questions.json.gz",keep)
    old_first={row[1] for q,item in old.items() for row in item[1] if row[0]==order[q]["seed"]}
    assert len(old_first)==640
    save(S/"previous-first-names.json.gz",sorted(old_first))
    save(HERE/"candidate-receipt.json",{"total_train":len(allq),"prior_ids":len(old_ids),"prior_titles":len(old_first),
                                        "prior_normalized_questions":len(old_questions),"excluded_id_on_prefix":idskip,"excluded_text_on_prefix":textskip,
                                        "n":len(keep),"sha_candidates":hashfile(S/"candidate.in"),
                                        "protocol_sha256":hashfile(HERE/"PROTOCOL_RU.md"),"train_sha256":hashfile(PAR)})
    print("candidate receipt",len(keep),flush=True)

def accept():
    old={int(l.split("\t")[1]) for l in (DEV/"seed.tsv").read_text().splitlines()}
    old_names=set(read(S/"previous-first-names.json.gz"))
    # Also exclude textual aliases of a dev row with another Wikipedia ID.
    devp=read(GP/"predictions.json.gz")
    devnames=read(GP/"chosen-titles.json.gz")
    old_names |= {devnames[str(r["seed"])][1] for r in devp.values()}
    canon_old={canon(t) for t in old_names}
    rows=[(a,int(b),int(c),int(d)) for a,b,c,d in (l.split("\t") for l in (S/"candidate-seeds.tsv").read_text().splitlines())]
    ids={r[1] for r in rows};names={}
    with (S/"titles.txt").open(encoding="utf8") as f:
        for i,l in enumerate(f):
            if i in ids:names[i]=l.rstrip("\n").split("\t",1)[1]
    assert len(rows)==4500 and [r[0] for r in rows]==sorted((r[0] for r in rows),key=sig)
    source=read(S/"candidate-questions.json.gz")
    accept=[];excluded=0
    for q,idx,wiki,m in rows:
        if idx in old or canon(names[idx]) in canon_old:
            excluded+=1;continue
        accept.append((q,idx,wiki,m))
        if len(accept)==2400:break
    assert len(accept)==2400
    with (S/"seed.tsv").open("w",encoding="ascii",newline="\n") as f:
        for q,idx,wiki,m in sorted(accept):f.write(f"{q}\t{idx}\t{wiki}\t{idx}\t{m}\n")
    qset={r[0] for r in accept}
    save(S/"questions.json.gz",{q:source[q] for q in qset})
    lines={l.split()[0]:l for l in (S/"candidate.in").read_text().splitlines()}
    (S/"questions.in").write_bytes(("\n".join(lines[q] for q in sorted(qset))+"\n").encode())
    save(HERE/"panel.json",{"ids_in_hash_order":[r[0] for r in accept],"stage1":len(rows),"scanned":len(accept)+excluded,
         "rejected_first":excluded,"unique_first":len({r[1] for r in accept}),"used_dev_seeds":len(old),"excluded_names":len(canon_old),
         "seed_sha256":hashfile(S/"seed.tsv"),"question_sha256":hashfile(S/"questions.in")})
    print("accepted",len(accept),"rejected",excluded,flush=True)

if __name__=="__main__":
    {"candidate":candidate,"accept":accept}[sys.argv[1]]()

