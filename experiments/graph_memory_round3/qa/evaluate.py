"""Score locked rankings using turn and session outcomes, and fixed reader answers with original category treatment."""
import sys,json,gzip,math,re,os,string,itertools,collections
from pathlib import Path
import numpy as np
from prepare import P,read,write,sha
sys.path.insert(0,str(P/'deps'))
from nltk.stem import PorterStemmer
PS=PorterStemmer()
def normalized(x):
    x=x.replace(",","").lower().translate(str.maketrans("","",string.punctuation));return " ".join(re.sub(r"\b(a|an|the|and)\b"," ",x).split())
def f1(x,y):
    a=[PS.stem(w) for w in normalized(x).split()];b=[PS.stem(w) for w in normalized(y).split()]
    shared=sum((collections.Counter(a)&collections.Counter(b)).values())
    return 2*shared/(len(a)+len(b)) if shared else 0.
def official(x,y,cat):
    if cat==3:y=y.split(';')[0].strip()
    if cat!=1:return f1(x,y)
    return sum(max(f1(t,w) for t in x.split(',')) for w in y.split(','))/len(y.split(','))
def hits(r,g,k,session=False):
    rr=[j for j,x in enumerate(r[:k]) if x in g]
    discount=lambda i:1/math.log2(i+2)
    alt=lambda i:1 if i==0 else 1/math.log2(i+1)
    dcg=lambda fx:sum(fx(i) for i in rr)/sum(fx(i) for i in range(min(k,len(g))))
    return {f'any@{k}':bool(rr),f'all@{k}':len(rr)==len(g),f'recall@{k}':len(rr)/len(g),f'ndcg@{k}':dcg(discount),**({f'official_ndcg@{k}':dcg(alt)} if session else {})}
def contrast(rows,arm,metric):
    conv=sorted({q.split(':')[0] for q in rows});delta=np.array([x['graph'][metric]-x[arm][metric] for x in rows.values()],dtype=float);ids=list(rows)
    group=np.array([[sum(delta[j] for j,k in enumerate(ids) if k.split(':')[0]==c),sum(k.split(':')[0]==c for k in ids)] for c in conv])
    g,n=group.T;rng=np.random.default_rng(261118);sel=rng.integers(len(n),size=(10000,len(n)));boot=g[sel].sum(axis=1)/n[sel].sum(axis=1)
    signs=np.asarray(list(itertools.product([-1,1],repeat=len(n))))
    return dict(n=len(rows),delta=float(delta.mean()),ci=np.quantile(boot,[.025,.975]).tolist(),p_cluster=float(np.mean(np.abs(signs@g)>=abs(g.sum())-1e-10)),wins=int(sum(delta>1e-8)),loss=int(sum(delta< -1e-8)),macro=float(np.mean(g/n)),by_conversation={c:dict(n=int(z[1]),delta=float(z[0]/z[1])) for c,z in zip(conv,group)})
def aggregate(rows):
    arms=list(next(iter(rows.values())));metrics=list(next(iter(rows.values()))[arms[0]])
    return {a:{m:float(sum(x[a][m] for x in rows.values())/len(rows)) for m in metrics} for a in arms}
def main():
    gold=read('gold.json');r=json.loads(gzip.decompress((P/'predictions.json.gz').read_bytes()))
    lock=read('prediction_lock.json')
    for f,h in lock['sha256'].items():assert sha((P/f).read_bytes())==h
    info={c['id']:{t['id'] for t in c['turns']} for c in read('input.json')};allrows={'turn':{},'session':{}};hasbad=collections.Counter();single=read("query_owner.json")
    for i,by_arm in r.items():
        a=gold[i]
        if a['cat'] not in [1,2,3,4]:continue
        tid=set(a['evidence']);sid={"session_"+m[1] for x in tid if (m:=re.match(r"D(\d+)",x))}
        for scope,gg,z in [('turn',tid,0),('session',sid,1)]:
            if not gg or (z==0 and not gg<=info[i.split(':')[0]]):
                hasbad[scope]+=1;continue
            row={}
            for arm,v in by_arm.items():
                rank=v[z];m={};assert len(rank)==len(set(rank))
                for k in (1,3,5,10):m.update(hits(rank,gg,k,session=z==1))
                m['mrr@10']=next((1/j for j,e in enumerate(rank[:10],1) if e in gg),0)
                row[arm]=m
            allrows[scope][i]=row
    total={}
    for scope,rows in allrows.items():
        total[scope]={'n':len(rows),'metrics':aggregate(rows),'contrasts':{a:{m:contrast(rows,a,m) for m in ('all@5','any@5','all@10','mrr@10')} for a in ('flat','attribution','placebo','fusion','bm25')},'subgroups':{}}
        for attr,keep in [('unique_owner',lambda k:single[k]),('multi_evidence',lambda k:len(set(gold[k]['evidence']))>1)]:
            part={k:v for k,v in rows.items() if keep(k)}
            total[scope]['subgroups'][attr]=dict(n=len(part),all5=contrast(part,'flat','all@5'))
    (P/'retrieval_scores.json.gz').write_bytes(gzip.compress(json.dumps(allrows,separators=(',',':')).encode(),mtime=0))
    write('retrieval_results.json',dict(results=total,excluded=dict(hasbad)))
def reader():
    result=read("reader_output.json");assert read("reader_receipt.json")["reader_sha"]==sha((P/"reader_output.json").read_bytes())
    gold=read("gold.json");rows={}
    for i,arms in result.items():
        y=gold[i];rows[i]={a:dict(f1=official(v["answer"],y['answer'],y['cat']),em=int(normalized(v['answer'])==normalized(y['answer'])),tokens=v['tokens'],truncated=int(v['truncated'])) for a,v in arms.items()}
    write("reader_scores.json",rows);write('reader_results.json',dict(n=len(rows),means=aggregate(rows),contrasts={a:contrast(rows,a,"f1") for a in ('flat','fusion','bm25','placebo')},by_cat={str(c):{"n":sum(gold[k]["cat"]==c for k in rows),"means":aggregate({k:v for k,v in rows.items() if gold[k]["cat"]==c})} for c in range(1,5)}))
if __name__=="__main__":
    if 'reader' in sys.argv:reader()
    else:main()