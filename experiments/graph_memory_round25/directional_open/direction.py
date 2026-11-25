"""Frozen component, bidirectional text service, and actual read billing."""
from collections import defaultdict
import hashlib,sys
from shared25 import R,ARMS,PAIRS
sys.path.insert(0,str(R/"marginal_open"))
from novelty import WORDS,make_windows,lexical_order
def choose(query,frags,lengths,tok):
    spans=defaultdict(list)
    for e,l,s in frags:
        if s:spans[e].append((l,l+len(s),s))
    comps={}
    for e,v in spans.items():
        out=[]
        for l,h,s in sorted(v):
            if out and l<=out[-1][1]:
                a,b,txt=out[-1];edge=min(b,h)
                assert txt[l-a:edge-a]==s[:edge-l]
                if h>b:out[-1]=(a,h,txt+s[b-l:])
            else:out.append((l,h,s))
        comps[e]=out
    wins=make_windows(frags,tok)
    for j in lexical_order(query,wins):
        v=wins[j];cand=next(((a,b,s) for a,b,s in comps.get(v.field,()) if a<=v.start<b),None)
        if not cand:continue
        l,h,s=cand
        if h>=lengths[v.field]:continue
        offsets=tok.encode(s,add_special_tokens=False).offsets
        ls=s[:offsets[32][0]] if len(offsets)>32 else s
        rs=s[offsets[-32][0]:] if len(offsets)>32 else s
        terms=set(WORDS.findall(query.casefold()))
        left=len(terms.intersection(WORDS.findall(ls.casefold())))
        right=len(terms.intersection(WORDS.findall(rs.casefold())))
        return {"e":v.field,"l":l,"h":h,"L":lengths[v.field],"matches":[left,right],"left":int(l>0 and left>right)}
    return None
def token(tok,text):return tok.encode(text,add_special_tokens=False)
def part(tok,src,e,anchor,side,cap):
    head=f"[{e}:{anchor}] ";nh=len(token(tok,head).ids)
    if cap<nh:return None
    if side=="R":
        txt=head+src[anchor:];end=min(len(txt),4096)
        while True:
            while end<len(txt) and not txt[end].isspace():end+=1
            enc=token(tok,txt[:end])
            if len(enc.ids)>cap or end==len(txt):break
            end=min(len(txt),2*end)
        cut=enc.offsets[cap][0] if len(enc.ids)>cap else end
        while cut>=len(head) and len(token(tok,txt[:cut]).ids)>cap:cut-=1
        if cut<len(head):return None
        l,h=anchor,anchor+cut-len(head)
    else:
        width=min(anchor,4096)
        while True:
            start=anchor-width
            while start>0 and not src[start-1].isspace():start-=1
            seg=src[start:anchor];enc=token(tok,seg);n=len(enc.ids)
            if n>cap-nh or start==0:break
            width=min(anchor,width*2)
        keep=cap-nh
        if keep==0:l=anchor
        elif n<=keep:l=start
        else:l=start+enc.offsets[n-keep][0]
        while l<=anchor and len(token(tok,head+src[l:anchor]).ids)>cap:l+=1
        if l>anchor:return None
        h=anchor
    real=head+src[l:h];n=len(token(tok,real).ids);assert nh<=n<=cap
    return [e,l,h,n,anchor,side,nh]
def execute(tok,component,src):
    if not component:
        return {"arms":{k:[] for k in ARMS},"equal":{x+"-"+y:[[],[]] for x,y in PAIRS}}
    p=component;e,l,h=p["e"],p["l"],p["h"];cache={};result_cache={}
    def piece(side,cap):
        k=(side,cap)
        if k not in cache:cache[k]=part(tok,src,e,l if side=="L" else h,side,cap)
        return cache[k]
    def make(arm,cap):
        tag=(arm,cap)
        if tag in result_cache:return result_cache[tag]
        if cap<=0 or (arm=="left" and l==0):out=[]
        elif arm=="both" and l>0:out=[x for x in (piece("L",cap//2),piece("R",cap-cap//2)) if x]
        else:
            side="L" if l and (arm in ("left","feasible_left") or (arm=="adaptive" and p["left"])) else "R"
            single=piece(side,cap);out=[single] if single else []
        wire="\n".join(f"[{u[0]}:{u[4]}] "+src[u[1]:u[2]] for u in out)
        assert len(token(tok,wire).ids)==sum(a[3] for a in out)<=cap
        result_cache[tag]=out;return out
    charge=lambda v:sum(a[3] for a in v)
    out={k:make(k,256) for k in ARMS};eq={}
    for x,y in PAIRS:
        cap=min(charge(out[x]),charge(out[y]))
        while True:
            a,b=make(x,cap),make(y,cap);u,v=charge(a),charge(b)
            if u==v:break
            assert min(u,v)<cap;cap=min(u,v)
        eq[x+"-"+y]=[a,b]
    return {"arms":out,"equal":eq}
