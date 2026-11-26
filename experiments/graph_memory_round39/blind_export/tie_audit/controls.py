"""Secondary contextualization after the direct midrank contrast, with sealed R39 baselines."""
from pathlib import Path
import gzip
import json
import sys
D=Path(__file__).resolve().parent
src=D.parent/"author_baseline"
sys.path.insert(0,str(src))
from grade import summarize
from panel import read,sha
old=read(D.parent/"repo_crossfit/outcomes.json.gz")
new=read(D/"outcomes.json.gz")
assert old.keys()==new.keys()
for q,r in new.items():
    assert old[q]["metrics"]["proposed"]==r["metrics"]["original"]
    for k in ("bge","bge_seen","union_seen"):
        r["metrics"][k]=old[q]["metrics"][k]
res=summarize(new,"midrank")
res["old"]=sha(D.parent/"repo_crossfit/outcomes.json.gz")
res["new"]=sha(D/"outcomes.json.gz")
(D/"secondary.json").write_text(json.dumps(res,sort_keys=True,separators=(",",":"))+"\n",encoding="utf8")
