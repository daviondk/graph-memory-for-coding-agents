"""Fit on disjoint repositories. Prediction never receives the lookahead window or its labels."""
import gzip, hashlib, json, math, os, sys
from pathlib import Path
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
import numpy as np

HERE = Path(__file__).resolve().parent
PACK = HERE.parents[1] / "memory_session5" / "packets"
sys.path.insert(0, str(PACK))
from common import advance, groups, newmeta, pages, rows, rel, success, STOP
from policy import CAP, DIMS, gen_features, order, unique_span, wordset
from pipeline import future

def sha(s):
    return hashlib.sha256(s if isinstance(s, bytes) else s.encode()).hexdigest()
def save(name, obj):
    (HERE/name).write_text(json.dumps(obj, ensure_ascii=False, indent=1), encoding="utf8")
def read(name):
    return json.loads((HERE/name).read_bytes())
def packed(d, line):
    d.write(json.dumps(line,ensure_ascii=True,separators=(",",":"))+"\n")
def all_files():
    return [p for base in [PACK/"source/train",PACK/"source/test",PACK/"transfer/source"] for p in sorted(base.glob("*.gz"))]
def prepare():
    seen=set(); projects=set(); index=[]
    for k,p in enumerate(all_files()):
        ids=[]
        for o in rows(p):
            i=o["instance"]
            if i in seen: continue
            seen.add(i);ids.append(i);projects.add(i.split(".")[0])
        index.append(dict(file=str(p), ids=ids, sha=sha(p.read_bytes())))
    repos=sorted(projects,key=lambda x:sha("round2edit|"+x))
    save("split.json",dict(test=repos[::3],all=repos,shards=index))
    save("method_lock.json",{n:sha((HERE/n).read_bytes()) for n in ["PROTOCOL.md","experiment.py","split.json"]}|
         {str(PACK/n):sha((PACK/n).read_bytes()) for n in ["common.py","pipeline.py","policy.py"]})

def changed_lines(args, state, path):
    old=args.get("old_str");new=args.get("new_str","")
    if not isinstance(old,str) or not old or not isinstance(new,str): return None,None
    blocks=state.get(path,{})
    start=None
    for ns in groups(blocks):
        text="\n".join(blocks[j][0] for j in ns)
        idx=text.find(old)
        if idx<0:continue
        if start is not None or text.find(old,idx+1)>=0:return None,None
        start=ns[0]+text[:idx].count("\n")
    if start is None:return None,None
    oldlines=old.split("\n");newlines=new.split("\n")
    common=0
    for x,y in zip(oldlines,newlines):
        if x!=y:break
        common+=1
    return start+min(common,len(newlines)-1),(start,start+len(oldlines)-1,len(newlines)-len(oldlines))
def write_event(history,event,state,step):
    cmd,args,feedback=event
    if cmd not in ("str_replace_editor","str_replace_based_edit_tool","edit_file") or not isinstance(args,dict):return
    path=rel(args.get("path"));op=args.get("command")
    if not path:return
    edited=success(op,path,feedback)
    if not edited and op not in ("insert","undo_edit","create"):return
    anchor,bounds=changed_lines(args,state,path) if edited else (None,None)
    for h in history:
        if h[0]!=path or h[1] is None:continue
        if not bounds or bounds[0]<=h[1]<=bounds[1]:h[1]=None
        elif h[1]>bounds[1]:h[1]+=bounds[2]
    if edited:
        old=wordset(str(args.get("old_str","")))-STOP
        new=wordset(str(args.get("new_str","")))-STOP
        history.insert(0,[path,anchor,step,new-old,old-new]);del history[2:]
def bucket(distance):
    return sum(distance>k for k in [0,3,12,36,100])
def extra(r,hist,step,paths,issue_seed):
    p,a,b,_,body=r; words=wordset(body)-STOP
    flat=[];edges=[];sign=[];fake=[]
    for j in range(2):
        if j>=len(hist):
            flat.extend([7,0,6,0]);edges.append(6);fake.append(6);sign.extend([0,0]);continue
        hp,n,when,adds,dels=hist[j];d=6 if n is None else bucket(max(a-n,0,n-b))
        flat.extend([min(6,step-when),int(p==hp),d,min(4,len(words&(adds|dels)))])
        edges.append(d if p==hp else 6)
        alternatives=[x for x in paths if x!=hp]
        other=alternatives[int(sha(f"{issue_seed}/{when}/{hp}")[:8],16)%len(alternatives)] if alternatives else hp
        fake.append(d if p==other else 6)
        sign.extend([min(4,len(words&adds)),min(4,len(words&dels))])
    return flat+edges+sign+fake

EXTRA=[8,2,7,5]*2+[7]*2+[5]*4+[7]*2
ARMS={"base":list(range(17)),"flat":list(range(25)),"address":list(range(27)),
      "full":list(range(31)),"placebo":list(range(25))+[31,32]+list(range(27,31))}
def run_shard(args):
    mode,k=args;s=read("split.json"); shard=s["shards"][k];p=Path(shard["file"])
    assert sha(p.read_bytes())==shard["sha"]
    ids=set(shard["ids"]);held=set(s["test"])
    model=read("model.json") if mode=="predict" else None
    with gzip.open(HERE/f"{mode}_{k:02}.jsonl.gz","wt",encoding="utf8",compresslevel=2) as out:
        for o in rows(p):
            i=o["instance"];repo=i.split(".")[0]
            if i not in ids or (repo in held)!=(mode!="train"):continue
            ids.remove(i)
            hist=[];states={"rebase":{}};meta=newmeta();events=o["events"]
            for t,event in enumerate(events,1):
                write_event(hist,event,states["rebase"],t)
                advance(states,meta,event,t)
                if t%4 or t>=len(events):continue
                if mode!="predict":
                    target=future(events,t)
                    if not target or not target[2]:continue
                rr=pages(states["rebase"]);indices=order(rr,meta)[:CAP]
                if mode in ("train","gold"):
                    span=unique_span(rr,target[0],target[1]);positive=span[0] if span else -1
                    if mode=="gold":
                        packed(out,[i,t,list(span or []),positive in indices]);continue
                paths=sorted(states["rebase"])
                if mode=="train":
                    indices=[idx for idx in indices if idx==positive or (idx+o["row"]+t)%4==0]
                ff=[gen_features(rr[idx],meta,t,o["issue"])+extra(rr[idx],hist,t,paths,i) for idx in indices]
                if mode=="train":
                    for idx,features in zip(indices,ff):
                        packed(out,[features,int(idx==positive)])
                else:
                    pred={"recent":indices[:3]}
                    if ff:
                        f=np.asarray(ff,dtype=int)
                        for arm,cols in ARMS.items():
                            scores=np.zeros(len(ff))
                            for c,w in zip(cols,model[arm]):scores+=np.take(w,f[:,c])
                            pred[arm]=[indices[j] for j in np.argsort(-scores,kind="stable")[:3]]
                    packed(out,[i,t,len(hist),pred])
    return k
def parallel(mode):
    with ProcessPoolExecutor(4) as ex:list(ex.map(run_shard,[(mode,k) for k in range(len(all_files()))]))
def fit():
    parallel("train")
    pairs=[r for p in sorted(HERE.glob("train_*.gz")) for r in rows(p)]
    X=np.array([r[0] for r in pairs],dtype=np.int16); y=np.array([r[1] for r in pairs],dtype=float)
    weight=np.where(y,1.,4.);w=weight/weight.sum();model={}
    for arm,cols in ARMS.items():
        dims=np.array(DIMS+EXTRA)[cols];offset=np.cumsum([0,*dims[:-1]])
        keys=X[:,cols]+offset
        coef=np.zeros(sum(dims));inter=np.log(np.sum(w*y)/np.sum(w*(1-y)))
        for it in range(120):
            z=np.clip(inter+coef[keys].sum(axis=1),-25,25)
            err=(1/(1+np.exp(-z))-y)*w
            grad=np.bincount(keys.ravel(),weights=np.repeat(err,len(cols)),minlength=len(coef))
            coef-=4*(grad+0.0005*coef);inter-=4*sum(err)
        model[arm]=[coef[l:l+d].tolist() for d,l in zip(dims,offset)]
    save("model.json",model);save("training.json",dict(rows=len(y),pos=int(y.sum())))
def main():
    prepare();fit();parallel("predict")
    save("prediction_lock.json",{p.name:sha(p.read_bytes()) for p in [HERE/"method_lock.json",HERE/"model.json",*sorted(HERE.glob("predict_*.gz"))]})
    parallel("gold")
if __name__=="__main__":main()

