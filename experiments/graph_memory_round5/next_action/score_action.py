"""Evaluate the unseen future location of a recorded edit without giving it to the model."""
import sys,math,re,json,gzip,itertools
from pathlib import Path
from collections import defaultdict
from infer_action import D,read,save,sha
import numpy as np
def extract(s):
    m=re.search(r"\{[^{}]*\}",s)
    if m:
        try:
            z=json.loads(m[0]);p=z["path"];n=z["line"]
            if type(n) is int and n>0 and isinstance(p,str):
                return p.strip().replace("\\","/").removeprefix("/testbed/").removeprefix("./"),n
        except (ValueError,KeyError,TypeError):pass
    return None
def evaluate(ans,p,n):return {"valid":int(ans is not None),"file":int(bool(ans and ans[0]==p)),"near5":int(bool(ans and ans[0]==p and abs(ans[1]-n)<=5)),"exact":int(bool(ans and ans[0]==p and ans[1]==n))}
def compare(items,a,b,field,byrepo):
    groups=defaultdict(list)
    for x in items:groups[x["repo"] if byrepo else x["id"]].append(x["m"][a][field]-x["m"][b][field])
    mat=np.array([(len(v),sum(v)) for v in groups.values()]); w=sum(x>0 for vals in groups.values() for x in vals);l=sum(x<0 for vals in groups.values() for x in vals)
    rng=np.random.default_rng(1811202601);s=mat[rng.integers(len(mat),size=(10000,len(mat)))].sum(axis=1)
    v=mat[:,1];n=w+l
    p=sum(abs(np.dot(v,t))>=abs(v.sum()) for t in itertools.product([-1,1],repeat=len(v)))/2**len(v) if byrepo else min(1.,2*sum(math.comb(n,j) for j in range(min(w,l)+1))/2**n)
    return dict(delta=float(v.sum()/len(items)),ci=np.quantile(s[:,1]/s[:,0],[.025,.975]).tolist(),wins=w,losses=l,p=float(p))
def main():
    ix=read("H_assignment.json");locks=read("H_decisions.json");packet=read("H_packets.json.gz");calls={}
    for n,h in read("H_input_lock.json").items():assert sha((D/n).read_bytes())==h
    assert set(locks)=={v+".json.gz" for arm in ix.values() for v in arm.values()}
    for n,h in locks.items():
        f=D/"H_calls"/n;assert sha(f.read_bytes())==h
        reply=read(f)["reply"];calls[n.split(".")[0]]=(extract(reply["choices"][0]["message"]["content"] or ""),reply["usage"])
    refs={}
    with gzip.open(D.parent/"writer/headroom.jsonl.gz","rt",encoding="utf8") as f:
        for iid,cut,when,p,n,count,*_ in map(json.loads,f):refs[iid+"|"+str(cut)]=(p,n)
    out=[]
    for x in packet:
        i=x["id"];p,n=refs[i];m={}
        for a,cid in ix[i].items():
            ans,u=calls[cid];m[a]=evaluate(ans,p,n)|dict(proposed=ans,input_tokens=u["prompt_tokens"],output_tokens=u["completion_tokens"])
        m["last"]=evaluate(x["last_address"],p,n)|dict(proposed=x["last_address"])
        out.append(dict(id=i,repo=x["repo"],m=m,ref=[p,n],changed=ix[i]["address"]!=ix[i]["terminal"]))
    assert len(out)==len({x["id"].split("|")[0] for x in out})
    def summarize(z):
        arms=list(z[0]["m"]);metrics=["valid","file","near5","exact"]
        return dict(n=len(z),repos=len({x["repo"] for x in z}),totals={a:{f:sum(x["m"][a][f] for x in z) for f in metrics} for a in arms},contrasts={a+"-"+b:{f:{"task":compare(z,a,b,f,False),"repo":compare(z,a,b,f,True)} for f in ["near5","file","exact"]} for a,b in [("address","terminal"),("terminal","editor"),("address","last")]})
    changed=[r for r in out if r["changed"]];res=dict(all=summarize(out),changed=summarize(changed) if changed else None,physical_calls=len(calls),tokens={f:sum(u[f] for a,u in calls.values()) for f in ["prompt_tokens","completion_tokens"]})
    save("H_items.json.gz",out);save("H_results.json",res);print(res["all"]["totals"],flush=True)
if __name__=="__main__":main()

