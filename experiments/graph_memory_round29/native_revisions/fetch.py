"""Fetch the released ROPES contrasts without executing any dataset code."""
import hashlib,json,zipfile
from pathlib import Path
from urllib.request import urlopen
REV="e2b87316ba7b30093bc9ffbc340e6550cab79f67"
BASE=f"https://raw.githubusercontent.com/allenai/contrast-sets/{REV}/ropes/"
ROOT=Path(__file__).resolve().parent
CACHE=Path("D:/CodexResearch/x20-r29-ropes")/REV
FILES={"original":"data/ropes_contrast_set_original_032820.json","edits":"data/ropes_contrast_set_032820.json",
       "before":"predictions/predictions_original_032820.json","after":"predictions/predictions_contrast_set_032820.json",
       "evaluation":"evaluate_contrast_set.py"}
def read(name):return json.loads((CACHE/FILES[name]).read_bytes())
def checksum(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def save(name,data):(ROOT/name).write_text(json.dumps(data,sort_keys=True,ensure_ascii=False,indent=2)+"\n",encoding="utf8")
if __name__=="__main__":
    rec={}
    for key,relative in FILES.items():
        p=CACHE/relative;p.parent.mkdir(exist_ok=True,parents=True)
        if not p.exists():
            with urlopen(BASE+relative,timeout=30) as r:raw=r.read()
            p.write_bytes(raw)
        rec[key]={"source":BASE+relative,"bytes":p.stat().st_size,"sha":checksum(p)}
    save("sources.json",rec)

