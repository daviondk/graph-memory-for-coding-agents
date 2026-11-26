"""Use only displayed questions and source catalogs to select a disjoint validation panel."""
import collections
import json
import pyarrow.parquet as pq
from paths_repl import *
from rewire import catalog,tie
from panel import norm

def doc_hash(title,body):
    return hexb((title+"\0"+body).encode())

def columns(path,names):
    for batch in pq.ParquetFile(path).iter_batches(batch_size=512,columns=names):
        yield from batch.to_pylist()

def prior_catalogs():
    catalogs={}
    def make(name,records):
        ids=set();questions=set();docs=set()
        for q,txt,parts in records:
            ids.add(q);questions.add(norm(txt));docs.update(doc_hash(t,b) for t,b in parts)
        catalogs[name]=(ids,questions,docs)
    make("2wiki_dev",((x["_id"],x["question"],[(t," ".join(s)) for t,s in json.loads(x["context"])])
                     for x in columns(DEV,["_id","question","context"])))
    make("hotpot_dev",((q,v["q"],[(t," ".join(s)) for t,s in zip(v["titles"],v["sentences"],strict=True)])
                       for q,v in get(HP).items()))
    for name,path in zip(["musique_train","musique_dev"],MQ,strict=True):
        with path.open(encoding="utf8") as stream:
            make(name,((x["id"],x["question"],[(p["title"],p["paragraph_text"]) for p in x["paragraphs"]])
                       for line in stream if (x:=json.loads(line))))
    return catalogs

def main():
    check()
    history=prior_catalogs()
    ids,questions,docs=(set.union(*(v[i] for v in history.values())) for i in range(3))
    order=[];total=0;old_ids=0;old_questions=0
    for row in columns(TRAIN,["_id","question"]):
        q=row["_id"];total+=1
        if q in ids:old_ids+=1;continue
        if norm(row["question"]) in questions:old_questions+=1;continue
        order.append(q)
    order.sort(key=lambda q:hexb(("r50-2wiki-unseen-v1|"+q).encode()))
    assert len(order)==len(set(order))
    selected=[];view={};stats=collections.Counter();selected_q=set();firsts=set();overlaps={}
    for start in range(0,len(order),2048):
        batch=order[start:start+2048];eligible=set(batch)
        subset={r["_id"]:r for r in columns(TRAIN,["_id","question","context"]) if r["_id"] in eligible}
        for q in batch:
            x=subset[q];question=x["question"];qn=norm(question);parts=json.loads(x["context"])
            orig=sorted(range(len(parts)),key=lambda i:tie(q+"|"+parts[i][0]))
            titles=[parts[i][0] for i in orig];scores=catalog(question,titles)[2](question)
            f=orig[max(range(len(orig)),key=scores.__getitem__)]
            hashes=[doc_hash(t," ".join(s)) for t,s in parts];fh=hashes[f]
            if qn in selected_q:stats["duplicate_selected_question"]+=1;continue
            if fh in docs:stats["first_in_prior_catalog"]+=1;continue
            if fh in firsts:stats["duplicate_selected_first"]+=1;continue
            firsts.add(fh);selected_q.add(qn);selected.append(q)
            view[q]=[question,[[i,t," ".join(s)] for i,(t,s) in enumerate(parts)]]
            overlaps[q]={"first":fh,"prior":{k:sorted(set(hashes)&v[2]) for k,v in history.items()}}
            if len(selected)==640:break
        if len(selected)==640:break
    assert len(selected)==len(firsts)==len(selected_q)==640
    assert not firsts&docs and not selected_q&questions and not set(selected)&ids
    put(P/"visible.json.gz",view)
    by_prior={k:sorted({h for v in overlaps.values() for h in v["prior"][k]}) for k in history}
    put(P/"seen-documents.json.gz",by_prior);put(D/"overlap.json.gz",overlaps)
    put(D/"panel.json",dict(order=selected,source_n=total,excluded_id=old_ids,excluded_question=old_questions,
        sorted_candidates=len(order),examined=len(selected)+sum(stats.values()),rejected=stats,
        history={k:dict(ids=len(v[0]),questions=len(v[1]),documents=len(v[2]),
                   selected_catalogs_sharing=sum(bool(o["prior"][k]) for o in overlaps.values()),shared_documents=len(by_prior[k])) for k,v in history.items()},
        pooled_catalogs_sharing=sum(any(o["prior"].values()) for o in overlaps.values()),
        zero_prior_ids=True,zero_prior_questions=True,zero_prior_first=True,unique_first=len(firsts),
        visible=sha(P/"visible.json.gz"),overlap=sha(D/"overlap.json.gz"),registration=sha(D/"registration.json"),code=sha(Path(__file__))))
    print("Selected",len(selected),"from",total,"rejected",stats,flush=True)
if __name__=="__main__":main()
