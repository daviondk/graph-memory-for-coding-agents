"""Select 12k new rows with zero question and first-source overlap with previous main panels."""
from pathlib import Path
import sys,os,re,hashlib,gzip
from collections import Counter
HERE=Path(__file__).resolve().parent
CONF=HERE.parent
sys.path.insert(0,str(CONF))
from panel import read,save,hashfile,canon,tokens,GT,GP,R50,PAR,DEV,S as C_S
S=Path("D:/CodexResearch/x20-r52-directory-confirm-large")
def sortkey(q):
    return hashlib.sha256(("r52-large-independent-v1|"+q).encode()).hexdigest()
def candidate():
    import pyarrow.parquet as pq
    source=read(CONF/"candidate-receipt.json")["train_sha256"]
    assert hashfile(PAR)==source
    S.mkdir(exist_ok=True)
    for k in ("lex.bin","stop.bin","vocab.txt","titles.txt","para_with_hyperlink.zip","confirm-seeds.exe"):
        p=C_S/k
        if not (S/k).exists():os.link(p,S/k)
        assert os.path.samefile(p,S/k)
    allq={r["_id"]:r["question"] for b in pq.ParquetFile(PAR).iter_batches(columns=["_id","question"]) for r in b.to_pylist()}
    devq=read(DEV/"questions.json.gz");prev=read(C_S/"questions.json.gz")
    history=set(devq)|set(prev)
    archived=read(CONF/"novelty.json");old=set()
    rx=re.compile(rb"(?<![a-fA-F0-9])[a-fA-F0-9]{32}(?![a-fA-F0-9])")
    known=set(allq)|set(devq)
    for _,path,_,_,digest in archived["matching_inputs"]:
        p=Path(path)
        if not p.is_absolute():p=HERE.parents[2]/p
        assert hashfile(p)==digest
        data=p.read_bytes()
        if p.suffix==".gz":data=gzip.decompress(data)
        old.update({m[0].decode().lower() for m in rx.finditer(data)}&known)
    assert len(old)==archived["history_ids"]
    history|=old
    merged=devq|allq
    seen={canon(merged[q]) for q in history}
    remain={};skipped=Counter()
    for q in sorted(allq,key=sortkey):
        if q in history:skipped["old_id"]+=1;continue
        key=canon(allq[q])
        if key in seen:skipped["old_or_duplicate_question"]+=1;continue
        remain[q]=allq[q];seen.add(key)
        if len(remain)==22000:break
    assert len(remain)==22000
    dic={v.rstrip("\n"):i for i,v in enumerate((S/"vocab.txt").open(encoding="utf8"))}
    with (S/"candidate.in").open("w",encoding="ascii",newline="\n") as f:
        for q in sorted(remain,key=sortkey):f.write(q+" "+" ".join(str(dic.get(t,0)) for t in tokens(remain[q]))+"\n")
    save(S/"candidate-questions.json.gz",remain)
    titles=set(read(C_S/"previous-first-names.json.gz"))
    for component,visible in [("gate_confirmation","gate-confirmation"),("adaptive_address","adaptive-address"),("qa_external","qa-external"),("qa_replication","qa-replication")]:
        orders=read(R50.parent/component/"orders.json.gz")
        catalogue=read(Path("D:/CodexResearch")/("x20-r50-"+visible)/"visible.json.gz")
        assert set(orders)==set(catalogue)
        titles.update(row[1] for q,(_,rows) in catalogue.items() for row in rows if row[0]==orders[q]["seed"])
    historical_count=len(titles)
    for root in (GP,CONF):
        pred=read(root/"predictions.json.gz");names=read(root/"chosen-titles.json.gz")
        titles.update(names[str(r["seed"])][1] for r in pred.values())
    save(S/"old-first-titles.json.gz",sorted({canon(t) for t in titles}))
    save(HERE/"sampling.json",dict(candidate_n=len(remain),history_ids=len(history),history_titles=historical_count,
         old_names=len(read(S/"old-first-titles.json.gz")),exclusions=skipped,source_sha256=source,
         historical_id_receipt=hashfile(CONF/"novelty.json"),candidate_input=hashfile(S/"candidate.in"),protocol=hashfile(HERE/"PROTOCOL_RU.md")))
    print("candidate",len(remain),len(history),historical_count)

def accept():
    forbid=set(read(S/"old-first-titles.json.gz"))
    prioridx={int(l.split("\t")[1]) for p in (DEV/"seed.tsv",C_S/"seed.tsv") for l in p.read_text().splitlines()}
    rows=[(q,int(r),int(w),int(n)) for q,r,w,n in (l.split("\t") for l in (S/"candidate-seeds.tsv").read_text().splitlines())]
    assert len(rows)==22000 and [r[0] for r in rows]==sorted((r[0] for r in rows),key=sortkey)
    target={r[1] for r in rows};names={}
    with (S/"titles.txt").open(encoding="utf8") as f:
        for i,l in enumerate(f):
            if i in target:names[i]=canon(l.rstrip("\n").split("\t",1)[1])
    accepted=[];rejected=0
    for q,i,w,n in rows:
        if i in prioridx or names[i] in forbid:rejected+=1;continue
        accepted.append((q,i,w,n))
        if len(accepted)==12000:break
    assert len(accepted)==12000
    ordered=sorted(accepted)
    with (S/"seed.tsv").open("w",encoding="ascii",newline="\n") as f:
        for q,i,w,n in ordered:f.write(f"{q}\t{i}\t{w}\t{i}\t{n}\n")
    bank=read(S/"candidate-questions.json.gz")
    save(S/"questions.json.gz",{r[0]:bank[r[0]] for r in accepted})
    all_lines={l.split()[0]:l for l in (S/"candidate.in").read_text().splitlines()}
    (S/"questions.in").write_bytes(("\n".join(all_lines[r[0]] for r in ordered)+"\n").encode())
    save(HERE/"panel.json",{"ids_in_hash_order":[r[0] for r in accepted],"n":len(accepted),"unique_first":len({r[1] for r in accepted}),
        "rejected_first":rejected,"examined":len(accepted)+rejected,"exclusion_titles":len(forbid),"address_overlap":0,
        "seed_sha256":hashfile(S/"seed.tsv"),"question_sha256":hashfile(S/"questions.json.gz")})
    print("accepted",len(accepted),rejected)

if __name__=="__main__":{"candidate":candidate,"accept":accept}[sys.argv[1]]()

