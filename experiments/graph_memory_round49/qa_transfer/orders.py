"""Choose second-document addresses using titles and one observed first snippet."""
from collections import Counter
from common import *
from rewire import Evidence,choose,tie,Tokenizer,E5,catalog,ranks,rr,place

def main():
    check();seal=get(D/"source-seal.json");assert sha(P/"visible.json.gz")==seal["visible"]
    view=get(P/"visible.json.gz");tok=Tokenizer.from_file(str(E5/"tokenizer.json"))
    records={};status=Counter()
    for q,(question,docs) in view.items():
        idx=sorted(range(len(docs)),key=lambda j:tie(q+"|musique|"+str(docs[j][0])))
        labels=[docs[j][0] for j in idx];assert len(set(labels))==len(labels)
        titles=[docs[j][1] for j in idx];reader=Evidence(idx,[[d[2]] for d in docs],tok)
        choice=choose(question,titles,reader,qid=q);first=choice["seed"];assert reader.read_ids==[first]
        seq,_,lex=catalog(question,titles);rq=ranks(lex(question));rd=ranks(lex(reader.snippet))
        order=sorted((j for j in rq if j!=first),key=lambda j:(-rr(rq[j])-rr(rd[j]),j))
        marked={int(j):pos for j,pos in choice["mentions"].items()}
        true=next((j for j in order if j in marked),order[0]);base=order[0];sham={}
        assert (true,base)==(choice["next"]["mention_expanded"],choice["next"]["expanded"])
        for s in SEEDS:
            fake,mapping,st=place(q,s,order,marked,rq,rd,list(map(len,seq)))
            dest=next((j for j in order if j in fake),base);assert (dest==base)==(true==base)
            sham[str(s)]=dict(second=labels[dest],status=st,edges={labels[j]:p for j,p in fake.items()},
                              owners={labels[a]:labels[b] for a,b in mapping.items()});status[st]+=1
        records[q]=dict(seed=labels[first],true=labels[true],lex=labels[base],base4={k:labels[choice["next"][k]] for k in ("expanded","mention_expanded","title","mention_title")},
            order=[labels[j] for j in order],edges={labels[j]:p for j,p in marked.items()},question_rank={labels[j]:rq[j] for j in rq},
            snippet_rank={labels[j]:rd[j] for j in rd},sham=sham)
    put(D/"orders.json.gz",records)
    put(D/"retrieval-seal.json",dict(orders=sha(D/"orders.json.gz"),registration=sha(D/"registration.json"),source=sha(D/"source-seal.json"),
                                    placer=sha(R47/"rewire.py"),code=sha(Path(__file__)),status=dict(status),n=len(records)))
    print(len(records),dict(status),flush=True)
if __name__=="__main__":main()
