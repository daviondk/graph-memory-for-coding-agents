"""Pure prefix policy; receives only the current observed pages, times and issue description."""
import math,re
from functools import lru_cache
from collections import Counter
from common import pages,groups,signal
BUDGETS=(256,512,1024)
ARMS=('reset_tail','rebased_tail','rebased_center','latest_contiguous','first_page','marginal','joint')
CAP=48
TOKENIZER=None
@lru_cache(maxsize=50000)
def cost(s):
    global TOKENIZER
    if TOKENIZER is None:
        from common import ROOT
        from tokenizers import Tokenizer
        TOKENIZER=Tokenizer.from_file(str(ROOT/'qwen_tokenizer.json'))
    return len(TOKENIZER.encode(s,add_special_tokens=False).ids)
def render(v):return f'@@ {v[0]} {v[1]}..{v[2]} @@\n'+v[4]
def weight_text(t):
    return frozenset(w.lower() for w in re.findall(r'\b[A-Za-z_]\w{2,}\b',t))
wordset=lru_cache(maxsize=50000)(weight_text)
def order(rows,meta,style='center'):
    def key(i):
        path,a,b,when,_=rows[i]
        x=-a if style=='tail' else abs((a+b)/2-meta['center'][path])
        return -when,-meta['paths'][path],x,path,a
    return sorted(range(len(rows)),key=key)
def costs(rows):
    return [cost(render(v))+1 for v in rows]
def adjust(rows,indices,budget):
    wire='\n'.join(render(rows[i]) for i in indices)
    actual=cost(wire)
    while actual>budget:
        indices=indices[:-1];actual=cost('\n'.join(render(rows[i]) for i in indices))
    return indices,actual
def greedy_base(rows,priority,cs,limit,contiguous=False):
    picked=[];used=0;bounds=None
    for i in priority:
        p,a,b,_,_=rows[i]
        if cs[i]-1>limit-used:continue
        if contiguous and bounds is not None:
            q,lo,hi=bounds
            if q!=p or not(a==hi+1 or b==lo-1):continue
            bounds=(p,min(a,lo),max(b,hi))
        else:bounds=(p,a,b)
        picked.append(i);used+=cs[i]
    return adjust(rows,picked,limit)
def gen_features(row,meta,step,issue):
    p,a,b,age,body=row;center=meta['center'][p];cmdtime=meta['paths'][p];dist=((a+b)/2-center)/12
    words=wordset(body);terms=wordset(issue[:9000]);common=words & terms
    marked=sum((('_' in x or len(x)>8) and x in terms) for x in words)
    stem=p.split('/')[-1].rsplit('.',1)[0].lower()
    return [
        min(8,step-age),min(8,step-cmdtime), min(8,meta['visits'][p]),min(8,step-meta['edited'].get(p,-100)),
        max(-5,min(5,round(dist)))+5, min(5,len(common)),min(3,marked),int(stem in terms),
        int('def ' in body), int('class ' in body), int('return ' in body),int('test' in p.lower()),int(p.lower().endswith('.py')),
        min(5,len(body)//150),min(5,a//120),int(age==cmdtime),min(4,len(body.splitlines())//3),
    ]
DIMS=[9,9,9,9,11,6,4,2,2,2,2,2,2,6,6,2,5]
def features(rows,meta,step,issue,allowed):
    return {i:gen_features(rows[i],meta,step,issue) for i in allowed}
def unique_span(rows,path,old):
    # Find exact byte sequence across neighboring pages. Ambiguous or unseen spans carry no positive training label.
    ordered=[(i,r) for i,r in enumerate(rows) if r[0]==path]
    found=[];chunk=[]
    def finish(c):
        if not c:return
        body='\n'.join(r[4] for _,r in c);pos=body.find(old)
        if pos<0:return
        if body.find(old,pos+1)>=0:found.extend([(),()]);return
        lo=c[0][1][1]+body[:pos].count('\n');hi=lo+old.count('\n')
        found.append(tuple(i for i,r in c if r[1]<=hi and r[2]>=lo))
    for i,r in ordered:
        if chunk and r[1]!=chunk[-1][1][2]+1:finish(chunk);chunk=[]
        chunk.append((i,r))
    finish(chunk)
    return found[0] if len(found)==1 else None
def predictor(f,model):
    z=model['intercept']+sum(row[k] for row,k in zip(model['weights'],f))
    return 1/(1+math.exp(-max(-25,min(25,z))))
def proposals(rows,fs,model):
    next_idx={(r[0],r[1]):i for i,r in enumerate(rows)}
    out={}
    for i,feat in fs.items():
        prob=predictor(feat,model);p=rows[i][0];block=[i];j=i
        for k,q in enumerate(model['width_fractions']):
            if k:
                j=next_idx.get((p,rows[j][2]+1))
                if j is None:break
                block.append(j)
            out[tuple(block)]=q*prob
    return out
def ranked_fill(rows,cs,utilities,limit):
    rank=sorted(utilities,key=lambda i:(-utilities[i]/max(1,cs[i]),i))
    return greedy_base(rows,rank,cs,limit)
def joint_fill(rows,cs,props,limit):
    avail=dict(props);chosen=set();seq=[];used=0
    # All requirements are intervals of at most 3 pages. A candidate's gain is mass of
    # every previously uncovered requirement whose missing pages it covers in full.
    while avail:
        missing={frozenset(set(k)-chosen) for k in avail}
        aggregate=Counter()
        for span,q in avail.items():aggregate[frozenset(set(span)-chosen)]+=q
        best=None
        for block in missing:
            b=tuple(sorted(block));c=sum(cs[i] for i in b)
            if not b or used+c-1>limit:continue
            gain=sum(aggregate[frozenset(b[j] for j in range(len(b)) if mask & (1<<j))] for mask in range(1,1<<len(b)))
            choice=(gain/c,gain,-min(b),b)
            if best is None or choice>best:best=choice
        if best is None:break
        b=best[-1];chosen.update(b);seq.extend(b);used+=sum(cs[i] for i in b)
        avail={s:q for s,q in avail.items() if not all(i in chosen for i in s)}
    return adjust(rows,seq,limit)
def policy(states,meta,t,issue,model):
    resets=pages(states['drop']);rs=pages(states['rebase']);dc=costs(resets);cs=costs(rs)
    dt=order(resets,meta,'tail');rt=order(rs,meta,'tail');mid=order(rs,meta);active=mid[:CAP]
    fs=features(rs,meta,t,issue,active);pr=proposals(rs,fs,model)
    first={i:predictor(feat,model) for i,feat in fs.items()};marg=Counter()
    for span,prob in pr.items():
        for i in span:marg[i]+=prob/len(span)
    out={}
    for b in BUDGETS:
        ans=[greedy_base(resets,dt,dc,b),greedy_base(rs,rt,cs,b),greedy_base(rs,mid,cs,b),
             greedy_base(rs,mid,cs,b,True),ranked_fill(rs,cs,first,b),ranked_fill(rs,cs,marg,b),joint_fill(rs,cs,pr,b)]
        out[str(b)]=dict(zip(ARMS,ans))
    return out
