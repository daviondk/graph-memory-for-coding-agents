"""Measure two exact incremental graph alternatives, with per-node vocabulary already resident."""
from collections import defaultdict,Counter
import gc,gzip,hashlib,json,random,statistics,tracemalloc
from pathlib import Path
import numpy as np
from incremental import EventGraph,record,encode
from incremental_precise import cycles
D=Path(__file__).resolve().parent
class Lean:
    def __init__(self,live):
        self.live=live;self.roots=defaultdict(list);self.nodes=[];self.edges=[];self.out=[];self.df=Counter()
    def add(self,c):
        j=len(self.nodes);root=c["root"]
        self.edges.append([]);self.out.append(set())
        if root:
            owners=self.roots[root];weight=1/(len(owners)+1)
            if self.live:
                for owner in owners:
                    self.edges[owner]=[(src,a,weight) for src,a,_ in self.edges[owner]]
            for src,prior_node in enumerate(self.nodes):
                if root in prior_node["words"]:
                    for words,antecedent in prior_node["history"]:
                        if root in words:
                            self.edges[j].append((src,antecedent,weight));self.out[src].add(j)
            owners.append(j)
        relevant=c["words"] & self.roots.keys()
        if relevant:
            for words,a in c["history"]:
                for word in words&relevant:
                    owners=self.roots[word];w=1/len(owners)
                    for target in owners:
                        if target!=j:self.edges[target].append((j,a,w));self.out[j].add(target)
        self.nodes.append(c);self.df.update(c["words"])
    def view(self):
        if self.live:return self.nodes,self.edges,self.out,self.df
        rows=[[(s,a,1/len(self.roots[node["root"]])) for s,a,_ in e] for node,e in zip(self.nodes,self.edges)]
        return self.nodes,rows,self.out,self.df

def trial(task,seq,mem):
    nodes=[record(t) for t in seq]
    factories={"index":EventGraph,"scan":lambda:Lean(False),"live":lambda:Lean(True)}
    units={k:f() for k,f in factories.items()}
    for j,n in enumerate(nodes,1):
        ref=encode(seq[:j])
        for g in units.values():
            g.add(n);assert g.view()==ref
    del units,ref,g
    def run(mode,kind):
        if kind=="rebuild":
            if mode=="final":return encode(seq)
            for j in range(1,len(seq)+1):res=encode(seq[:j])
            return res
        g=factories[kind]()
        for n in nodes:
            g.add(n)
            if mode=="each":res=g.view()
        if mode=="final":res=g.view()
        return g,res
    arms=[(mode,name) for mode in ("each","final") for name in ("rebuild","index","scan","live")]
    rng=random.Random("lean|"+str(task));rng.shuffle(arms)
    times=defaultdict(list);space={}
    for ii in range(3):
        order=arms if not ii%2 else list(reversed(arms))
        for mode,name in order:
            key=mode+"_"+name;start=cycles();run(mode,name);times[key].append(cycles()-start)
    if mem:
        for kind in ("rebuild","index","scan","live"):
            gc.collect();tracemalloc.start();outcome=run("final",kind)
            space[kind]=list(tracemalloc.get_traced_memory());tracemalloc.stop();del outcome
    return times,space
def main():
    src=D.parent/"encoder/blind.jsonl.gz";hashof=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    (D/"lean_lock.json").write_text(json.dumps({p.name:hashof(p) for p in [src,D/"LEAN_RU.md",Path(__file__),D/"incremental_precise.py",D/"incremental.py",D/"memory.py"]}),encoding="utf8")
    rows=list(map(json.loads,gzip.open(src,"rt",encoding="utf8")));by=defaultdict(list)
    for r in rows:by[r["panel"]].append(r)
    memids={(r["panel"],r["idx"]) for a in by.values() for r in sorted(a,key=lambda r:hashlib.sha256(("r4incmem|"+str(r["idx"])).encode()).digest())[:8]}
    logs=[]
    for r in rows:
        p=(r["panel"],r["idx"]);texts=r["candidates"]
        orders={"listed":texts,"shuffled":[t for _,t in sorted(enumerate(texts),key=lambda z:hashlib.sha256(("r4inc|"+str(z[0])+z[1]).encode()).digest())]}
        for label,seq in orders.items():
            t,m=trial(p,seq,p in memids and label=="listed")
            logs.append(dict(project=r["project"],id=p,order=label,n=len(seq),cycles=t,memory=m))
    (D/"lean_items.json.gz").write_bytes(gzip.compress(json.dumps(logs,separators=(",",":")).encode(),mtime=0))
    res={}
    for label in orders:
        items=[v for v in logs if v["order"]==label];by=defaultdict(list)
        for v in items:by[v["project"]].append(v)
        keys=sorted(items[0]["cycles"]);mat=np.array([[sum(statistics.median(x["cycles"][k]) for x in vs) for k in keys] for vs in by.values()]);b=mat[np.random.default_rng(113).integers(len(mat),size=(10000,len(mat)))].sum(axis=1);s=mat.sum(axis=0)
        pairs={}
        for mode in ("each","final"):
            for a,base in [("rebuild","index"),("rebuild","scan"),("rebuild","live"),("index","live"),("scan","live")]:
                i,j=[keys.index(mode+"_"+k) for k in (a,base)];pairs[mode+"_"+a+"_over_"+base]={"ratio":s[i]/s[j],"ci":np.quantile(b[:,i]/b[:,j],[.025,.975]).tolist()}
        res[label]=dict(n=len(items),checkpoints=sum(i["n"] for i in items),pairs=pairs,cycles=dict(zip(keys,[float(x) for x in s])))
    ms=[x["memory"] for x in logs if x["memory"]]
    res["median_live_bytes"]={k:statistics.median(x[k][0] for x in ms) for k in ms[0]}
    (D/"lean_results.json").write_text(json.dumps(res,indent=2),encoding="utf8");print(res["listed"]["pairs"],res["median_live_bytes"])
if __name__=="__main__":main()

