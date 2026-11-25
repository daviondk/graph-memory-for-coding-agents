from pathlib import Path
import hashlib,json
D=Path(__file__).resolve().parent;W=D.parents[1];R=W/"graph_memory_round23";F=W/"graph_memory_round24/frontier_open"
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
paths=[D/"PROTOCOL_RU.md",F/"action-lock.json",F/"routes.py",R/"marginal_open/novelty.py",R/"marginal_open/visible-seal.json",R/"marginal_transfer/forecast-seal.json",R/"transfer/forecast-seal.json"]
target=D/"plan.json";data={"before_outcomes":True,"local_inputs":{p.relative_to(W).as_posix():sha(p) for p in paths},"third":"https://rajpurkar.github.io/SQuAD-explorer/dataset/dev-v1.1.json","seed":250451,"queries_per_article":12,"edge_wp":32,"budget":256,"entry_budget":2048}
if target.exists():assert json.loads(target.read_bytes())==data
else:target.write_text(json.dumps(data,sort_keys=True,indent=2)+"\n",encoding="utf8")
print(sha(target))
