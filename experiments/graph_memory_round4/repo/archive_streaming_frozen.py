"""Compare exact append-only graph maintenance with rebuilding each prefix of observed declarations."""
from experiment import *
from collections import defaultdict,Counter
from data_io import panel_name, rows
from memory import record
import pyarrow.parquet as pq
import gc
class AppendGraph:
    def __init__(self):
        self.documents=[];self.roots=defaultdict(set);self.incoming=[];self.outgoing=[];self.df=Counter()
    def observe(self,raw):
        src=len(self.documents);c=record(raw);name=c["root"]
        self.documents.append(c);self.incoming.append([]);self.outgoing.append(set());self.df.update(c["words"])
        if name:
            self.roots[name].add(src)
            for j,d in enumerate(self.documents[:-1]):
                if name not in d["words"]:continue
                for symbols,prior in d["history"]:
                    if name in symbols:
                        self.incoming[src].append((j,prior));self.outgoing[j].add(src)
        relevant=c["words"]&self.roots.keys()
        if relevant:
            for symbols,prior in c["history"]:
                for tok in symbols&relevant:
                    for dest in self.roots[tok]:
                        if dest!=src:
                            self.incoming[dest].append((src,prior));self.outgoing[src].add(dest)
    def snapshot(self):
        inp=[[(src,prior,1/len(self.roots[self.documents[dst]["root"]])) for src,prior in events] for dst,events in enumerate(self.incoming)]
        return self.documents,inp,self.outgoing,self.df
def edge_key(edges):
    return tuple(Counter(e) for e in edges)
def run(text,variant,audit=False):
    record.cache_clear();cpu0=time.process_time();wall0=time.perf_counter();states=[]
    if variant=="incremental":
        g=AppendGraph()
        for raw in text:
            g.observe(raw)
            s=g.snapshot()
            if audit:states.append((s[1],[set(z) for z in s[2]],s[3].copy()))
    elif variant=="rebuild":
        for i in range(len(text)):
            s=encode(text[:i+1])
            if audit:states.append((s[1],s[2],s[3]))
    else:
        s=encode(text)
    return s,states,(time.process_time()-cpu0,time.perf_counter()-wall0)
def main():
    paths=sorted((D/"archive_inputs").glob("*.parquet"));ids={}
    for p in paths:
        panel=panel_name(p.stem)
        ids[panel]=sorted(sorted(range(pq.ParquetFile(p).metadata.num_rows),key=lambda j:hashstr(f"incremental|{panel}|{j}"))[:60])
    write("incremental_lock.json",{"ids":ids,"sha":{n:sha(D/n) for n in ("INCREMENTAL_PROTOCOL_RU.md","incremental.py","memory.py","models.pkl")}})
    with (D/"models.pkl").open("rb") as f:model=pickle.load(f)[3,"graph"]
    records=[]
    for p in paths:
        panel=panel_name(p.stem);wanted=set(ids[panel])
        for i,r in enumerate(rows(p,["repo_name","code","context"])):
            if i not in wanted:continue
            order=sorted(range(len(r["context"])),key=lambda j:hashstr(f"incremental|{panel}|{i}|{j}"))[:20]
            text=[r["context"][j] for j in order];q="\n".join(r["code"].split('\n')[-3:])
            which=sorted(("batch","incremental","rebuild"),key=lambda k:hashstr(f"order|{panel}|{i}|{k}"))
            got={k:run(text,k) for k in which}
            batch,inc,reb=(got[k][0] for k in ("batch","incremental","rebuild"))
            for s,t in zip(run(text,"incremental",True)[1],run(text,"rebuild",True)[1]):
                assert edge_key(s[0])==edge_key(t[0]) and s[1]==t[1] and s[2]==t[2]
            assert edge_key(batch[1])==edge_key(inc[1])
            x,y=features(q,batch,3),features(q,inc,3)
            assert np.allclose(x,y,atol=1e-6,rtol=1e-7)
            s,t=model.predict_proba(x)[:,1],model.predict_proba(y)[:,1]
            assert np.array_equal(s,t)
            nr=Counter(d["root"] for d in batch[0] if d["root"])
            records.append([panel,i,r["repo_name"],len(text),sum(map(len,inc[1])),max(nr.values(),default=0),{k:got[k][2] for k in ("batch","incremental","rebuild")}])
    dest=D/"incremental.jsonl.gz"
    with gzip.open(dest,"wt",encoding="utf8") as f:
        for z in records:f.write(json.dumps(z,separators=(",",":"))+"\n")
    projects=sorted({z[2] for z in records});times=np.array([z[-1]["rebuild"]+z[-1]["incremental"]+z[-1]["batch"] for z in records])
    pids=np.array([projects.index(z[2]) for z in records]);pc=np.stack([times[pids==j].sum(axis=0) for j in range(len(projects))]);rng=np.random.default_rng(261118)
    boot=pc[rng.integers(0,len(pc),size=(10000,len(pc)))].sum(axis=1);us=boot[:,0]/boot[:,2]
    nz=times[:,2]>0
    write("incremental_results.json",{"rows":len(records),"projects":len(projects),"events":sum(z[3] for z in records),"edges_last":sum(z[4] for z in records),"episodes_ambiguous_root":sum(z[5]>1 for z in records),"time_order":["rebuild_cpu","rebuild_wall","incremental_cpu","incremental_wall","one_batch_cpu","one_batch_wall"],"times":times.sum(axis=0).tolist(),"speedup_total":times[:,0].sum()/times[:,2].sum(),"speedup_cluster_ci":np.quantile(us,[.025,.975]).tolist(),"median_wall_speedup":float(np.median(times[:,1]/times[:,3])),"median_cpu_speedup_nonzero":float(np.median(times[nz,0]/times[nz,2])),"nonzero_cpu_pairs":sum(map(int,nz)),"ranks_identical":len(records),"sha_data":sha(dest)})
if __name__=="__main__":main()
