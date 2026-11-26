"""Export only question, first observed snippet and unexpanded catalog titles to the address selector."""
from paths_a import *
from rewire import Evidence,E5,Tokenizer,tie

def main():
    check();previous=get(D/"lex-retrieval-seal.json")
    assert sha(D/"lex-orders.json.gz")==previous["orders"]
    order=get(D/"lex-orders.json.gz");panel=get(D/"panel.json")
    view=get(P/"visible.json.gz");assert sha(P/"visible.json.gz")==panel["visible"]
    tok=Tokenizer.from_file(str(E5/"tokenizer.json"));export={};receipts={}
    for q in panel["order"]:
        question,docs=view[q];r=order[q];first=r["seed"]
        reader=Evidence([first],[[None] if i!=first else [body] for i,_,body in docs],tok)
        snippet,observed=reader.open(0);assert reader.read_ids==[0]
        titles=[(i,title) for i,title,_ in docs if i!=first]
        titles.sort(key=lambda v:(tie(q+"|"+v[1]),v[0]))
        export[q]=[question,snippet,titles]
        receipts[q]=dict(first=first,observed=observed,snippet=hexb(snippet.encode()),question=hexb(question.encode()),
            titles={i:hexb(t.encode()) for i,t in titles},tie=[i for i,t in titles])
    put(P/"catalog-input.json.gz",export)
    put(D/"catalog-receipts.json.gz",receipts)
    put(D/"projection-seal.json",dict(source=sha(P/"visible.json.gz"),visible=sha(P/"catalog-input.json.gz"),
        receipts=sha(D/"catalog-receipts.json.gz"),panel=sha(D/"panel.json"),code=sha(Path(__file__))))
if __name__=="__main__":main()
