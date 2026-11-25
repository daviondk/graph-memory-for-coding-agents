"""Return a source-coordinate recipe for each exact, physically charged request."""
from functools import lru_cache
from bisect import bisect_left,bisect_right
from data import *
import sys
sys.path.insert(0,str(OLD))
import direction
from novelty import Window,lexical_order
def leftdiff(a,b,known):
    out=[]
    for l,h in known:
        if h<=a:continue
        if l>=b:break
        if a<l:out.append((a,min(l,b)))
        a=max(a,h)
    if a<b:out.append((a,b))
    return out
def merge(seq):
    out=[]
    for l,h in sorted(seq):
        if out and l<=out[-1][1]:out[-1]=(out[-1][0],max(h,out[-1][1]))
        else:out.append((l,h))
    return out
def txt(part,src):
    k=part[0]
    if k=='s':return src[part[1]:part[2]]
    if k=='h':return f'[0:{part[1]}] '
    return ' ' if k=='w' else '\n'
def bill(tok,parts,src):
    wire=''.join(txt(p,src) for p in parts)
    return len(tok.encode(wire,add_special_tokens=False).ids)
def makeops(ops):
    out=[]
    for row in ops:
        if not row:continue
        if out:out.append(['n'])
        out.extend(row)
    return out
def prefix(tok,parts,src,cap):
    if not parts or cap<=0:return []
    head=txt(parts[0],src);assert parts[0][0]=='h'
    if len(tok.encode(head,add_special_tokens=False).ids)>cap:return []
    strings=[txt(p,src) for p in parts];wire=''.join(strings);enc=tok.encode(wire,add_special_tokens=False)
    if len(enc.ids)<=cap:return parts
    cut=enc.offsets[cap][0]
    while cut and len(tok.encode(wire[:cut],add_special_tokens=False).ids)>cap:cut-=1
    if cut<len(head):return []
    result=[];seen=0
    for p,s in zip(parts,strings,strict=True):
        keep=max(0,min(len(s),cut-seen))
        if keep:
            if keep==len(s):result.append(p)
            else:
                assert p[0]=='s'
                result.append(['s',p[1],p[1]+keep])
        seen+=len(s)
    assert ''.join(txt(v,src) for v in result)==wire[:cut];return result
def side_slice(tok,src,l,h,side,cap):
    if side=='R':return prefix(tok,[['h',l],['s',l,h]],src,cap)
    head=['h',h];nh=bill(tok,[head],src)
    if nh>cap:return []
    if bill(tok,[head,['s',l,h]],src)<=cap:return [head,['s',l,h]]
    offsets=tok.encode(src[l:h],add_special_tokens=False).offsets;b=cap-nh
    start=h if not b else l+offsets[max(0,len(offsets)-b)][0]
    while start<h and bill(tok,[head,['s',start,h]],src)>cap:start+=1
    return [head,['s',start,h]] if start<h else [head]
class Reader:
    def __init__(self,source,sentences,tok):
        self.src=source;self.sent=sentences;self.tok=tok
        self.low=[r[0] for r in sentences];self.high=[r[1] for r in sentences]
    def block(self,query,base,cut):
        src,tok,sent=self.src,self.tok,self.sent
        known=merge([(l,h) for e,l,h in base])
        if not cut:return None
        l,h=cut['l'],cut['h'];assert cut['e']==0 and (l,h) in known
        low=bisect_right(self.high,l);stop=bisect_left(self.low,h)
        choices=[Window(0,max(a,l),min(b,h),src[max(a,l):min(b,h)],0) for a,b in sent[low:stop]]
        if not choices:
            assert not src[l:h].strip()
            return None
        center=low+lexical_order(query,choices)[0]
        native=[['h',sent[max(0,center-3)][0]]]
        for i,(a,b) in enumerate(sent[max(center-3,0):center+4]):
            if i:native.append(['w'])
            native.append(['s',a,b])
        def neighbors(side):
            rows=[];selected=[]
            indexes=range(bisect_left(self.low,l)-1,-1,-1) if side=='L' else range(bisect_right(self.high,h),len(sent))
            for j in indexes:
                a,b=sent[j]
                if side=='L':b=min(b,l)
                else:a=max(a,h)
                if b<=a:continue
                novel=leftdiff(a,b,known)
                if novel:
                    selected.append(j);rows.extend(novel)
                    if len(selected)==3:break
            arr=merge(rows)
            return (arr[::-1] if side=='L' else arr),selected
        left,idxl=neighbors('L');right,idxr=neighbors('R')
        @lru_cache(None)
        def side_segments(side,cap):
            spans=left if side=='L' else right;parts=[];cost=0
            for a,b in spans:
                if cap<=cost:break
                z=side_slice(tok,src,a,b,side,cap-cost)
                if not z:break
                parts.append(z);cost+=bill(tok,z,src)
                covered=sum(v[2]-v[1] for v in z if v[0]=='s')
                if covered<b-a:break
            return parts,cost
        @lru_cache(None)
        def query_at(method,cap):
            if cap<=0:return [],0
            if method=='window':parts=prefix(tok,native,src,cap)
            elif method=='both':
                cfg=[('L',l,cap//2),('R',h,cap-cap//2)] if l>0 else [('R',h,cap)]
                rr=[direction.part(tok,src,0,anchor,side,w) for side,anchor,w in cfg]
                ops=[[['h',x[4]],['s',x[1],x[2]]] for x in rr if x]
                parts=makeops(ops)
            else:
                assert method=='boundary_window'
                p,nleft=side_segments('L',cap//2)
                rest,nright=side_segments('R',cap-nleft)
                p,nleft=side_segments('L',cap-nright)
                parts=makeops(p+rest)
            cost=bill(tok,parts,src);assert cost<=cap
            return parts,cost
        return query_at,{'center':center,'visible_candidates':len(choices),'left_indices':idxl,'right_indices':idxr}
def equal(fn,a,b):
    cap=min(fn(a,256)[1],fn(b,256)[1])
    while True:
        x,y=fn(a,cap),fn(b,cap)
        if x[1]==y[1]:return x,y
        assert min(x[1],y[1])<cap;cap=min(x[1],y[1])
