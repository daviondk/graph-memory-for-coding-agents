from collections import defaultdict
from pathlib import Path
import hashlib,sqlite3,sys
from shared25 import *
from direction import token,choose,execute
sys.path.insert(0,str(F))
from routes import c,Tokenizer,TOK,CACHE,merged
from novelty import Window,lexical_order
M=R/"marginal_open";MT=R/"marginal_transfer"
def ro(p):return sqlite3.connect(p.as_uri()+"?mode=ro&immutable=1",uri=True)
def squad_rows():
    data=read(SQUAD)["data"];rows=[]
    for article in data:
        fields=[];offsets=[];base=0
        for para in article["paragraphs"]:
            offsets.append(base);text=para["context"];fields.append(text);base+=len(text)+2
        article_text="\n\n".join(fields);qs=[]
        for i,para in enumerate(article["paragraphs"]):
            for qa in para["qas"]:qs.append((qa["id"],qa["question"]))
        selected=sorted(qs,key=lambda qa:hashlib.sha256(("direction-v1/"+qa[0]).encode()).digest())[:12]
        rows.append((article["title"],article_text,selected))
    return rows
def squad_frags(tok,text,questions):
    offsets=token(tok,text).offsets
    wins=[]
    for j in range(0,len(offsets),64):
        start=offsets[j][0] if j else 0;end=offsets[j+64][0] if j+64<len(offsets) else len(text)
        wins.append(Window(0,start,end,text[start:end],min(64,len(offsets)-j)))
    prices=[len(token(tok,f"[0:{v.start}] "+v.text).ids) for v in wins]
    for q,query in questions:
        order=lexical_order(query,wins);sel=[];fee=0
        for j in order:
            if fee+prices[j]<=2048:sel.append(wins[j]);fee+=prices[j]
        wire="\n".join(f"[0:{z.start}] "+z.text for z in sel)
        assert fee==len(token(tok,wire).ids)<=2048
        coords=merged([(0,z.start,z.end) for z in sel]);frags=[(e,l,text[l:h]) for e,l,h in coords]
        yield q,query,frags,fee
def ise_visible():
    seal=read(M/"visible-seal.json");conn=ro(M/"field-lengths.sqlite");source=Path("D:/CodexResearch/x20-isetrace-fine-train/marginal-open")
    for i,meta in enumerate(seal["parts"]):
        p=source/f"visible-{i}.json.gz";assert sha(p)==meta["visible"]
        for row in read(p):
            t=row["t"];v=row["fragments"]
            sizes={e:conn.execute("select n from field_size where t=? and e=?",(t,e)).fetchone()[0] for e in {z[0] for z in v}}
            yield row["q"],t,row["question"],v,sizes,row["paid"],i
    conn.close()
def md_visible():
    view=c.get_views();docs=view["documents"];qs={q:(t,query) for q,t,query in view["q"]}
    p=MT/"actions.json.gz";assert sha(p)==read(MT/"forecast-seal.json")["predictions"]
    for q,r in read(p).items():
        t,query=qs[q];frags=[(e,l,docs[e][2][l:h]) for e,l,h in r["base"]]
        yield q,t,query,frags,{e:len(docs[e][2]) for e,l,txt in frags},r["source_tokens"],None
def select(name):
    check();tok=c.tok() if name=="mdd" else Tokenizer.from_file(str(TOK));out={}
    if name=="squad":
        def ready():
            for t,text,questions in squad_rows():
                for q,x,f,fee in squad_frags(tok,text,questions):yield q,t,x,f,{0:len(text)},fee,None
        stream=ready()
    else:stream=md_visible() if name=="mdd" else ise_visible()
    for q,t,query,frags,sizes,fee,i in stream:
        cut=choose(query,frags,sizes,tok)
        assert q not in out and fee<=2048
        out[q]={"t":t,"shard":i,"initial_tokens":fee,"base":[[e,l,l+len(txt)] for e,l,txt in frags],"cut":cut}
    if name!="squad":assert len(out)==(661 if name=="mdd" else 2000)
    h=save(D/f"{name}-choices.json.gz",out)
    save(D/f"{name}-choice-seal.json",{"actions":h,"plan":sha(D/"plan.json"),"source":sha(SQUAD) if name=="squad" else None,"selector":sha(D/"direction.py"),"adapter":sha(Path(__file__))})
def run(name):
    p=D/f"{name}-choices.json.gz";assert sha(p)==read(D/f"{name}-choice-seal.json")["actions"]
    picks=read(p);results={};tok=c.tok() if name=="mdd" else Tokenizer.from_file(str(TOK))
    if name=="ise":
        reg=ro(R/"read_causes/registry.sqlite");group=defaultdict(list)
        for q,r in picks.items():group[r["shard"],r["t"]].append((q,r))
        for (i,t),records in group.items():
            src=read(CACHE/f"{i}-{t}.json.gz")["fields"];addr=dict(reg.execute("select e,eid from address where t=?",(t,)))
            for q,r in records:
                cut=r["cut"];results[q]=execute(tok,cut,src[addr[cut["e"]]] if cut else "")
        reg.close()
    else:
        by=({t:text for t,text,_ in squad_rows()} if name=="squad" else {i:d[2] for i,d in enumerate(c.get_views()["documents"])})
        for q,r in picks.items():
            cut=r["cut"];text=by[r["t"] if name=="squad" else cut["e"]] if cut else ""
            results[q]=execute(tok,cut,text)
    if name in ("ise","mdd"):
        old=F/("actions-isetrace.json.gz" if name=="ise" else "actions-multidoc.json.gz");assert sha(old)==read(F/"action-lock.json")["files"][old.name]
        for q,r in read(old).items():
            right=results[q]["arms"]["right"]
            assert (right[0][:4] if right else None)==r["actions"]["right_edge"]
    h=save(D/f"{name}-opened.json.gz",results);save(D/f"{name}-open-seal.json",{"actions":h,"choices":sha(D/f"{name}-choice-seal.json"),"code":sha(D/"direction.py"),"r24_identical":0 if name=="squad" else len(results)})
if __name__=="__main__":globals()[sys.argv[1]](sys.argv[2])
