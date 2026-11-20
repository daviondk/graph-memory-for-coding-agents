"""Build a third, project-disjoint public SWE-smith cohort before seeing new labels."""
import collections,gzip,hashlib,json,sys
from pathlib import Path
D=Path(__file__).resolve().parent
sys.path.insert(0,str(D.parent/"context"))
import acquire as a
import confirm_acquire as b
REPOS=set("getmoto__moto encode__starlette Cog-Creators__Red-DiscordBot benoitc__gunicorn bottlepy__bottle scrapy__scrapy tweepy__tweepy django__channels tornadoweb__tornado pallets__flask django__daphne cool-RR__PySnooper alanjds__drf-nested-routers".split())
def main():
    assert not (REPOS&(a.SAFE|a.ALLOWED|b.REPOS))
    old=set()
    for p in (a.OLD/"source").glob("*.gz"):
        with gzip.open(p,"rb") as f:old.update(json.loads(l)["instance"] for l in f)
    shards=json.loads((a.P/"shards.json").read_bytes());paths=[];opts=collections.defaultdict(list)
    for k,ref in enumerate(shards):
        path=a.OLD/".scratch"/Path(ref["path"]).name;paths.append(path)
        with path.open("rb") as f:assert hashlib.file_digest(f,"sha256").hexdigest()==ref["lfs"]["oid"]
        pf=a.pq.ParquetFile(path);n=0
        for batch in pf.iter_batches(columns=["instance_id","traj_id"]):
            for r in batch.to_pylist():
                i=r["instance_id"]
                if i.split(".")[0] in REPOS and i not in old:opts[i].append((a.h(f"r3readorwrite|{r['traj_id']}|{k}|{n}"),k,n))
                n+=1
        pf.close()
    cap=collections.Counter();sel=[]
    for i in sorted(opts,key=lambda i:a.h("r3utility|"+i)):
        project=i.split(".")[0]
        if cap[project]<24:cap[project]+=1;sel.append([i,*min(opts[i])[1:]])
    (D/"selection.json").write_text(json.dumps(sel),encoding="utf8");chosen={(k,j) for i,k,j in sel};actual=collections.Counter()
    for k,path in enumerate(paths):
        pf=a.pq.ParquetFile(path);n=0
        with gzip.open(D/f"source_{k}.jsonl.gz","wt",encoding="utf8",compresslevel=3) as f:
            for batch in pf.iter_batches(batch_size=24,columns=["instance_id","traj_id","messages","model"],use_threads=False):
                for j in range(batch.num_rows):
                    if (k,n) in chosen:
                        item=a.decode(batch.slice(j,1).to_pylist()[0],k,n)
                        if item:f.write(json.dumps(item,separators=(",",":"))+"\n");actual[item["instance"].split(".")[0]]+=1
                    n+=1
        pf.close()
    (D/"acquisition.json").write_text(json.dumps({"considered":len(sel),"actual":actual,"sources":shards},indent=1));print(sum(actual.values()),len(actual))
if __name__=="__main__":main()
