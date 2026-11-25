"""Reads only pre-change texts, observations and issue descriptions. No future event or edit labels."""
import ast, bisect, io, math, re, struct, sys, tokenize, warnings
from collections import Counter
from functools import lru_cache
from time import perf_counter
from tokenizers import Tokenizer
from common import *
WORDS=re.compile(r"[A-Za-z_][A-Za-z0-9_]*|[0-9]+")
ARMS=("right","left","both","line_neighbors","scope_neighbors","lexical")
def terms(s):return WORDS.findall(s.casefold())
def tokenids(t,s):return t.encode(s,add_special_tokens=False).ids
def source(key):
    raw=(P/"files"/key).read_bytes()
    enc=tokenize.detect_encoding(io.BytesIO(raw).readline)[0]
    return raw.decode(enc).replace("\r\n","\n").replace("\r","\n")
def index_file(tok,txt):
    begin=perf_counter()
    lines=txt.split("\n");lens=[0];ids=[]
    for line in lines:
        ids+=tokenids(tok,line);lens.append(len(ids))
    assert ids==tokenids(tok,txt)
    tindex=perf_counter()-begin;begin=perf_counter()
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            tree=ast.parse(txt)
        nodes=[(min([o.lineno]+[x.lineno for x in o.decorator_list]),o.end_lineno) for o in ast.walk(tree) if isinstance(o,(ast.ClassDef,ast.FunctionDef,ast.AsyncFunctionDef)) and o.end_lineno]
        ast_valid=True
    except (SyntaxError,ValueError):
        nodes=[];ast_valid=False
    return lines,lens,ids,sorted(nodes,key=lambda x:(x[1]-x[0],x)),(tindex,perf_counter()-begin,ast_valid)
def lexical_blocks(lines,query,lens):
    seq=[]
    for i in range(0,len(lines),16):
        h=min(i+16,len(lines))
        if lens[h]>lens[i]:seq.append((i+1,h,Counter(terms("\n".join(lines[i:h])))))
    if not seq:return []
    n=len(seq);q=set(terms(query));sizes=[sum(f.values()) for _,_,f in seq];avg=sum(sizes)/n or 1
    df=Counter(w for _,_,d in seq for w in q.intersection(d))
    def score(k):
        f=seq[k][2]
        return sum(math.log1p((n-df[w]+.5)/(df[w]+.5))*2.2*f[w]/(f[w]+1.2*(.25+.75*sizes[k]/avg)) for w in sorted(q.intersection(f)))
    return [seq[k][:2] for k in sorted(range(n),key=lambda k:(-score(k),k))]
def policies(tok,query,lo,hi,info,next_block):
    lines,E,ids,nodes,_=info;L,H=E[lo-1],E[hi];N=len(ids)
    def wire_head(anchor):return tokenids(tok,f"[0:{anchor}]")
    hl,hr=len(wire_head(L)),len(wire_head(H))
    def segment(left,a,b,at):
        if a>=b:return []
        nh=len(wire_head(at));return [[a,b,at,nh,nh+b-a]]
    def single(side,cap):
        if side=="L":return segment(1,max(0,L-max(0,cap-hl)),L,L)
        return segment(0,H,min(N,H+max(0,cap-hr)),H)
    def bounds(i):
        for l,h in nodes:
            if l<=i<=h:return l,h
        return 1,len(lines)
    sb_l=bounds(lo)[0];sb_h=bounds(hi)[1]
    q=set(terms(query))
    def matched(v):return len(q.intersection(terms(tok.decode(v,skip_special_tokens=False))))
    prefer_left=matched(ids[L:min(H,L+32)])>matched(ids[max(L,H-32):H])
    def balanced_lines(cap,scope):
        left,right=lo-1,hi+1;lc=rc=0;use_left=True
        lower=sb_l if scope and sb_l<lo else 1
        upper=sb_h if scope and sb_h>hi else len(lines)
        while left>=lower or right<=upper:
            success=False
            for side in (use_left,not use_left):
                if side and left>=lower:
                    dl=E[left]-E[left-1]
                    if lc+rc+dl+(hl if lc+dl else 0)+(hr if rc else 0)<=cap:
                        lc+=dl;left-=1;success=True;use_left=False;break
                elif not side and right<=upper:
                    dr=E[right]-E[right-1]
                    if lc+rc+dr+(hr if rc+dr else 0)+(hl if lc else 0)<=cap:
                        rc+=dr;right+=1;success=True;use_left=True;break
            if not success:break
        return segment(1,L-lc,L,L)+segment(0,H,H+rc,H)
    def make(arm,cap):
        if arm=="right":return single("R",cap)
        if arm=="left":return single("L",cap)
        if arm=="both":
            if L==0:return single("R",cap)
            if H==N:return single("L",cap)
            return single("L",cap//2)+single("R",cap-cap//2)
        if arm=="lexical":return single("L" if L and (prefer_left or H==N) else "R",cap)
        if arm=="index":
            if not next_block:return []
            a=E[next_block[0]-1];nh=len(wire_head(a))
            return segment(0,a,min(N,a+max(0,cap-nh)),a)
        if arm in ("line_neighbors","scope_neighbors"):return balanced_lines(cap,arm=="scope_neighbors")
        raise ValueError(arm)
    def checked(m,cap):
        charge=sum(z[4] for z in m);wire=[]
        for a,b,z,nh,n in m:
            assert 0<=a<b<=N and (z==a or z==b)
            head=wire_head(z);assert len(head)==nh
            wire+=head+ids[a:b]
        assert len(wire)==charge<=cap
        wire_sha=hashlib.sha256(struct.pack("<"+"I"*len(wire),*wire)).hexdigest()
        return dict(windows=m,cost=charge,wire_sha=wire_sha)
    arms={k:checked(make(k,256),256) for k in ARMS+(("index",) if next_block is not None else ())}
    cap=min(arms[k]["cost"] for k in ("right","both"))
    while True:
        eq={k:checked(make(k,cap),cap) for k in ("both","right")}
        a,b=[v["cost"] for v in eq.values()]
        if a==b:break
        assert min(a,b)<cap;cap=min(a,b)
    return dict(lines=[lo,hi],visible=[L,H],arms=arms,equal=eq)
def main(panel):
    inputs();pref="loc-" if panel=="loc" else ""
    schema=read(D/(pref+"dataset.json"));obs=read(D/(pref+"observations.json.gz"))
    quest=read(P/(pref+"questions.json"));maps=read(P/(pref+"source-map.json"))
    assert sha(P/(pref+"source-map.json"))==schema["source_sha"]
    assert sha(P/(pref+"questions.json"))==schema["issues_sha"]
    assert sha(D/(pref+"observations.json.gz"))==schema["observations_sha"]
    tok=Tokenizer.from_file(str(T));tok.no_truncation();tok.no_padding()
    outputs=[];indexes={};missing=[];timing={}
    for row in obs:
        q=row["issue"];key=row["file"]
        if key not in indexes:
            m=next(m for m in maps if m[0]==key)
            if not m[4]:
                missing.append([row["id"],"source_absent"]);continue
            assert sha(P/"files"/key)==m[4]
            txt=source(key);info=index_file(tok,txt);indexes[key]=info
            timing[key]={"line_token_seconds":info[4][0],"ast_seconds":info[4][1],"ast_valid":info[4][2],"source_bytes":m[5],"wordpieces":len(info[2]),"ast_scopes":len(info[3])}
        info=indexes[key];next_block=None
        if panel=="loc":
            begin=perf_counter();blocks=lexical_blocks(info[0],quest[q],info[1])
            timing[key]["bm25_seconds"]=perf_counter()-begin
            if not blocks:missing.append([row["id"],"empty_file"]);continue
            lo,hi=blocks[0];next_block=blocks[1] if len(blocks)>1 else ()
        else:
            lo,hi=row["visible"];hi=min(hi,len(info[0]))
            if lo>hi:missing.append([row["id"],"visible_beyond_eof"]);continue
        pred=policies(tok,quest[q],lo,hi,info,next_block)
        outputs.append(dict(id=row["id"],issue=q,repo=row["repo"],file=key,**pred))
    save(D/(pref+"forecasts.json.gz"),outputs)
    save(D/(pref+"forecast-seal.json"),dict(n=len(outputs),sha=sha(D/(pref+"forecasts.json.gz")),tokenizer=sha(T),dataset=sha(D/(pref+"dataset.json")),operator=sha(D/"predict.py"),excluded=missing,inventory=timing))
if __name__=="__main__":main(sys.argv[1])

