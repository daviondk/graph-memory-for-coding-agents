from common import *
paths=sorted(p for p in D.iterdir() if p.is_file() and p.name!="manifest.json")
val={"files":{p.name:sha(p) for p in paths},"n":len(paths),"bytes":sum(p.stat().st_size for p in paths)}
if (D/"manifest.json").exists():assert read(D/"manifest.json")==val
else:save(D/"manifest.json",val)
print(val["n"],val["bytes"],sha(D/"manifest.json"))
