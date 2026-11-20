"""Post-outcome audit of why alternate certificates had no marginal read effect on C."""
import csv
import gzip
import hashlib
import json
from collections import Counter
from pathlib import Path
from free_git import GitObjects,Snapshot

ROOT=Path(__file__).resolve().parent
lock=json.loads((ROOT/"predictions.lock.json").read_bytes())
sample=json.loads((ROOT/"sample.lock.json").read_bytes())
counts=Counter()
repos=set()
fine=[]
for g in sample["groups"]:
    repo=g["repo"];raw=(ROOT/"logs"/(repo+".jsonl.gz")).read_bytes()
    assert hashlib.sha256(raw).hexdigest()==lock["shas"][repo]
    obj=GitObjects(g["mirror"])
    try:
        for line in gzip.decompress(raw).splitlines():
            if not line: continue
            row=json.loads(line);_,old,new,s,t=row["key"];a=row["answers"]
            assert a["edge"]["cache_bytes"]<=a["free"]["cache_bytes"]
            assert a["free"]["cache"][4][0]==a["one"]["cache"][4][0]
            sources=set(one[0] for one in row["old"]["source_reads"])
            caches=a["free"]["cache"];ids=caches[3];ps=[[ids[i][0] for i in p] for p in caches[4]]
            deps=[set(p[:-1]) for p in ps]
            assert all(all(n in sources for n in d) or row["old"]["counts"].get("blob_cache_hits",0) for d in deps)
            if len(ps)<2: continue
            repos.add(repo);counts["with_multiple"]+=1
            counts["first_provider_set_subset_all_alternatives"]+=int(all(deps[0]<=d for d in deps[1:]))
            counts["first_fast"]+=int(a["one"]["fast"])
            counts["first_validated"]+=int(a["one"]["verified"])
            snap=Snapshot(obj,new)
            changed={name for name,path,sha in ids if snap.resolve(name)!=(path,sha)}
            common=set.intersection(*deps)
            rowdiag={"repo":repo,"source":s,"target":t,"before":old,"after":new,
                     "first_fast":a["one"]["fast"],"first_validated":a["one"]["verified"],
                     "changed_source":s in changed,"changed_common_provider":bool(common&changed),
                     "first_set_subset_all":all(deps[0]<=d for d in deps[1:])}
            counts["nonfast_source_changed"]+=int(not a["one"]["fast"] and s in changed)
            counts["nonfast_common_changed"]+=int(not a["one"]["fast"] and bool(common&changed))
            fine.append(rowdiag)
    finally: obj.close()
res={"summary":dict(counts),"repos_with_alternatives":sorted(repos),"rows":fine}
(ROOT/"overlap.json").write_text(json.dumps(res,indent=2),encoding="utf8")
print(res["summary"],sorted(repos))

