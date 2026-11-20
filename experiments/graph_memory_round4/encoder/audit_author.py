"""Execute the authors' unedited retrieve and cosine functions directly on one hash-selected row per stratum."""
import ast
import hashlib
import json
import time
from collections import defaultdict
import torch
from common_run import D,R,hashfile,load,now,readgz,save
from repo_unixcoder import UniXcoder

torch.set_num_threads(4)
torch.set_num_interop_threads(1)

def function_from_file(path,name,scope):
    tree=ast.parse(path.read_text("utf8"))
    fn=next(node for node in tree.body if isinstance(node,ast.FunctionDef) and node.name==name)
    exec(compile(ast.Module(body=[fn],type_ignores=[]),str(path),"exec"),scope)
    return scope[name]

assert hashfile(D/"predictions.jsonl.gz")==load(D/"prediction_lock.json")["pred_sha"]
packets=defaultdict(list)
for row in readgz(D/"blind.jsonl.gz"):
    packets[row["panel"]].append(row)
pred={(r["panel"],r["idx"]):r["rank"] for r in readgz(D/"predictions.jsonl.gz") if r["query"]=="3"}
model=UniXcoder(str(D/"weights")).cpu().eval()
cos=function_from_file(R/"repo_author_similarity.py","cosine_similarity",{"torch":torch})
retrieve=function_from_file(R/"repo_author_retriever.py","retrieve",{"torch":torch,"UniXcoder":UniXcoder,"cosine_similarity":cos})
results=[]
t=time.monotonic()
for panel,items in sorted(packets.items()):
    p=min(items,key=lambda row:hashlib.sha256(f"author-audit-r4|{panel}|{row['idx']}".encode()).digest())
    actual=retrieve(p["queries"]["3"],p["candidates"],model=model,max_length=512,similarity="cosine")
    reference=pred[panel,p["idx"]]
    results.append(dict(panel=panel,idx=p["idx"],order=actual,expected=reference,matched=(actual==reference)))
save("author_audit.json",dict(utc=now(),selection="one smallest sha256 per stratum",seconds=time.monotonic()-t,checks=results))
assert all(r["matched"] for r in results)
print("complete rank matching",len(results))
