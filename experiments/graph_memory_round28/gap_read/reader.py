"""Apply real predecessor/successor lookup, physical rendering and independent gap assertions."""
from functools import lru_cache
from bisect import bisect_left,bisect_right
from nltk.tokenize import PunktSentenceTokenizer
from store import *
import direction
ARMS=('both','window','gap')
def difference(l,h,known):
    gaps=[]
    for a,b in known:
        if b<=l:continue
        if a>=h:break
        if l<a:gaps.append((l,min(a,h)))
        l=max(b,l)
    if l<h:gaps.append((l,h))
    return gaps
def units(src,ds):
    if ds=='ise':
        x=0;parts=[]
        for line in src.splitlines(keepends=True):
            parts.append((x,x+len(line)));x+=len(line)
        assert x==len(src);return parts
    z=list(PunktSentenceTokenizer().span_tokenize(src))
    return [(l,z[i+1][0] if i+1<len(z) else len(src)) for i,(l,h) in enumerate(z)]
def piece(tok,src,e,start,end,side,cap):
    anchor=start if side=='R' else end;head=f'[{e}:{anchor}] ';nh=len(tok.encode(head,add_special_tokens=False).ids)
    if cap<=nh:return None
    text=src[start:end];enc=tok.encode(head+text,add_special_tokens=False)
    l,h=start,end
    if len(enc.ids)>cap:
        if side=='R':
            clip=enc.offsets[cap][0]
            while clip>len(head) and len(tok.encode((head+text)[:clip],add_special_tokens=False).ids)>cap:clip-=1
            h=start+max(0,clip-len(head))
        else:
            ix=tok.encode(text,add_special_tokens=False).offsets
            l=start+ix[max(0,len(ix)-(cap-nh))][0]
            while l<h and len(tok.encode(head+src[l:h],add_special_tokens=False).ids)>cap:l+=1
    if h<=l:return None
    paid=len(tok.encode(head+src[l:h],add_special_tokens=False).ids);assert nh<=paid<=cap
    return [e,l,h,paid,anchor,side,nh]
def execute(db,ds,q,r,tok,src,segments):
    cut=r['cut']
    if not cut:
        return {'arms':{k:[] for k in ARMS},'eq':{a:[[],[]] for a in ('window','both')},'diag':{'no_component':True,'sql_ranges':0}}
    e,l,h=cut['e'],cut['l'],cut['h'];assert len(src)==cut['L']
    known=union([(a,b) for eid,a,b in r['base'] if eid==e])
    allg=difference(0,len(src),known)
    left=db.execute(SQL_LEFT,(ds,q,e,l)).fetchall();right=db.execute(SQL_RIGHT,(ds,q,e,h)).fetchall()
    assert left==[p for p in reversed(allg) if p[1]<=l][:3] and right==[p for p in allg if p[0]>=h][:3]
    los=[x for x,y in segments];his=[y for x,y in segments]
    def structural(side):
        order=range(bisect_left(los,l)-1,-1,-1) if side=='L' else range(bisect_right(his,h),len(segments))
        parts=[];num=0
        for j in order:
            a,b=segments[j]
            if side=='L':b=min(b,l)
            else:a=max(a,h)
            if b<=a:continue
            gaps=difference(a,b,known)
            if gaps:
                parts+=gaps;num+=1
                if num==3:break
        arr=[tuple(v) for v in union(parts)]
        return (arr[::-1] if side=='L' else arr)[:3]
    win=(structural('L'),structural('R'));sides={'gap':(left,right),'window':win}
    @lru_cache(None)
    def one(method,side,cap):
        op=[];cost=0
        for a,b in sides[method][0 if side=='L' else 1]:
            z=piece(tok,src,e,a,b,side,cap-cost)
            if not z:break
            op.append(z);cost+=z[3]
            if z[2]-z[1]<b-a:break
        return op,cost
    @lru_cache(None)
    def fn(method,cap):
        if cap<=0:return [],0
        if method=='both':
            cfg=(('L',l,cap//2),('R',h,cap-cap//2)) if l>0 else (('R',h,cap),)
            op=[v for side,anchor,w in cfg if (v:=direction.part(tok,src,e,anchor,side,w))]
        else:
            _,paid=one(method,'L',cap//2)
            y,n=one(method,'R',cap-paid)
            x,_=one(method,'L',cap-n)
            op=x+y;assert len(op)<=6
        wire='\n'.join(f'[{e}:{z[4]}] '+src[z[1]:z[2]] for z in op)
        paid=len(tok.encode(wire,add_special_tokens=False).ids)
        assert paid==sum(z[3] for z in op)<=cap
        return op,paid
    def paired(a):
        cap=min(fn('gap',256)[1],fn(a,256)[1])
        while True:
            x,n=fn('gap',cap);y,m=fn(a,cap)
            if n==m:return [x,y]
            assert min(n,m)<cap;cap=min(n,m)
    arms={k:fn(k,256)[0] for k in ARMS};eq={a:paired(a) for a in ('window','both')}
    # Read and verify each physically returned address from SQLite; coordinate metric is Unicode codepoints.
    returned={tuple(z[:3]) for op in list(arms.values())+[v for pair in eq.values() for v in pair] for z in op}
    positions={ix:len(src[:ix].encode()) for _,a,b in returned for ix in (a,b)}
    for eid,a,b in returned:
        data=db.execute('select substr(cast(body as blob),?,?) from fields where ds=? and t=? and e=?',(positions[a]+1,positions[b]-positions[a],ds,str(r['t']),eid)).fetchone()[0]
        assert data==src[a:b].encode()
    diag={'no_component':False,'field_units':len(segments),'available_gap':[len(left),len(right)],'available_window':[len(win[0]),len(win[1])],'same_span_pools':(left,right)==win,'sql_ranges':len(returned)}
    return {'arms':arms,'eq':eq,'diag':diag}
def forecast(name):
    lock();assert sha(DB)==read(D/'db-receipt.json')['database']
    c=open_db();tok=source.c.tok() if name=='mdd' else source.Tokenizer.from_file(str(source.TOK))
    picks=read(R25/f'{name}-choices.json.gz');native=read(R25/f'{name}-opened.json.gz');srcset={};out={}
    for q,r in sorted(picks.items()):
        k=r['cut'];t=str(r['t'])
        if k:
            key=t,k['e']
            if key not in srcset:
                src,dig=c.execute('select body,digest from fields where ds=? and t=? and e=?',(name,*key)).fetchone()
                assert hashlib.sha256(src.encode()).hexdigest()==dig;srcset[key]=src,units(src,name)
            src,segments=srcset[key]
        else:src,segments='',[]
        ans=execute(c,name,q,r,tok,src,segments)
        assert ans['arms']['both']==native[q]['arms']['both']
        out[q]=ans
    c.close();p=D/f'{name}-forecasts.json.gz';digest=save(p,out)
    save(D/f'{name}-seal.json',{'rows':digest,'n':len(out),'db':sha(D/'db-receipt.json'),'operator':sha(Path(__file__)),'analysis_plan':sha(D/'analysis-lock.json'),'r25_identical':len(out)})
if __name__=='__main__':forecast(sys.argv[1])
