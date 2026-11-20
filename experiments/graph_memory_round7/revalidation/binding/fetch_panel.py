from pathlib import Path
import sys
import json
from concurrent.futures import ThreadPoolExecutor
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent))
from fetch import choose, download
projects="toolz pydot mizani tabulate mpmath patsy markdown-it-py pyparsing".split()
p=HERE/"sources.json"
if not p.exists():
    rows=[r for a in ThreadPoolExecutor(6).map(choose,projects) for r in a]
    p.write_text(json.dumps(rows,indent=2)+"\n",encoding="utf8")
rows=json.loads(p.read_bytes())
list(ThreadPoolExecutor(6).map(download,rows))
print("Verified",len(rows),"wheels.")
