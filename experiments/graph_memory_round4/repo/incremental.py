"""Maintain the round-4 candidate graph as files arrive; verify every intermediate view."""
from collections import Counter,defaultdict
from itertools import chain
from pathlib import Path
from time import process_time_ns
import gzip,hashlib,json,random,statistics
import numpy as np
from memory import record,encode

D=Path(__file__).resolve().parent
class EventGraph:
    def __init__(self):
        self.nodes=[];self.postings=defaultdict(list);self.roots=defaultdict(list)
        self.edges=[];self.out=[];self.df=Counter()
    def add(self,node):
        j=len(self.nodes);root=node["root"]
        self.nodes.append(node);self.edges.append([]);self.out.append(set())
        if root:
            for source in self.postings.get(root,()):
                self.link(source,root,[j])
            self.roots[root].append(j)
        relevant=node["words"] & self.roots.keys()
        if relevant:
            for words,prior in node["history"]:
                for symbol in words&relevant:
                    for target in self.roots[symbol]:
                        if target!=j:
                            self.edges[target].append((j,prior))
                            self.out[j].add(target)
        self.df.update(node["words"])
        for term in node["words"]:
            self.postings[term].append(j)
    def link(self,source,symbol,targets):
        for words,prior in self.nodes[source]["history"]:
            if symbol in words:
                for target in targets:
                    self.edges[target].append((source,prior));self.out[source].add(target)
    def view(self):
        edges=[]
        for n,items in zip(self.nodes,self.edges):
            weight=1/len(self.roots[n["root"]]) if items else 1.
            edges.append([(src,prior,weight) for src,prior in items])
        return self.nodes,edges,self.out,self.df

def benchmark(row,texts):
    nodes=[record(t) for t in texts]
    g=EventGraph();checks=0;edges=0
    for j,node in enumerate(nodes,1):
        g.add(node)
        target=encode(texts[:j]);now=g.view()
        assert all(c is d for c,d in zip(target[0],now[0],strict=True))
        assert target[1:]==now[1:],(row["panel"],row["idx"],j)
        checks+=1;edges+=sum(map(len,now[1]))
    postings=sum(map(len,g.postings.values()))
    def run(arm):
        if arm=="final":return encode(texts)
        if arm=="each":
            for j in range(1,len(texts)+1):enc=encode(texts[:j])
            return enc
        gg=EventGraph()
        for node in nodes:
            gg.add(node)
            if arm=="add_each":gg.view()
        if arm=="add_final":gg.view()
    arms=["each","final","add_each","add_final"]
    rng=random.Random(str((row["panel"],row["idx"])));rng.shuffle(arms)
    elapsed=defaultdict(list)
    for order in [arms,list(reversed(arms))]:
        for a in order:
            start=process_time_ns();run(a);elapsed[a].append(process_time_ns()-start)
    return {"checks":checks,"edges_over_checkpoints":edges,"postings":postings,"times_ns":{k:statistics.mean(v) for k,v in elapsed.items()}}

def main():
    src=D.parent/"encoder"/"blind.jsonl.gz"
    digest=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    lock={str(p.name):digest(p) for p in [src,Path(__file__),D/"memory.py",D/"INCREMENTAL_RU.md"]}
    (D/"incremental_lock.json").write_text(json.dumps(lock),encoding="utf8")
    items=[]
    for row in map(json.loads,gzip.open(src,"rt",encoding="utf8")):
        texts=row["candidates"]
        orders={"listed":texts,"shuffled":sorted(enumerate(texts),key=lambda item:hashlib.sha256(("r4inc|"+str(item[0])+item[1]).encode()).digest())}
        orders["shuffled"]=[t for _,t in orders["shuffled"]]
        for name,seq in orders.items():
            v=benchmark(row,seq);items.append(dict(panel=row["panel"],id=row["idx"],project=row["project"],order=name,**v))
    (D/"incremental_items.json.gz").write_bytes(gzip.compress(json.dumps(items,separators=(",",":")).encode(),mtime=0))
    results={}
    for label in ("listed","shuffled"):
        selected=[i for i in items if i["order"]==label]
        groups=defaultdict(list)
        for x in selected:groups[x["project"]].append(x)
        methods=("each","add_each","final","add_final")
        x=np.array([[sum(i["times_ns"][m] for i in group) for m in methods] for group in groups.values()])
        b=x[np.random.default_rng(7711).integers(len(x),size=(10000,len(x)))].sum(axis=1)
        total=x.sum(axis=0)
        results[label]={"n":len(selected),"projects":len(groups),"checkpoints":sum(q["checks"] for q in selected),"times_cpu_s":{k:float(v/1e9) for k,v in zip(methods,total)},"repeat_speedup":float(total[0]/total[1]),"repeat_speedup_ci":np.quantile(b[:,0]/b[:,1],[.025,.975]).tolist(),"single_ratio_new_to_base":float(total[3]/total[2]),"postings_per_task_median":statistics.median(z["postings"] for z in selected)}
    (D/"incremental_results.json").write_text(json.dumps(results,indent=2),encoding="utf8")
    print(results)
if __name__=="__main__":main()

