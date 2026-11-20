"""Read graph-memory inputs. Only identifiers, coordinates and data strings enter this module."""
import gzip, hashlib, itertools, json, re, sys
from pathlib import Path
from collections import Counter,defaultdict
from functools import lru_cache
import numpy as np
D=Path(__file__).resolve().parent; W=D.parents[1];F=W/"graph_memory_round2/span_memory"
sys.path.insert(0,str(F))
import budget as prev
from run import e, stream, rows, future
from policy import cost,render,wordset
def save(n,x):(D/n).write_text(json.dumps(x,ensure_ascii=True,indent=1))
def read(n):return json.loads((D/n).read_bytes())
def h(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def atomic_line(f,x):f.write(json.dumps(x,ensure_ascii=True,separators=(",",":"))+"\n")
def line_target(rr,path,old):
    slices=[];cur=[]
    for j,r in enumerate(rr):
        if r[0]!=path:continue
        if cur and rr[cur[-1]][2]+1!=r[1]:slices.append(cur);cur=[]
        cur.append(j)
    if cur:slices.append(cur)
    match=[]
    for ix in slices:
        wire="\n".join(rr[j][4] for j in ix)
        off=wire.find(old)
        if off<0:continue
        if wire.find(old,off+1)>=0:return None
        start=rr[ix[0]][1]+wire[:off].count("\n")
        end=start+old.count("\n");pid=next(j for j in ix if rr[j][1]<=start<=rr[j][2])
        match.append((path,start,end,pid))
    return match[0] if len(match)==1 else None

def kind(s):
    c=s.strip()
    if not c:return 0
    first=c.split(None,1)[0]
    if c.startswith(("def ","async def ","class ")):return 1
    if c.startswith(("#","'''",'"""')):return 2
    if c.startswith("@"):return 3
    if first in ("if","elif","else:","try:","except","finally:","for","while","with","match","case"):return 4
    if first in ("return","raise","yield","assert"):return 5
    if c.startswith(("from ","import ")):return 6
    if c in (")","]","}",");","])", "],", "),"):return 7
    if "=" in c:return 8
    return 9
DIMS=[12,12,10,7,5,6,6,3,3,3,2,2]
def feats(r,terms):
    path,lo,hi,age,body=r;lines=body.split("\n");out=[]
    assert len(lines)==hi-lo+1
    indent=lambda s:min(6,(len(s)-len(s.lstrip()))//2)
    for j,s in enumerate(lines):
        stripped=s.strip();left=lines[j-1] if j else None;right=lines[j+1] if j+1<len(lines) else None
        out.append([j,len(lines)-j-1,kind(s),indent(s),min(4,len(wordset(s)&terms)),min(5,len(s)//16),min(5,len(wordset(s))),2 if left is None else int(not left.strip()),2 if right is None else int(not right.strip()),2 if left is None else int(indent(s)<indent(left)),int(stripped.endswith(":")),int(lo%12==1)])
    return out

def fitted_line_probs(ff,model,mode):
    if mode=="flat":return np.full(len(ff),1/len(ff))
    x=np.array(ff);z=sum(np.take(a,x[:,j]) for j,a in enumerate(model["start_weights"]))
    q=np.exp(z-z.max());return q/q.sum()
def lenkey(f):
    return [str(f[2]),str(f[3]//2),str(f[10]),str(f[4]>0)]
def len_cdf(f,m,typed):
    key="|".join(lenkey(f));dist=m["length_dist"]
    if not typed:return np.array(dist["*"])
    return np.array(dist.get(key,dist.get("|".join(lenkey(f)[:2]),dist.get(lenkey(f)[0],dist["*"]))))
def gather(j):
    s=e.read("split.json");sh=s["shards"][j];ex=set(s["test"]);ids=set(sh["ids"]);pairs=[]
    for obj in rows(Path(sh["file"])):
        i=obj["instance"]
        if i not in ids or i.split(".")[0] in ex:continue
        ids.remove(i);terms=wordset(obj["issue"][:9000])
        for t,rr,idx,meta,hist,last in stream(obj):
            q=future(obj["events"],t)
            if not q or not q[2]:continue
            x=line_target(rr,q[0],q[1])
            if not x or x[3] not in idx:continue
            path,a,b,p=x;f=feats(rr[p],terms)
            pairs.append((f,a-rr[p][1],min(96,b-a+1)))
    return pairs
def train():
    from concurrent.futures import ProcessPoolExecutor
    with ProcessPoolExecutor(4) as ex:records=[r for part in ex.map(gather,range(len(e.all_files()))) for r in part]
    ofs=np.cumsum([0,*DIMS[:-1]]);dim=sum(DIMS);coef=np.zeros(dim)
    # Conditional softmax over visible candidate start lines *within* each independently estimated page.
    f=np.array([x for ff,j,hg in records for x in ff]);keys=f+ofs
    counts=np.array([len(ff) for ff,j,hg in records]);starts=np.r_[0,np.cumsum(counts)[:-1]]
    target=np.zeros(len(f));target[starts+np.array([a for ff,a,ln in records])]=1
    for step in range(180):
        z=np.exp(np.clip(coef[keys].sum(axis=1),-18,18));p=z/np.repeat(np.add.reduceat(z,starts),counts)
        err=(p-target)/len(records)
        coef-=.5*(np.bincount(keys.ravel(),weights=np.repeat(err,len(DIMS)),minlength=dim)+.001*coef)
    counts=defaultdict(lambda:np.zeros(97))
    for ff,j,ln in records:
        t=lenkey(ff[j])
        for key in ["*",t[0],"|".join(t[:2]),"|".join(t)]:counts[key][ln]+=1
    # Last bin represents 96 or more lines; our maximum connected new record is 72 lines.
    dist={"*":(counts["*"]+1)/(len(records)+97)};dist["*"][0]=0;dist["*"]/=dist["*"].sum()
    for n in [1,2,4]:
        for key,x in counts.items():
            if key=="*" or len(key.split("|"))!=n:continue
            par="*" if n==1 else "|".join(key.split("|")[:1 if n==2 else 2])
            dist[key]=(x+32*dist[par])/(x.sum()+32)
    model={"start_weights":[coef[a:a+n].tolist() for a,n in zip(ofs,DIMS)],"length_dist":{k:np.cumsum(v).tolist() for k,v in dist.items()},"n":len(records)}
    save("fine_model.json",model)
if __name__=="__main__":train()
