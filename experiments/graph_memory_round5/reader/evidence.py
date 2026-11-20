"""Read a short usage witness from links among code fragments that are already accessible."""
import re, math
from functools import lru_cache
from pathlib import Path
import sys
D=Path(__file__).resolve().parent
R4=D.parents[1]/"graph_memory_round4"
sys.path.insert(0,str(R4/"repo"));sys.path.insert(0,str(D.parents[1]/"graph_memory_round3/repo/lib"))
from memory import record,pp,wt,cos
from tokenizers import Tokenizer
TOKENFILE=D.parents[1]/"memory_session5/live/tokenizer.json"
tok=Tokenizer.from_file(str(TOKENFILE))
def trim(text,cap,tail=False):
    ids=tok.encode(text,add_special_tokens=False).ids
    if len(ids)<=cap:return text,len(ids)
    ix=ids[-cap:] if tail else ids[:cap]
    while ix:
        t=tok.decode(ix,skip_special_tokens=False);n=len(tok.encode(t,add_special_tokens=False).ids)
        if n<=cap:return t,n
        ix=ix[1:] if tail else ix[:-1]
    return "",0
def query(ctx):
    ll=ctx.splitlines()
    return pp("\n".join(ll[-3:])),pp("\n".join(ll[-10:])),pp("\n".join(ll[-30:]))
def proximity(q,p):
    return .55*cos(q[0],p)+.3*cos(q[1],p)+.15*cos(q[2],p)
def ignored(line):
    return line.lstrip().startswith(("//","/*","*","import ","package "))
def local_view(q,text,cap):
    if len(tok.encode(text,add_special_tokens=False).ids)<=cap:return trim(text,cap)
    ls=text.splitlines(); root=record(text)["root"]
    header=next((line.strip() for line in ls if re.search(r"\b(?:class|interface|enum|record)\s+",line) and not ignored(line)),"")
    cand=[]
    for j,line in enumerate(ls):
        if not line.strip() or ignored(line):continue
        words=pp(line); local=pp("\n".join(ls[max(0,j-1):j+2]))
        score=.7*proximity(q,words)+.3*proximity(q,local)
        cand.append((score,-j))
    if not cand or max(cand)[0]==0:return trim(text,cap)
    j=-max(cand)[1];start=max(0,j-1)
    window="\n".join(ls[start:j+10])
    if header and header not in window:window=trim(header,min(30,cap//3))[0]+"\n"+window
    return trim(window,cap)
def edge_view(q,texts,rank,cap=256):
    dest=rank[0];root=record(texts[dest])["root"];candidates=[]
    if root:
        token=re.compile(r"(?<![A-Za-z0-9_$])"+re.escape(root)+r"(?![A-Za-z0-9_$])",re.I)
        for order,ix in enumerate(rank[1:],1):
            lines=texts[ix].splitlines()
            for j,line in enumerate(lines):
                if ignored(line) or not token.search(line):continue
                if re.search(r"\b(?:class|interface|enum|record)\s+"+re.escape(root)+r"\b",line,re.I):continue
                previous=pp("\n".join(lines[max(0,j-3):j]))
                nearby=proximity(q,previous)+.3*proximity(q,pp(line))
                candidates.append((nearby,-order,-j,ix))
    if not candidates:return local_view(q,texts[dest],cap),None
    _,_,mj,source=max(candidates);j=-mj;lines=texts[source].splitlines()
    # Preserve the line that actually uses the chosen declaration when the preceding line is long.
    use=lines[j].strip()+"\n"+"\n".join(lines[j+1:j+3])
    witness=trim(use,100)[0]
    decl=local_view(q,texts[dest],145)[0]
    combined=trim(decl+"\n// Usage in another fragment\n"+witness,cap)
    return combined,{"source":source,"line":j,"root":root}
def make(ctx,texts,rank):
    q=query(ctx);chosen=texts[rank[0]]
    edge,event=edge_view(q,texts,rank)
    top=rank[:4];per=(256-3*(len(top)-1))//len(top)
    join=lambda vals:trim("\n\n".join(vals),256)
    return {"empty":("(no external fragment)",0),"head":trim(chosen,256),"local":local_view(q,chosen,256),"edge":edge,
            "four_head":join([trim(texts[i],per)[0] for i in top]),"portfolio":join([local_view(q,texts[i],per)[0] for i in top])},event

