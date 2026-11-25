from cfg import D,load,save,sha_file
paths=sorted(p for p in D.iterdir() if p.is_file() and p.name!="manifest.json")
z={"files":{p.name:sha_file(p) for p in paths},"n":len(paths),"bytes":sum(p.stat().st_size for p in paths)}
p=D/"manifest.json"
if p.exists():assert load(p)==z
else:save(p,z)
print(z["n"],z["bytes"],sha_file(p))
