"""Stage 1: rewire observed mentions using only the original one-read interface and title catalog."""
from collections import Counter
from base47 import *
sys.path.insert(0,str(W/'graph_memory_round32/observed_transfer'))
from transfer import Evidence,choose,tie,Tokenizer,E5,catalog,ranks
from predict import rr

def h(q,seed,stage,i):return hexb(f'r47|{q}|{seed}|{stage}|{i}'.encode())

def place(q,seed,order,marked,rankq,rankdoc,length):
    rank={j:i for i,j in enumerate(order)};baseline=order[0]
    if not marked:return {},{},'no_edge'
    best=min(marked,key=rank.get);n=len(marked);switched=best!=baseline
    if not switched:
        chosen=best;status='preserve_leader'
    else:
        loose=[j for j in order if j not in marked and j!=baseline and len(order)-rank[j]-1>=n-1]
        strict=[j for j in loose if sum(k not in marked for k in order[rank[j]+1:])>=n-1]
        if not loose:return marked,{j:j for j in marked},'infeasible'
        pool=strict or loose
        near=sorted(pool,key=lambda j:(abs(rank[j]-rank[best]),abs(rankq[j]-rankq[best]),
                    abs(rankdoc[j]-rankdoc[best]),abs(length[j]-length[best]),j))
        chosen=min(near[:3],key=lambda j:h(q,seed,'top',j))
        status='disjoint' if strict else 'partial'
    remaining=sorted(order[rank[chosen]+1:],key=lambda j:(j in marked,h(q,seed,'other-target',j)))[:n-1]
    owners=sorted(set(marked)-{best},key=lambda j:h(q,seed,'other-owner',j))
    mapping={best:chosen,**dict(zip(owners,remaining,strict=True))}
    new={dst:marked[src] for src,dst in mapping.items()}
    assert len(new)==len(marked) and sorted(map(tuple,new.values()))==sorted(map(tuple,marked.values()))
    assert min(new,key=rank.get)==chosen and (chosen!=baseline)==switched
    if switched:assert chosen not in marked
    return new,mapping,status

def main():
    check();view=get(PRIVATE/'visible.json.gz');panel=signed(R46,'panel.json');old=signed(R46,'contexts.json.gz')
    assert sha(PRIVATE/'visible.json.gz')==panel['observations']
    tok=Tokenizer.from_file(str(E5/'tokenizer.json'));out={};statuses=Counter()
    for q in panel['order']:
        question,docs=view[q]
        ids=sorted(range(len(docs)),key=lambda i:tie(q+'|musique|'+str(docs[i][0])))
        local=[docs[i][0] for i in ids];titles=[docs[i][1] for i in ids]
        reader=Evidence(ids,[[p[2]] for p in docs],tok)
        ref=choose(question,titles,reader,qid=q);first=ref['seed'];assert reader.read_ids==[first]
        seq,_,lex=catalog(question,titles);rq=ranks(lex(question));rd=ranks(lex(reader.snippet))
        order=sorted((j for j in rq if j!=first),key=lambda j:(-rr(rq[j])-rr(rd[j]),j))
        marked={int(j):pos for j,pos in ref['mentions'].items()}
        true=next((j for j in order if j in marked),order[0]);base=order[0]
        assert ref['next']['expanded']==base and ref['next']['mention_expanded']==true
        assert [local[first],local[true],local[base]]==[old[q]['seed'],old[q]['prompt']['mention_expanded'][0],old[q]['prompt']['expanded'][0]]
        sham={}
        for s in SEEDS:
            fake,mapping,status=place(q,s,order,marked,rq,rd,list(map(len,seq)))
            target=next((j for j in order if j in fake),base)
            assert (target==base)==(true==base)
            sham[str(s)]=dict(second=local[target],status=status,edges={local[j]:p for j,p in fake.items()},
                              owners={local[a]:local[b] for a,b in mapping.items()})
            statuses[status]+=1
        out[q]=dict(seed=local[first],true=local[true],lex=local[base],edges={local[j]:pos for j,pos in marked.items()},
                    order=[local[j] for j in order],question_rank={local[j]:rq[j] for j in rq},
                    snippet_rank={local[j]:rd[j] for j in rd},sham=sham)
    put(D/'orders.json.gz',out);put(D/'retrieval-seal.json',dict(orders=sha(D/'orders.json.gz'),
        code=sha(D/'rewire.py'),registration=sha(D/'registration.json'),statuses=statuses))
    print(statuses)

if __name__=='__main__':main()
