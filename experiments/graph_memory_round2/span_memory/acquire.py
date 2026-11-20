"""Project the next unlabeled-by-selection cohort from the publisher shards."""
from pathlib import Path
import sys
HERE=Path(__file__).resolve().parent
PACK=HERE.parents[1]/"memory_session5/packets";sys.path.insert(0,str(PACK))
from extract5 import OLD, pq, decode, h, ALLOWED, BAN
import json, gzip, hashlib
from collections import defaultdict,Counter
def main():
    read=lambda p:json.loads(p.read_bytes())
    refs=read(PACK/"shards.json")
    forbidden={s for records in read(PACK/"selection.json").values() for s,k,j in records}
    forbidden.update(s for s,k,j in read(PACK/"transfer/selection.json"))
    hold=set(read(HERE.parent/"edit_memory/split.json")["test"])
    c=defaultdict(list);files=[]
    for k,ref in enumerate(refs):
        p=OLD/".scratch"/Path(ref["path"]).name;files.append(p)
        with p.open("rb") as raw:assert hashlib.file_digest(raw,"sha256").hexdigest()==ref["lfs"]["oid"]
        pf=pq.ParquetFile(p);idx=0
        for batch in pf.iter_batches(batch_size=1000,columns=["instance_id","traj_id"]):
            for r in batch.to_pylist():
                i=r["instance_id"]
                if i.split(".")[0] in hold and i not in forbidden and int(h("compact-s4|"+i),16)%10!=0:
                    c[i].append((h(f"r2f-trace|{i}|{k}|{idx}"),k,idx))
                idx+=1
        pf.close()
    subset=[(i,*min(c[i])[1:]) for i in sorted(c,key=lambda i:h("r2f-unseen"+i))[:700]]
    assert not forbidden.intersection(i for i,_,_ in subset)
    (HERE/"selection.json").write_text(json.dumps(subset),encoding="utf8")
    pick={(k,idx) for i,k,idx in subset};co=Counter()
    for k,p in enumerate(files):
        pf=pq.ParquetFile(p);idx=0
        with gzip.open(HERE/f"fresh_{k}.jsonl.gz","wt",encoding="utf8",compresslevel=3) as out:
            for batch in pf.iter_batches(batch_size=24,columns=["instance_id","traj_id","messages","model"],use_threads=False):
                for j in range(batch.num_rows):
                    if (k,idx) in pick:
                        x=decode(batch.slice(j,1).to_pylist()[0],k,idx)
                        if x:
                            out.write(json.dumps(x,separators=(",",":"))+"\n");co[x["format"]]+=1
                        else:co["filtered"]+=1
                    idx+=1
        pf.close();print(k,dict(co),flush=True)
    (HERE/"acquisition.json").write_text(json.dumps(co),encoding="utf8")
if __name__=="__main__":main()
