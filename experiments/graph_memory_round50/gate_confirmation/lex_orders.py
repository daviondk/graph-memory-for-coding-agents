from collections import Counter
from paths_a import *
from rewire import Evidence,choose,tie,Tokenizer,E5,catalog,ranks,rr,place
from common import SEEDS

def main():
    check();panel=get(D/"panel.json");assert sha(P/"visible.json.gz")==panel["visible"]
    view=get(P/"visible.json.gz");overlap=get(D/"overlap.json.gz")
    tok=Tokenizer.from_file(str(E5/"tokenizer.json"));orders={};stats=Counter()
    for q,(question,docs) in view.items():
        idx=sorted(range(len(docs)),key=lambda i:tie(q+"|"+docs[i][1]))
        titles=[docs[i][1] for i in idx];obs=Evidence(idx,[[d[2]] for d in docs],tok)
        rec=choose(question,titles,obs,qid=q);f=rec["seed"]
        assert obs.read_ids==[f] and hexb("\0".join(docs[idx[f]][1:]).encode())==overlap[q]["first"]
        seq,_,lex=catalog(question,titles);rq=ranks(lex(question));rd=ranks(lex(obs.snippet))
        order=sorted((j for j in rq if j!=f),key=lambda j:(-rr(rq[j])-rr(rd[j]),j))
        real={int(j):pos for j,pos in rec["mentions"].items()}
        truth=next((j for j in order if j in real),order[0]);base=order[0]
        assert truth==rec["next"]["mention_expanded"] and base==rec["next"]["expanded"]
        shams={};budget=[]
        for s in SEEDS:
            fake,mapping,status=place(q,s,order,real,rq,rd,list(map(len,seq)))
            dest=next((j for j in order if j in fake),base);assert (dest==base)==(truth==base)
            budget.append(idx[dest])
            if s==47011:
                shams[str(s)]=dict(second=idx[dest],status=status,edges={idx[j]:p for j,p in fake.items()},owners={idx[a]:idx[b] for a,b in mapping.items()})
                stats[status]+=1
        modes=("expanded","mention_expanded","title","mention_title")
        orders[q]=dict(seed=idx[f],true=idx[truth],lex=idx[base],base4={a:idx[rec["next"][a]] for a in modes},
              order=[idx[j] for j in order],edges={idx[j]:p for j,p in real.items()},sham=shams,budget_all5=budget,
              question_rank={idx[j]:rq[j] for j in rq},snippet_rank={idx[j]:rd[j] for j in rd})
    put(D/"lex-orders.json.gz",orders);put(D/"lex-retrieval-seal.json",dict(orders=sha(D/"lex-orders.json.gz"),panel=sha(D/"panel.json"),statuses=stats,code=sha(Path(__file__))))
    print("Orders",len(orders),stats,flush=True)
if __name__=="__main__":main()
