"""Choose every eligible untouched issue, without importing result labels."""
from pathlib import Path
from collections import Counter
import hashlib,json,re,sys

D=Path(__file__).resolve().parent
P=D.parents[1]/"memory_session5/packets";sys.path.insert(0,str(P))
from extract5 import pq,BAN
R3=D.parents[1]/"graph_memory_round3"
guard=re.compile(r"\b(?:malware|vulnerab\w*|exploit\w*|shellcode|SQL injection|cross.site scripting|attacker|weapon|pathogen|anthrax|nerve agent|ammunition|bioweapon)\b",re.I)
prior_paths=[R3/name/"selection.json" for name in ("real_swe","real_swe_followup")]
prior={r["instance_id"] for p in prior_paths for r in json.loads(p.read_bytes())}
assert len(prior)==294
source=R3/"real_swe/official_verified.parquet"
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
assert sha(source)=="030cfd7f2a704c4c0226e7f104c725a3b41230b1d3517f9c915ad7ea5be3fa25"
rows=pq.read_table(source,columns=["instance_id","repo","base_commit","problem_statement"]).to_pylist()
chosen=[];reason=Counter()
for row in sorted(rows,key=lambda r:hashlib.sha256(("r4writer|"+r["instance_id"]).encode()).hexdigest()):
    if row["instance_id"] in prior:reason["prior"]+=1;continue
    if row["instance_id"]=="sympy__sympy-11618":reason["format_example"]+=1;continue
    if BAN.search(row["problem_statement"]) or guard.search(row["problem_statement"]):reason["scope"]+=1;continue
    chosen.append(row)
audit=dict(n=len(chosen),exclude=reason,overlap=sorted(prior&{r["instance_id"] for r in chosen}),repos=Counter(r["repo"] for r in chosen),source=sha(source),previous={p.parent.name:sha(p) for p in prior_paths},protocol=sha(D/"PROTOCOL_RU.md"))
(D/"selection.json").write_text(json.dumps(chosen,indent=1),encoding="utf8")
(D/"selection_receipt.json").write_text(json.dumps(audit,indent=1),encoding="utf8")
print(audit)
