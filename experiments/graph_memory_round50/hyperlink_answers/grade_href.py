from contextlib import redirect_stdout
from io import StringIO
import importlib.util,json,sys
import numpy as np
from paths_href import *
sys.path.insert(0,str(D))
from verify import score

PAIRS=(("union","true"),("href","true"),("union","href"))
def summary(rows):
    names=list(ARMS);a=np.array([[v["arms"][s] for s in names] for v in rows]);delta=np.stack([a[:,names.index(x)]-a[:,names.index(y)] for x,y in PAIRS],axis=1)
    clusters,idx=np.unique([v["cluster"] for v in rows],return_inverse=True);cnt=np.bincount(idx);m=len(cnt)
    acc=np.zeros((m,*delta.shape[1:]));np.add.at(acc,idx,delta)
    rng=np.random.default_rng(470091);samples=[]
    for _ in range(100):
        draw=rng.integers(m,size=(100,m));w=np.array([np.bincount(k,minlength=m) for k in draw])
        samples.append(w@acc.reshape(m,-1)/(w@cnt)[:,None])
    ci=100*np.quantile(np.concatenate(samples).reshape(-1,*delta.shape[1:]),[.025,.975],axis=0)
    contrasts={}
    for j,(x,y) in enumerate(PAIRS):
        k=delta[:,j];contrasts[x+"-"+y]=dict(pp=(100*k.mean(0)).tolist(),ci=ci[:,j].T.tolist(),wins=(k>1e-12).sum(0).tolist(),
          losses=(k< -1e-12).sum(0).tolist(),switches=sum(v["targets"][x]!=v["targets"][y] for v in rows))
    return dict(n=len(rows),clusters=m,means={s:a[:,i].mean(0).tolist() for i,s in enumerate(names)},contrasts=contrasts)

def main():
    check();lock=get(D/"answer-seal.json");assert sha(D/"answers.json.gz")==lock["answers"] and sha(D/"input-seal.json")==lock["input"]
    ctx=get(D/"contexts.json.gz");out=get(D/"answers.json.gz");reuse=get(D/"reuse.json.gz");rows={};gold={};results={}
    author_path=VISIBLE["dev"]/"author_evaluate.py";assert sha(author_path)==get(PRIOR["dev"]/"official-source.json")["evaluator"]
    sys.modules.setdefault("ujson",json)
    spec=importlib.util.spec_from_file_location("official",author_path);auth=importlib.util.module_from_spec(spec);spec.loader.exec_module(auth)
    for split,prior in PRIOR.items():
        labels=get(prior/"gold.json.gz");assert sha(prior/"gold.json.gz")==get(prior/"manifest.json")["files"]["gold.json.gz"];gold.update(labels)
        arms={a:{} for a in ARMS}
        for q,(truth,titles,refs) in labels.items():
            v=ctx[q];assert v["split"]==split;targets={};marks=set(refs);scores={}
            for a,(i,k,n) in v["refs"].items():
                ans=out[k]["answer"];arms[a][q]=ans;targets[a]=i;em,f1=score(ans,truth)
                m=dict(em=0.,f1=0.,prec=0.,recall=0.);auth.update_answer(m,ans,truth);assert m["em"]==em and abs(m["f1"]-f1)<1e-12
                used={titles[i],titles[v["seed"]]};scores[a]=[em,f1,int(marks<=used),len(marks&used)/len(marks)]
            rows[q]=dict(split=split,cluster=v["cluster"],targets=targets,arms=scores)
        sel=[v for v in rows.values() if v["split"]==split];res=summary(sel);res["official"]={}
        al=VISIBLE[split]/("replication-aliases.jsonl" if split=="train" else "grade-aliases.jsonl")
        for i,a in enumerate(ARMS):
            pp=P/"official-pred.json";pp.write_text(json.dumps(dict(answer=arms[a],sp={},evidence={})),encoding="ascii")
            stdout=StringIO()
            with redirect_stdout(stdout):auth.eval(str(pp),str(VISIBLE[split]/"grade-cases.json"),str(al))
            s=stdout.getvalue();rec=json.loads(s[s.rfind("{"):])
            res["official"][a]=[rec["em"],rec["f1"]]
            assert all(abs(x-100*y)<=.00500001 for x,y in zip(res["official"][a],res["means"][a][:2],strict=True))
        records={q:v for q,v in ctx.items() if v["split"]==split}
        keys={x[1] for v in records.values() for x in v["refs"].values()}
        res["tokens"]=dict(shortened=sum(v["n"]<v["old_n"] for v in records.values()),unique=len(keys),unique_cached=len(keys&set(reuse)),
            logical_cached={a:sum(v["refs"][a][1] in reuse for v in records.values()) for a in ARMS},
            first=sum(v["first"] for v in records.values()),second=sum(v["n"] for v in records.values()),input=sum(v["refs"]["true"][2] for v in records.values()))
        results[split]=res
    put(D/"outcomes.json.gz",rows);put(D/"gold.json.gz",gold);put(D/"results.json",results)
    print([(s,v["official"],v["contrasts"]["union-true"]) for s,v in results.items()],flush=True)
if __name__=="__main__":main()
