import gzip, hashlib, json, sys
from pathlib import Path
from collections import defaultdict,Counter
H=Path(__file__).resolve().parent;W=H.parents[1];P=W/"memory_session5/packets";sys.path.insert(0,str(P))
from extract5 import pq,OLD,ALLOWED,decode
SAFE=set("""marshmallow-code__apispec lepture__mistune getnikola__nikola kurtmckee__feedparser weaveworks__grafanalib graphql-python__graphene pdfminer__pdfminer cookiecutter__cookiecutter Mimino666__langdetect gruns__furl pudo__dataset sloria__environs Knio__dominate madzak__python-json-logger buriy__python-readability martinblech__xmltodict vi3k6i5__flashtext pytest-dev__iniconfig pyparsing__pyparsing gruns__icecream kennethreitz__records termcolor__termcolor mewwts__addict pwaller__pyfiglet datamade__usaddress borntyping__python-colorlog""".split())
def h(x):return hashlib.sha256(x.encode()).hexdigest()
def main():
    assert not (SAFE & ALLOWED)
    old={s for rs in json.load(open(P/"selection.json")).values() for s,k,i in rs}
    old.update(s for s,k,i in json.load(open(P/"transfer/selection.json")))
    old.update(s for s,k,i in json.load(open(W/"graph_memory_round2/span_memory/selection.json")))
    for f in (OLD/"source").glob("*.gz"):
        for line in gzip.open(f,"rb"):old.add(json.loads(line)["instance"])
    refs=json.loads((P/"shards.json").read_bytes());cs=defaultdict(list);srcs=[]
    for k,it in enumerate(refs):
        p=OLD/".scratch"/Path(it["path"]).name;srcs.append(p)
        with p.open("rb") as f:assert hashlib.file_digest(f,"sha256").hexdigest()==it["lfs"]["oid"]
        n=0;pf=pq.ParquetFile(p)
        for b in pf.iter_batches(columns=["instance_id","traj_id"]):
            for r in b.to_pylist():
                i=r["instance_id"]
                if i not in old and i.split(".")[0] in SAFE:cs[i].append((h(f"r3edge|{r['traj_id']}|{k}|{n}"),k,n))
                n+=1
        pf.close()
    keep=[];co=Counter()
    for i in sorted(cs,key=lambda i:h("r3edge|"+i)):
        repo=i.split(".")[0]
        if co[repo]<48:
            co[repo]+=1;keep.append((i,*min(cs[i])[1:]))
    (H/"selection.json").write_text(json.dumps(keep,indent=1))
    pairs={(k,n) for i,k,n in keep};status=Counter()
    for k,p in enumerate(srcs):
        n=0;pf=pq.ParquetFile(p)
        with gzip.open(H/f"source_{k}.jsonl.gz","wt",encoding="utf8",compresslevel=3) as out:
            for b in pf.iter_batches(batch_size=24,columns=["instance_id","traj_id","messages","model"],use_threads=False):
                for j in range(b.num_rows):
                    if (k,n) in pairs:
                        x=decode(b.slice(j,1).to_pylist()[0],k,n)
                        if x:
                            out.write(json.dumps(x,separators=(",",":"))+"\n");status[x["format"]]+=1
                        else:status["filtered"]+=1
                    n+=1
        pf.close()
    (H/"source_receipt.json").write_text(json.dumps(dict(candidates=dict(co),seen=dict(status),prior_overlap=0,sha256={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in [H/"acquire.py",H/"PROTOCOL_RU.md",H/"selection.json",*H.glob("source_*.gz")]}),indent=1))
    print(len(keep),dict(status),len(co))
if __name__=="__main__":main()
