"""Export only question, first observed snippet and unexpanded catalog titles to the address selector."""
from paths_sem import *
from rewire import Evidence,E5,Tokenizer,tie

def main():
    check();previous=get(REP/"manifest.json")["files"]
    assert sha(REP/"orders.json.gz")==previous["orders.json.gz"]
    order=get(REP/"orders.json.gz");panel=get(REP/"panel.json")
    view=get(OLD/"visible.json.gz");assert sha(OLD/"visible.json.gz")==panel["visible"]
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
    put(D/"projection-seal.json",dict(source=sha(OLD/"visible.json.gz"),visible=sha(P/"catalog-input.json.gz"),
        receipts=sha(D/"catalog-receipts.json.gz"),panel=sha(REP/"panel.json"),code=sha(Path(__file__))))
if __name__=="__main__":main()
