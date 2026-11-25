"""Choose graph-source continuation addresses using only already delivered text and lengths."""
from collections import defaultdict
from pathlib import Path
import sqlite3
import sys
D=Path(__file__).resolve().parent
S=D.parents[1]/"graph_memory_round23";M=S/"marginal_open"
sys.path.insert(0,str(S/"open_transfer"))
from run import c,merged,paid_open
sys.path.insert(0,str(S/"read_causes"))
from project import read,write,sha,Tokenizer,TOK,CACHE
sys.path.insert(0,str(M))
from novelty import make_windows,lexical_order,union_intervals
def select_visible(query,fragments,sizes,tok):
    intervals=defaultdict(list)
    for e,l,s in fragments:intervals[e].append((l,l+len(s)))
    intervals={e:union_intervals(vec) for e,vec in intervals.items()}
    wins=make_windows(fragments,tok)
    def pick(order):
        for i in order:
            w=wins[i];end=next(h for l,h in intervals[w.field] if l<=w.start<h)
            if end<sizes[w.field]:
                return [w.field,w.start],[w.field,end]
        return None,None
    at,beyond=pick(lexical_order(query,wins))
    _,first_beyond=pick(range(len(wins)))
    return {"same_window":at,"right_edge":beyond,"first_edge":first_beyond}
def trim(tok,fields,r,cap):
    if r is None or cap==0:return None
    e,l,h,n=r;head=f"[{e}:{l}] ";s=head+fields[e][l:h]
    enc=tok.encode(s,add_special_tokens=False);assert n==len(enc.ids)
    cut=enc.offsets[cap][0] if n>cap else len(s)
    while True:
        cost=len(tok.encode(s[:cut],add_special_tokens=False).ids)
        if cost<=cap:break
        cut-=1
    return [e,l,l+max(0,cut-len(head)),cost]
def execute(picks,fields,tok,old):
    opens={k:(paid_open(tok,fields[p[0]],*p) if p else None) for k,p in picks.items()}
    opens["first_positive"]=old
    cap=min((opens[k][3] if opens[k] else 0) for k in ("right_edge","first_positive"))
    for k in ("right_edge","first_positive"):
        opens[k+"_matched"]=trim(tok,fields,opens[k],cap)
    return opens
def ise():
    tok=Tokenizer.from_file(str(TOK));out={}
    pvt=Path("D:/CodexResearch/x20-isetrace-fine-train/marginal-open")
    seal=read(M/"visible-seal.json")
    reg=sqlite3.connect((S/"read_causes/registry.sqlite").resolve().as_uri()+"?mode=ro&immutable=1",uri=True)
    ls=sqlite3.connect((M/"field-lengths.sqlite").resolve().as_uri()+"?mode=ro&immutable=1",uri=True)
    for i in range(8):
        p=pvt/f"visible-{i}.json.gz";assert sha(p)==seal["parts"][i]["visible"]
        name,digest,_=read(M/"opened-seal.json")["files"][i];assert sha(M/name)==digest
        old={x["q"]:x["open"]["first_positive"] for x in read(M/name)}
        by=defaultdict(list)
        for r in read(p):by[r["t"]].append(r)
        for t,rows in by.items():
            lens=dict(ls.execute("SELECT e,n FROM field_size WHERE t=?",(t,)))
            choices={r["q"]:select_visible(r["question"],r["fragments"],lens,tok) for r in rows}
            strings=read(CACHE/f"{i}-{t}.json.gz")["fields"]
            fields={e:strings[eid] for e,eid in reg.execute("SELECT e,eid FROM address WHERE t=?",(t,))}
            for r in rows:
                q=r["q"];out[q]=dict(t=t,base=[[e,l,l+len(s)] for e,l,s in r["fragments"]],actions=execute(choices[q],fields,tok,old[q]))
    reg.close();ls.close();return out
def md():
    v=c.get_views();docs={i:r[2] for i,r in enumerate(v["documents"])};tok=c.tok()
    questions={r[0]:r[2] for r in v["q"]};sizes={e:len(s) for e,s in docs.items()}
    M2=S/"marginal_transfer";p=M2/"actions.json.gz";assert sha(p)==read(M2/"forecast-seal.json")["predictions"]
    out={}
    for q,r in read(p).items():
        parts=r["base"];frags=[(e,l,docs[e][l:h]) for e,l,h in parts]
        picks=select_visible(questions[q],frags,sizes,tok);old=r["actions"]["first_positive"]
        out[q]={"base":parts,"actions":execute(picks,docs,tok,old[1] if old else None)}
    return out
def main():
    names={}
    for tag,fn in (("isetrace",ise),("multidoc",md)):
        path=D/f"actions-{tag}.json.gz";write(path,fn());names[path.name]=sha(path)
    write(D/"action-lock.json",{"files":names,"plan":sha(D/"PROTOCOL_RU.md"),"code":sha(Path(__file__))})
if __name__=="__main__":main()
