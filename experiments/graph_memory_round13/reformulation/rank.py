"""Rank from a sealed input-only projection. This program opens no Git tree or future action log."""
import collections,gzip,hashlib,json,math,re,statistics,time
from pathlib import Path,PurePosixPath
D=Path(__file__).resolve().parent
def h(b):return hashlib.sha256(b).hexdigest()
def load(n):
    data=(D/n).read_bytes()
    return json.loads(gzip.decompress(data) if n.endswith('.gz') else data)
def dump(n,x):
    data=json.dumps(x,ensure_ascii=True,sort_keys=True,separators=(',',':')).encode()
    (D/n).write_bytes(gzip.compress(data,mtime=0) if n.endswith('.gz') else data)
STOP=set('in on a an as and are but for from has have here if import is it of or that the their this to was were will will with you your can should could which they method class def else elif with self cls none return true false not raise list str int print file use test tests python want would when values value data type function current object currently how what example following problem description consider using expected actual behavior'.split())
IDENT=re.compile(r'[A-Za-z_][A-Za-z_0-9]*')
def parts(tok):
    return re.sub(r'([a-z0-9])([A-Z])',r'\1_\2',re.sub(r'([A-Z]+)([A-Z][a-z])',r'\1_\2',tok)).lower().split('_')
def tokens(s):
    result=[]
    for w in IDENT.findall(s):
        seq=[w.lower(),*parts(w)]
        result.extend(t for t in dict.fromkeys(seq) if len(t)>1 and t not in STOP)
    return result
def ordering(names,score,docs):
    return sorted(names,key=lambda p:(-score[p],-docs[p]['last'],p))
def normalize(scores):
    top=max(scores.values(),default=0)
    return {p:x/top if top else 0. for p,x in scores.items()}
def adjacency(evidence,seeds):
    names=list(evidence);n=len(names)
    df=collections.Counter(term for ts in evidence.values() for term in ts)
    weights={w:math.log(1+(n-c+.5)/(c+.5))**2 for w,c in df.items() if 1<c and c<=max(2,math.ceil(n*.55))}
    bags={p:{w for w in evidence[p] if w in weights} for p in names}
    norm={p:math.sqrt(sum(weights[w] for w in bag)) for p,bag in bags.items()}
    adj={}
    for p in names:
        adj[p]=0.
        for s,mass in seeds.items():
            if s==p or not norm[p] or not norm[s]:continue
            shared=bags[p]&bags[s]
            edge=sum(weights[w] for w in shared)/(norm[p]*norm[s])
            adj[p]+=mass*edge
    return normalize(adj)
def calculate(row):
    docs=row['docs'];names=sorted(docs);k=row['key'];q=k['scope'];start=time.perf_counter_ns()
    if not names:return {m:[] for m in ('last_read','last_scope','bm25','strong','graph','shuffled')},{'prepare_ns':0,'graph_ns':0,'shuffled_ns':0}
    current=q if q in docs else None
    last_read=sorted(names,key=lambda p:(-docs[p]['read'],-docs[p]['direct'],-docs[p]['last'],p))
    if current:scope_order=[current,*[p for p in last_read if p!=current]]
    else:scope_order=last_read[:]
    query=collections.Counter(tokens(row['issue'])[:120])
    query.update(4*tokens(k['literal']));query.update(2*tokens(q))
    vocab={p:collections.Counter(3*tokens(p)+tokens(docs[p]['snip'])) for p in names}
    sizes={p:sum(x.values()) for p,x in vocab.items()};avg=sum(sizes.values())/len(names) or 1
    df=collections.Counter(w for x in vocab.values() for w in x)
    bm={}
    for p,x in vocab.items():
        score=0.
        for w,count in query.items():
            f=x.get(w,0)
            if f:
                idf=math.log(1+(len(names)-df[w]+.5)/(df[w]+.5))
                score+=min(4,count)*idf*(2.2*f)/(f+1.2*(.25+.75*sizes[p]/avg))
        bm[p]=score
    scaled=normalize(bm)
    recency={p:1/(1+.35*i) for i,p in enumerate(last_read)}
    scope_parts=PurePosixPath(q).parts
    def vicinity(p):
        if p==current:return 1.
        directories=PurePosixPath(p).parts[:-1]
        target=scope_parts[:-1] if q.endswith('.py') else scope_parts
        if not target or not directories:return 0.
        common=0
        for x,y in zip(target,directories):
            if x!=y:break
            common+=1
        return .45*common/max(len(directories),len(target))
    base={p:.35*scaled[p]+.35*recency[p]+.30*vicinity(p) for p in names}
    bro=ordering(names,base,docs);seed=bro[:3];seeds={p:base[p]/sum(base[x] for x in seed) for p in seed}
    age_end=time.perf_counter_ns()
    symbols={}
    for p in names:
        terms={s.lower() for s in IDENT.findall(docs[p]['snip']) if len(s)>=4 and s.lower() not in STOP}
        symbols[p]=terms
    actual=adjacency(symbols,seeds);t2=time.perf_counter_ns()
    order=sorted(names,key=lambda p:h((row['id']+'|'+p).encode()))
    placebo={p:symbols[order[(i+1)%len(order)]] for i,p in enumerate(order)}
    random=adjacency(placebo,seeds);t3=time.perf_counter_ns()
    def blend(adj):
        return ordering(names,{p:base[p]+.22*adj[p] for p in names},docs)
    out={'last_read':last_read,'last_scope':scope_order,'bm25':ordering(names,bm,docs),'strong':bro,'graph':blend(actual),'shuffled':blend(random)}
    assert all(set(xs)==set(names) for xs in out.values())
    return out,{'prepare_ns':age_end-start,'graph_ns':t2-age_end,'shuffled_ns':t3-t2,'edges_identifiers':sum(map(len,symbols.values()))}
def main():
    lock=load('input.lock.json')
    assert all(h((D/n).read_bytes())==v for n,v in lock['study'].items())
    rows=load('inputs.json.gz');ans=[]
    for row in rows:
        ranks,cost=calculate(row);ans.append({'id':row['id'],'rank':ranks,'cost':cost})
    dump('frozen_rankings.json.gz',ans)
    dump('forecast.lock.json',{'files':{n:h((D/n).read_bytes()) for n in ['rank.py','input.lock.json','inputs.json.gz','frozen_rankings.json.gz','PROTOCOL_RU.md']},'n':len(ans),'data_access':'sealed prefix only; no Git, future views or patch file lists','formula':{'strong':'0.35*BM25/max + 0.35/(1+0.35*last_read_rank_index) + 0.30*scope','graph':'strong + 0.22*(normalized rare identifier cosine diffusion from top 3 strong seeds, no self edge)','shuffled':'same as graph with a hash-defined rotation of whole identifier bags'}})
    print(len(ans),'sealed')
if __name__=='__main__':main()
