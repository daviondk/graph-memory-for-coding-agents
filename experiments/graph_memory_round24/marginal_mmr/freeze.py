"""Freeze inputs and protocol before producing decisions."""
import hashlib,json
from pathlib import Path
D=Path(__file__).resolve().parent
W=D.parents[1];R=W/"graph_memory_round23"
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
inputs=[D/"PROTOCOL_RU.md",R/"marginal_open/novelty.py",R/"marginal_open/visible-seal.json",R/"marginal_open/choice-seal.json",R/"marginal_transfer/forecast-seal.json",R/"transfer/forecast-seal.json"]
payload={"before_new_actions":True,"inputs":{p.relative_to(W).as_posix():sha(p) for p in inputs},"lambda":[0.25,0.5,0.75],"bootstrap":10000,"seed":242325,"corpora":{"ise":2000,"mdd":661}}
target=D/"plan.json"
if target.exists():assert json.loads(target.read_bytes())==payload
else:target.write_text(json.dumps(payload,sort_keys=True,indent=2)+"\n",encoding="utf-8")
print(sha(target))
