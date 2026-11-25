from qcheck import D,sha,wr,rd
paths=sorted(p for p in D.iterdir() if p.is_file() and p.name!="manifest.json")
out={"files":{p.name:sha(p) for p in paths},"n":len(paths),"bytes":sum(p.stat().st_size for p in paths)}
p=D/"manifest.json"
if p.exists():assert rd(p)==out
else:wr(p,out)
print(out["n"],out["bytes"],sha(p))
