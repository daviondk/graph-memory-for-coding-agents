from rep_io import D,save,read,sha
files=sorted(p for p in D.iterdir() if p.is_file() and p.name!="manifest.json")
val={"n":len(files),"bytes":sum(f.stat().st_size for f in files),"files":{f.name:sha(f) for f in files}}
p=D/"manifest.json"
if p.exists():assert read(p)==val
else:save(p,val)
print(val["n"],val["bytes"],sha(p))
