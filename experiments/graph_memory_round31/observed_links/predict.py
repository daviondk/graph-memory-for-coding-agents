"""Choose a second source using only its catalog title and one logged text read."""
from collections import Counter
from math import log
from pathlib import Path
import hashlib,sys
HERE=Path(__file__).resolve().parent;PAIR=HERE.parent/"support_pairs"
sys.path.insert(0,str(PAIR))
from prepare import PRIVATE,get,put,sha
from rank import words
R29=HERE.parents[1]/"graph_memory_round29/stale_reader";sys.path.insert(0,str(R29))
from retrieve29 import e5_session,encode,E5,Tokenizer,np

def tie(s):return hashlib.sha256(s.encode()).digest()
def catalog(q,titles):
    tokens=[words(t) for t in titles];df=Counter(t for v in tokens for t in set(v))
    idf={k:log(1+(len(titles)-v+.5)/(v+.5)) for k,v in df.items()}
    def score(text):
        # BM25 over the title catalog, with one query contribution per distinct token.
        bag=set(words(text));mean=sum(map(len,tokens))/len(tokens) or 1
        return [sum(idf[k]*c*2.2/(c+1.2*(.25+.75*len(row)/mean)) for k,c in Counter(row).items() if k in bag) for row in tokens]
    return tokens,idf,score
def ranks(values):
    order=sorted(range(len(values)),key=lambda i:(-values[i],i));return {i:j for j,i in enumerate(order)}
def rr(position):return 1/(10+position)
class ReadOne:
    def __init__(self,corpus_order,documents,tok):
        self.order=corpus_order;self.documents=documents;self.tok=tok;self.read_ids=[]
    def open(self,j):
        assert not self.read_ids
        self.read_ids.append(j);body=" ".join(self.documents[self.order[j]])
        item=self.tok.encode(body,add_special_tokens=False);offsets=item.offsets[:192]
        return body[:offsets[-1][1]] if offsets else "",len(offsets)

def choose(question,titles,observed,*,dense=None,qid):
    title_tokens,idf,lex=catalog(question,titles);query=lex(question)
    dense_titles=None
    if dense:
        tok,model=dense
        embeddings=encode(["query: "+question]+["passage: "+t for t in titles],tok,model)
        dense_titles=embeddings[1:];query=(dense_titles@embeddings[0]).tolist()
    prior=ranks(query);seed=min(prior,key=prior.get);snippet,cost=observed.open(seed)
    extension=lex(snippet)
    if dense:
        expanded=encode(["query: "+question+" "+snippet],tok,model)[0]
        extension=(dense_titles@expanded).tolist()
    after=ranks(extension)
    hybrid={j:rr(prior[j])+rr(after[j]) for j in prior};candidates=[j for j in prior if j!=seed]
    text_tokens=words(snippet);query_words=set(words(question))-set(title_tokens[seed])
    query_words={x for x in query_words if len(x)>2}
    mentions={};near={}
    for j in candidates:
        seq=title_tokens[j]
        positions=[i for i in range(len(text_tokens)-len(seq)+1) if seq and sum(map(len,seq))>=3 and text_tokens[i:i+len(seq)]==seq]
        if positions:mentions[j]=positions
        near[j]=max((sum(idf.get(t,1.0) for t in sorted(query_words & set(text_tokens[max(0,i-12):i+len(seq)+12]))) for i in positions),default=0)
    permutation=sorted(candidates,key=lambda j:tie(qid+"|shuffle-links|"+str(j)))
    fake={permutation[i] for i,j in enumerate(candidates) if j in mentions}
    def best(fn):return min(candidates,key=lambda j:(*fn(j),j))
    picks={"title":best(lambda j:(prior[j],)),"expanded":best(lambda j:(-hybrid[j],)),
           "mention_title":best(lambda j:(j not in mentions,prior[j])),
           "mention_expanded":best(lambda j:(j not in mentions,-hybrid[j])),
           "mention_local":best(lambda j:(j not in mentions,-near[j],-hybrid[j])),
           "shuffled":best(lambda j:(j not in fake,-hybrid[j]))}
    assert observed.read_ids==[seed] and all(v!=seed for v in picks.values())
    return {"seed":seed,"next":picks,"mentions":{str(j):v for j,v in mentions.items()},"tokens":cost,"seed_bytes":len(snippet.encode())}
def main():
    source=get(PAIR/"source.json");assert sha(PRIVATE/"blind.json.gz")==source["observations"]
    cases=get(PRIVATE/"blind.json.gz");panel=sorted(cases,key=lambda q:tie("r31-observed-dense/"+q))[:512]
    plan={"panel":panel,"source":sha(PAIR/"source.json"),"code":sha(Path(__file__)),"protocol":sha(HERE/"PROTOCOL_RU.md"),
          "tokenizer":sha(E5/"tokenizer.json"),"model":sha(E5/"model_qint8_avx512_vnni.onnx"),"encoder":sha(R29/"retrieve29.py")}
    put(HERE/"plan.json",plan);tok=Tokenizer.from_file(str(E5/"tokenizer.json"));engine=e5_session()
    storage=PRIVATE/("observed-"+sha(HERE/"plan.json"));storage.mkdir(exist_ok=True)
    forecasts={};dense_panel=set(panel)
    for k,(q,item) in enumerate(sorted(cases.items())):
        chk=storage/(q+".json")
        if not chk.exists():
            order=sorted(range(len(item["titles"])),key=lambda i:tie(q+"|"+item["titles"][i]))
            titles=[item["titles"][i] for i in order]
            def fetch():return ReadOne(order,item["sentences"],tok)
            row={"catalog":order,"sparse":choose(item["q"],titles,fetch(),qid=q)}
            if q in dense_panel:row["dense"]=choose(item["q"],titles,fetch(),qid=q,dense=(tok,engine))
            put(chk,row)
        forecasts[q]=get(chk)
        if (k+1)%1000==0:print(k+1,flush=True)
    put(HERE/"forecasts.json.gz",forecasts);put(HERE/"seal.json",{"forecasts":sha(HERE/"forecasts.json.gz"),"plan":sha(HERE/"plan.json")})
if __name__=="__main__":main()
