from pathlib import Path
from collections import Counter,defaultdict
import hashlib,json,re,sys
D=Path(__file__).resolve().parent;P=D.parents[1]/"memory_session5/packets";sys.path.insert(0,str(P))
from extract5 import pq,BAN
src=Path("D:/CodexResearch/x20-round4-verified.parquet")
h=lambda s:hashlib.sha256(s.encode()).hexdigest()
rows=pq.read_table(src,columns=["instance_id","repo","base_commit","problem_statement"]).to_pylist()
assert len(rows)==500 and len({r["instance_id"] for r in rows})==500
guard=re.compile(r"\b(?:malware|vulnerab\w*|exploit\w*|shellcode|SQL injection|cross.site scripting|attacker|weapon|pathogen|anthrax|nerve agent|ammunition|bioweapon)\b",re.I)
co=Counter();selected=[];blocked=Counter()
for row in sorted(rows,key=lambda r:h("r3realverified|"+r["instance_id"])):
    q=row["problem_statement"]
    if row["instance_id"]=="sympy__sympy-11618":blocked["schema_example"]+=1;continue
    if BAN.search(q) or guard.search(q):blocked["screen"]+=1;continue
    if co[row["repo"]]>=18:continue
    co[row["repo"]]+=1;selected.append(row)
(D/"selection.json").write_text(json.dumps(selected,ensure_ascii=True,indent=1),encoding="utf8")
(D/"selection_receipt.json").write_text(json.dumps({"official":len(rows),"input_sha256":hashlib.sha256(src.read_bytes()).hexdigest(),"strata":dict(co),"blocked":dict(blocked),"n":len(selected),"protocol_sha256":hashlib.sha256((D/"PROTOCOL_RU.md").read_bytes()).hexdigest()},indent=1))
print(len(selected),dict(co),dict(blocked))
