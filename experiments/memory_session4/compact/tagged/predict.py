"""Materialize every prefix-only prediction to disk before importing or invoking the scorer."""
from collections import defaultdict,Counter
from functools import lru_cache
from pathlib import Path
import gzip,hashlib,json,math,re,sys,time
from concurrent.futures import ProcessPoolExecutor
from common import *
from tokenizers import Tokenizer
TK=Tokenizer.from_file(str(ROOT/'source'/'qwen_tokenizer.json'))
@lru_cache(maxsize=40000)
def nt(s):return len(TK.encode(s,add_special_tokens=False).ids)
@lru_cache(maxsize=30000)
def tokens(s):return set(w.lower() for w in re.findall(r'[A-Za-z_][A-Za-z_0-9]{2,}',s) if w.lower() not in STOP)
@lru_cache(maxsize=25000)
def preview(p,n,e,body):return f'@@ {p} {n}..{e} @@\n'+body
BUDGETS=(256,512,1024)
ARMS={'drop_recenthead':('drop','head'),'drop_recenttail':('drop','tail'),'drop_mid':('drop','mid'),'drop_lexical':('drop','lex'),'drop_fused':('drop','fused'),
      'rebase_recenthead':('rebase','head'),'rebase_mid':('rebase','mid'),'rebase_fused':('rebase','fused'),'stale_fused':('stale','fused'),
      'one_reopen':('rebase','one'),'paths':('rebase','paths')}
def rankings(items,meta,q):
    idx=list(range(len(items)));issue_terms,cmd_terms=q
    def mid(i):
        p,n,e,age,_=items[i];return (-age,-meta['paths'].get(p,0),abs((n+e)/2-meta['center'].get(p,n)),p,n)
    head=sorted(idx,key=lambda i:(-items[i][3],-meta['paths'].get(items[i][0],0),items[i][0],items[i][1]))
    tail=sorted(idx,key=lambda i:(-items[i][3],-meta['paths'].get(items[i][0],0),items[i][0],-items[i][1]))
    center=sorted(idx,key=mid)
    df=Counter()
    terms=[tokens(item[4])|tokens(item[0]) for item in items]
    for tt in terms:df.update(tt)
    query=issue_terms|cmd_terms;weights={term:(1+.5*(term in cmd_terms))*math.log(1+(1+len(items))/(1+k)) for term,k in df.items() if term in query}
    ls=[sum(weights.get(t,0) for t in sorted(ts & query))/max(1,len(ts))**.35 for ts in terms]
    lex=sorted(idx,key=lambda i:(-ls[i],mid(i)))
    freq=sorted(idx,key=lambda i:(-meta['visits'][items[i][0]],mid(i)))
    cr={i:j for j,i in enumerate(center)};lr={i:j for j,i in enumerate(lex)};fr={i:j for j,i in enumerate(freq)}
    fused=sorted(idx,key=lambda i:(-(1/(6+cr[i])+1/(6+lr[i])+.3/(6+fr[i])),mid(i)))
    latest=center and items[center[0]][0]
    return {'head':head,'tail':tail,'mid':center,'lex':lex,'fused':fused,'one':[i for i in center if items[i][0]==latest]}
def pack(items,order,limit,one=False):
    pieces=[];selected=[];size=0
    for i in order:
        p,n,e,age,body=items[i];text=preview(p,n,e,body);nq=nt(text)
        if nq>limit-size:continue
        if one and selected:
            prev=items[selected[-1]]
            # A single contiguous range around the most recent observation, no disjoint cold reads.
            if not (n==max(items[j][2] for j in selected)+1 or e==min(items[j][1] for j in selected)-1):continue
        pieces.append(text);selected.append(i);size+=nq+1
        if limit-size<10:break
    wire='\n'.join(pieces);actual=nt(wire)
    while actual>limit:
        selected.pop();pieces.pop();wire='\n'.join(pieces);actual=nt(wire)
    return selected,actual
def output_for(states,meta,q):
    ret={};represent={}
    for mode,mem in states.items():
        items=pages(mem)
        # Page handles always refer to this prefix's captured table in source order.
        represent[mode]=items
        rankings_=rankings(items,meta,q)
        for arm,(m,method) in ARMS.items():
            if mode!=m:continue
            for budget in BUDGETS:
                if method=='paths':
                    out=[]
                    for p in sorted(mem,key=lambda p:(-meta['paths'].get(p,0),p)):
                        trial='\n'.join(out+[p])
                        if nt(trial)<=budget:out.append(p)
                    val=out;cost=nt('\n'.join(out))
                else:val,cost=pack(items,rankings_[method],budget,method=='one')
                ret[f'{arm}:{budget}']=[val,cost]
    return ret,represent
def work(k):
    out=ROOT/'sealed'/f'{k}.jsonl.gz'
    part=out.with_suffix('.tmp');total=0
    with gzip.open(part,'wt',encoding='utf8',compresslevel=3) as f:
        for row in src(k):
            meta=newmeta();states={m:{} for m in ('drop','rebase','stale')};n=len(row['events'])
            for t,event in enumerate(row['events'],1):
                advance(states,meta,event,t)
                if t%4 or t==n:continue
                qq=signal(row['issue'],meta['bash'])
                preds,represent=output_for(states,meta,qq)
                layouts={m:digest_pages(v) for m,v in represent.items()}
                print(emit([row['row'],t,preds,layouts]),file=f);total+=1
    part.replace(out); print('sealed',k,total,flush=True);return total
def digest_pages(items):
    return hashlib.sha256(emit(items).encode()).hexdigest()
if __name__=='__main__':
    (ROOT/'sealed').mkdir(exist_ok=True)
    with ProcessPoolExecutor(3) as pool:n=sum(pool.map(work,range(8)))
    names=['PROTOCOL.md','WRITE_AMENDMENT.md','common.py','predict.py','collect.py','score.py']+[str(p.relative_to(ROOT)).replace('\\','/') for folder in ('source','sealed') for p in sorted((ROOT/folder).glob('*')) if p.is_file()]
    (ROOT/'prediction_lock.json').write_text(json.dumps({'boundaries':n,'files':{p:digest(ROOT/p) for p in names}},indent=1))
    print('all sealed',n)

