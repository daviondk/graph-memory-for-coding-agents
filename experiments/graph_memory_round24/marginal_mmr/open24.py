from io24 import PAIRS
def clip(tok,op,body,cap):
    if not op or not cap:return None
    e,l,h,n=op
    if n<=cap:return op
    head=f"[{e}:{l}] ";s=head+body[l:h]
    enc=tok.encode(s,add_special_tokens=False);assert len(enc.ids)==n
    cut=enc.offsets[cap][0]
    while cut>=len(head):
        paid=len(tok.encode(s[:cut],add_special_tokens=False).ids)
        if paid<=cap:return [e,l,l+cut-len(head),paid]
        cut-=1
    return None
def apply(decisions,get_body,reader,tok):
    resolved={};arms={}
    for k,v in decisions.items():
        if v is None:arms[k]=None;continue
        j,e,l=v
        if (e,l) not in resolved:
            op=list(reader(tok,get_body(e),e,l))
            assert op[:2]==[e,l] and op[3]<=256
            resolved[e,l]=op
        arms[k]=resolved[e,l]
    equal={}
    for x,y in PAIRS:
        a,b=arms[x],arms[y];cap=min(a[3],b[3]) if a and b else 0
        while cap:
            p=clip(tok,a,get_body(a[0]),cap);q=clip(tok,b,get_body(b[0]),cap)
            u,v=(p[3] if p else 0),(q[3] if q else 0)
            if u==v:break
            assert min(u,v)<cap;cap=min(u,v)
        if not cap:p=q=None
        equal[x+"-"+y]=[p,q]
    return {"arms":arms,"equal":equal}
