"""Select by ID and replay R32's single-read adapter. No answer, supporting label or evidence read."""
from collections import Counter
import json
import pyarrow.parquet as pq
from paths50 import *
from rewire import Evidence,choose,tie,Tokenizer,E5,catalog,ranks,rr,place
from panel import norm

def main():
    check50();P50.mkdir(exist_ok=True)
    qfile=pq.ParquetFile(RAW)
    ids=[q for b in qfile.iter_batches(columns=["_id"]) for q in b.column(0).to_pylist()]
    assert len(ids)==len(set(ids))==12576
    selected=sorted(ids,key=lambda q:hexb(("r50-2wiki-panel-v1|"+q).encode()))[:960]
    target=set(selected);view={};docs_set={}
    for batch in qfile.iter_batches(columns=["_id","question","context"]):
        for row in batch.to_pylist():
            q=row["_id"]
            if q not in target:continue
            doc=json.loads(row["context"])
            view[q]=[row["question"],[[i,t," ".join(sent)] for i,(t,sent) in enumerate(doc)]]
            docs_set[q]={hexb((t+"\0"+" ".join(sent)).encode()) for t,sent in doc}
    assert set(view)==target
    prior={};tab={};qset={q:norm(v[0]) for q,v in view.items()}
    for name,path in (("r46_musique",Path("D:/CodexResearch/x20-r46-reader-transfer/visible.json.gz")),
                      ("r49_musique",Path("D:/CodexResearch/x20-r49-qa-transfer/visible.json.gz"))):
        other=get(path);forms={norm(o[0]) for o in other.values()}
        hashes={hexb((t+"\0"+body).encode()) for _,docs in other.values() for i,t,body in docs}
        shared=set.union(*docs_set.values())&hashes
        prior[name]=dict(source_questions=len(other),same_id=len(set(other)&target),same_whole_question=sum(s in forms for s in qset.values()),
                         any_catalog_overlap=sum(bool(v&shared) for v in docs_set.values()),distinct_shared_docs=len(shared),input=sha(path))
        tab[name]=sorted(shared)
    put(P50/"seen-documents.json.gz",tab);put(P50/"visible.json.gz",view)
    put(D50/"panel.json",dict(order=selected,total=len(ids),seen=prior,visible=sha(P50/"visible.json.gz"),code=sha(Path(__file__)),registration=sha(D50/"registration.json")))
    old=get(R32/"predictions.json.gz");assert len(old)==12576 and sha(R32/"predictions.json.gz")==get(R32/"seal.json")["predictions"]
    tok=Tokenizer.from_file(str(E5/"tokenizer.json"));orders={};stats=Counter()
    for q,(question,docs) in view.items():
        idx=sorted(range(len(docs)),key=lambda i:tie(q+"|"+docs[i][1]))
        titles=[docs[i][1] for i in idx];obs=Evidence(idx,[[d[2]] for d in docs],tok)
        rec=choose(question,titles,obs,qid=q);f=rec["seed"]
        assert obs.read_ids==[f] and idx==old[q]["order"] and f==old[q]["seed"]
        seq,_,lex=catalog(question,titles);rq=ranks(lex(question));rd=ranks(lex(obs.snippet))
        order=sorted((j for j in rq if j!=f),key=lambda j:(-rr(rq[j])-rr(rd[j]),j))
        real={int(j):pos for j,pos in rec["mentions"].items()}
        truth=next((j for j in order if j in real),order[0]);base=order[0]
        modes=("expanded","mention_expanded","title","mention_title")
        assert all(rec["next"][a]==old[q]["next"][a] for a in modes)
        shams={}
        for s in SEEDS:
            fake,mapping,status=place(q,s,order,real,rq,rd,list(map(len,seq)))
            dest=next((j for j in order if j in fake),base);assert (dest==base)==(truth==base)
            shams[str(s)]=dict(second=idx[dest],status=status,edges={idx[j]:p for j,p in fake.items()},owners={idx[a]:idx[b] for a,b in mapping.items()})
            stats[status]+=1
        orders[q]=dict(seed=idx[f],true=idx[truth],lex=idx[base],base4={a:idx[rec["next"][a]] for a in modes},order=[idx[j] for j in order],
                       edges={idx[j]:p for j,p in real.items()},sham=shams,question_rank={idx[j]:rq[j] for j in rq},snippet_rank={idx[j]:rd[j] for j in rd})
    put(D50/"orders.json.gz",orders)
    put(D50/"retrieval-seal.json",dict(orders=sha(D50/"orders.json.gz"),panel=sha(D50/"panel.json"),statuses=stats,r32_replayed=len(orders),r32_questions=12576))
    print("orders",len(orders),"switch",sum(r["true"]!=r["lex"] for r in orders.values()),"statuses",stats,flush=True)
if __name__=="__main__":main()
