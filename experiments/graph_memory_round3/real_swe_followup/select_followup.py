from pathlib import Path
import hashlib,json,re,sys
from collections import Counter
D=Path(__file__).resolve().parent; P=D.parents[1]/"memory_session5/packets";sys.path.insert(0,str(P))
from extract5 import pq,BAN
O=D.parent/"real_swe"; src=O/"official_verified.parquet"
assert hashlib.sha256(src.read_bytes()).hexdigest()=="030cfd7f2a704c4c0226e7f104c725a3b41230b1d3517f9c915ad7ea5be3fa25"
prior={r["instance_id"] for r in json.loads((O/"selection.json").read_bytes())}
guard=re.compile(r"\b(?:malware|vulnerab\w*|exploit\w*|shellcode|SQL injection|cross.site scripting|attacker|weapon|pathogen|anthrax|nerve agent|ammunition|bioweapon)\b",re.I)
rows=pq.read_table(src,columns=["instance_id","repo","base_commit","problem_statement"]).to_pylist()
co=Counter();sel=[];why=Counter()
for r in sorted(rows,key=lambda x:hashlib.sha256(("r3real-followup|"+x["instance_id"]).encode()).hexdigest()):
    if r["instance_id"] in prior:why["prior"]+=1;continue
    if r["instance_id"]=="sympy__sympy-11618":why["example"]+=1;continue
    if BAN.search(r["problem_statement"]) or guard.search(r["problem_statement"]):why["screen"]+=1;continue
    if co[r["repo"]]>=32:why["stratum_cap"]+=1;continue
    sel.append(r);co[r["repo"]]+=1
assert not prior.intersection(r["instance_id"] for r in sel)
(D/"selection.json").write_text(json.dumps(sel,ensure_ascii=True,indent=1),encoding="utf8")
info={"n":len(sel),"repo":dict(co),"why":dict(why),"prior_overlap":0,"protocol_sha256":hashlib.sha256((D/"PROTOCOL_RU.md").read_bytes()).hexdigest()}
(D/"selection_receipt.json").write_text(json.dumps(info,indent=1));print(info)

