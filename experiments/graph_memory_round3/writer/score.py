"""Read frozen compressed memory snapshots, independently locate the future edit and score retained lines."""
import re,json,gzip
from collections import Counter,defaultdict
import numpy as np
from replay import D,DATA,read,save,old,rows
from pipeline import future
def locations(pages,path,oldtext):
    blocks=[];current=[]
    for f,lo,hi,body in sorted((row for row in pages if row[0]==path),key=lambda r:r[1]):
        if current and current[-1][0]+1!=lo:blocks.append(current);current=[]
        ls=body.split("\n");assert len(ls)==hi-lo+1
        current.extend((lo+j,s) for j,s in enumerate(ls))
    if current:blocks.append(current)
    hits=[]
    for block in blocks:
        txt="\n".join(s for n,s in block);at=txt.find(oldtext)
        while at>=0:
            ln=txt[:at].count("\n");width=1+oldtext.count("\n")
            hits.append(block[ln:ln+width]);at=txt.find(oldtext,at+1)
            if len(hits)>1:return []
    return hits[0] if hits else []
def stats(v,compare,group):
    delta=np.asarray(v)-compare;cats=sorted(set(group));mat=np.array([[sum(delta[j] for j,r in enumerate(group) if r==c),sum(r==c for r in group)] for c in cats])
    rd=np.random.default_rng(181123).integers(len(cats),size=(10000,len(cats)));b=mat[rd].sum(axis=1)
    return {"delta":float(delta.mean()),"ci":np.quantile(b[:,0]/b[:,1],[.025,.975]).tolist(),"macro":float(np.mean(mat[:,0]/mat[:,1])),
            "wins":int((delta>0).sum()),"losses":int((delta<0).sum()),"project_sums":{k:v.tolist() for k,v in zip(cats,mat)}}
def main():
    for n,h in read(D/"decision_lock.json").items():assert old.e.sha((D/n).read_bytes())==h
    records=[];used=defaultdict(Counter);steps=0;seen=set();eff=defaultdict(list)
    with gzip.open(D/"per_cut.jsonl.gz","wt",encoding="utf8") as journal:
        for k in range(8):
            taskrows={r["instance"]:r for r in rows(DATA/f"source_{k}.jsonl.gz")}
            for i,cat,cuts,usage in rows(D/f"sealed_{k}.jsonl.gz"):
                seen.add(i);target=taskrows[i]
                for a,u in usage.items():
                    mx=u.pop("retained_bytes_max",0);used[a].update(u);used[a]["max"]=max(used[a]["max"],mx)
                for t,snap in cuts:
                    steps+=1;request=future(target["events"],t)
                    if not request or not request[2]:continue
                    path,oldtext,_=request;gold=locations([cat[j] for j in snap["unbounded@0"]],path,oldtext);known=bool(gold);m={}
                    for a,indices in snap.items():
                        retained={}
                        for j in indices:
                            f,lo,hi,body=cat[j]
                            if f==path:retained.update((lo+n,s) for n,s in enumerate(body.split("\n")))
                        matches=[retained.get(n)==s for n,s in gold];m[a]=[int(known and all(matches)),sum(matches)/len(matches) if known else 0.,int(known and matches[0])]
                    r=[i,t,len(gold),m];records.append(r);journal.write(json.dumps(r,separators=(",",":"))+"\n")
    groups=[x[0].split(".")[0] for x in records];keys=list(records[0][-1]);solutions={}
    for a in keys:
        ar=np.array([x[-1][a] for x in records]);solutions[a]={"hits":int(ar[:,0].sum()),"line_fraction":float(ar[:,1].mean()),"start_hits":int(ar[:,2].sum()),"usage":dict(used[a])}
        if "typed" not in a and "unbounded" not in a:
            new="typed@"+a.split("@")[1];bs=np.array([x[-1][new] for x in records]);solutions[a]["typed_minus"]={metric:stats(bs[:,j],ar[:,j],groups) for j,metric in enumerate(("whole","fraction","start"))}
    save(D/"results.json",{"n":len(records),"projects":len(set(groups)),"instances":len(seen),"included":len(set(x[0] for x in records)),"cuts":steps,"reachable":sum(bool(x[2]) for x in records),"arms":solutions})
if __name__=="__main__":main()
