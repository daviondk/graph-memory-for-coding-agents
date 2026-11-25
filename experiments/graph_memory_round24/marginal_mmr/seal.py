from io24 import D,read,sha,save
paths=sorted(p for p in D.iterdir() if p.is_file() and p.name!="manifest.json")
val={"files":{p.name:sha(p) for p in paths},"n":len(paths),"bytes":sum(p.stat().st_size for p in paths)}
p=D/"manifest.json"
if p.exists():assert read(p)==val
else:save(p,val)
print(val["n"],val["bytes"],sha(p))
