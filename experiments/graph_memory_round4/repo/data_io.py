import gzip
import hashlib
import json
import random
from collections import Counter
from pathlib import Path
import pyarrow.parquet as pq

D=Path(__file__).resolve().parent
R3=D.parents[1]/"graph_memory_round3/repo"
def write(name,obj):(D/name).write_text(json.dumps(obj,ensure_ascii=True,indent=1),encoding="utf8")
def read(name):return json.loads((D/name).read_bytes())
def sha(p):
    with Path(p).open("rb") as f:return hashlib.file_digest(f,"sha256").hexdigest()
def hashstr(s):return hashlib.sha256(s.encode()).hexdigest()
def gz(path):
    with gzip.open(path,"rt",encoding="utf8") as f:
        for line in f:yield json.loads(line)
def panel_name(name):return name.rsplit("_",1)[0]
def files(lang,split):return sorted((D/"inputs" if lang=="java" else R3/"inputs").glob(f"{lang}_*_{split}_*.parquet"))
def rows(path,cols):
    for batch in pq.ParquetFile(path).iter_batches(batch_size=24,columns=cols):
        yield from batch.to_pylist()
def make_roster():
    bins={};test_repos=set();native={}
    for lang in ("java","python"):
        groups={}
        for p in files(lang,"test"):groups.setdefault(panel_name(p.stem),[]).append(p)
        for panel,paths in groups.items():
            names=[r for p in paths for r in pq.read_table(p,columns=["repo_name"]).column(0).to_pylist()]
            test_repos.update(names);config,level=panel.split("_test_")
            ids=sorted(random.Random(f"20261003-{config}-{level}").sample(range(len(names)),500))
            native[panel]=sorted(sorted(ids,key=lambda j:hashstr(f"nativeR4|{panel}|{j}"))[:24])
            offset=0
            for p in paths:
                n=pq.ParquetFile(p).metadata.num_rows
                bins[p.stem]=[[i-offset,i] for i in ids if offset<=i<offset+n]
                offset+=n
    train=Counter()
    for p in files("java","train"):
        names=pq.read_table(p,columns=["repo_name"]).column(0).to_pylist()
        ids=[];projects=Counter()
        for j in sorted(range(len(names)),key=lambda z:hashstr(f"r4-train|{p.name}|{z}")):
            repo=names[j]
            if repo in test_repos or projects[repo]>=30:continue
            ids.append(j);projects[repo]+=1;train[repo]+=1
            if len(ids)==2500:break
        bins[p.stem]=[[j,j] for j in sorted(ids)]
    assert not set(test_repos)&set(train)
    write("roster.json",bins);write("native_roster.json",native)
    write("roster_audit.json",dict(all_test_repos=len(test_repos),train_projects=len(train),train_rows=sum(train.values()),counts={k:len(v) for k,v in bins.items()},train_overlap=0))
if __name__=="__main__":make_roster()
