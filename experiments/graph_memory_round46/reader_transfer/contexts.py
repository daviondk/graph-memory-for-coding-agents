"""Form all matched Qwen token sequences before any reader answers."""
from io46 import *
from engine import enc
import sys
import struct
sys.path.insert(0,str(W/'graph_memory_round32/observed_transfer'))
from transfer import Evidence,choose,tie,Tokenizer,E5

def key(tokens):
    return hexb(struct.pack('<'+'I'*len(tokens),*tokens))
SYS='Use the supplied documents to answer the question. Return only the shortest correct answer, with no explanation. If the documents do not establish the answer, return UNKNOWN.'
BASESYS='Answer the question from your knowledge. Return only the shortest correct answer, with no explanation. If you do not know, return UNKNOWN.'
def marker(system):return enc('<|im_start|>system\n'+system+'<|im_end|>\n<|im_start|>user\nQuestion: ',True)
def seal():
    plan=get(D/'plan.json');panel=get(D/'panel.json');assert sha(PRIVATE/'visible.json.gz')==panel['observations']
    assert sha(W/'graph_memory_round31/observed_links/predict.py')==plan['chooser']
    view=get(PRIVATE/'visible.json.gz');tok=Tokenizer.from_file(str(E5/'tokenizer.json'))
    prior=set(panel['seen_dev']);rows={};prompts={}
    end=enc('<|im_end|>\n<|im_start|>assistant\n',True);a1=enc('\nDocument 1:\n');a2=enc('\nDocument 2:\n')
    for j,q in enumerate(panel['order']):
        query,docs=view[q];idx=sorted(range(len(docs)),key=lambda i:tie(q+'|musique|'+str(docs[i][0])))
        titles=[docs[i][1] for i in idx];reader=Evidence(idx,[[x[2]] for x in docs],tok)
        choice=choose(query,titles,reader,qid=q);assert reader.read_ids==[choice['seed']]
        seed=docs[idx[choice['seed']]];second={a:docs[idx[choice['next'][a]]] for a in ARMS}
        def doc_parts(doc):return enc(doc[1]+'\n'+doc[2])[:192]
        seq1=doc_parts(seed);seconds={a:doc_parts(v) for a,v in second.items()};n=min(map(len,seconds.values()))
        args={};query_tokens=enc(query)[:80];common=marker(SYS)+query_tokens+a1+seq1+a2
        for a in ARMS:
            seq=common+seconds[a][:n]+end;k=key(seq)
            prior_seq=prompts.setdefault(k,seq);assert seq==prior_seq
            args[a]=[second[a][0],k,len(seq)]
        assert len({v[-1] for v in args.values()})==1
        if j<min(len(view),256):
            seq=marker(BASESYS)+query_tokens+end;k=key(seq);assert prompts.setdefault(k,seq)==seq
            args['closed']=[None,k,len(seq)]
        cluster=hexb((seed[1]+'\0'+seed[2]).encode())
        rows[q]=dict(seed=seed[0],cluster=cluster,seen_doc=cluster in prior,prompt=args,
            first_tokens=len(seq1),second_tokens=n,observed_wp=choice['tokens'],link_count=len(choice['mentions']))
        if (j+1)%256==0:print('prepared',j+1,flush=True)
    put(D/'contexts.json.gz',rows);put(D/'prompts.json.gz',prompts)
    put(D/'input-seal.json',dict(plan=sha(D/'plan.json'),panel=sha(D/'panel.json'),contexts=sha(D/'contexts.json.gz'),
        prompts=sha(D/'prompts.json.gz'),builder=sha(D/'contexts.py'),n=len(rows),unique=len(prompts),
        logical=sum(len(r['prompt']) for r in rows.values())))
    print('frozen contexts',len(rows),len(prompts),flush=True)

if __name__=='__main__':seal()
