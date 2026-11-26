"""Commit feature and model provenance before using the new panel."""
import hashlib
import json
from pathlib import Path

D=Path(__file__).resolve().parent
BASE=D.parent
ROUTING=BASE.parent/"routing"
FILES=[D/"PROTOCOL_RU.md",BASE/"model.json",BASE/"study.py",BASE/"hotpot_select.py",
       BASE/"hotpot_cardinality.py",ROUTING/"registration.json",ROUTING/"panel.json"]
data={str(p.relative_to(BASE.parent)).replace("\\","/"):hashlib.sha256(p.read_bytes()).hexdigest()
      for p in FILES}
p=D/"fixed.json"
if p.exists():
    assert json.loads(p.read_bytes())==data
else:
    p.write_bytes((json.dumps(data,indent=2,sort_keys=True)+"\n").encode())
print("Frozen",hashlib.sha256(p.read_bytes()).hexdigest())
