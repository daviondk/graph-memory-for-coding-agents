"""Sensitivity with a different target: all files named in ground-truth patch headers."""
from pathlib import Path
import json,re,gzip,hashlib,collections,sys
import prepare
from rank import rank_one,safe_file
ROOT=Path(__file__).resolve().parent
raw=[json.loads(s) for s in (ROOT/"input/loc_outputs.jsonl").read_text(encoding="utf8").splitlines()]
old={r["id"]:r for r in (json.loads(s) for s in (ROOT/"predictions.jsonl").read_text().splitlines())}
extra=[];status=[]
for r in raw:
    i=r["instance_id"]
    if i in old:continue
    m=r["meta_data"];q=m["problem_statement"]
    inp={"id":i,"repo":m["repo"],"date":"outside official author test","base":m["base_commit"],
         "excluded":bool(prepare.DENY.search(q)),"question":q if not prepare.DENY.search(q) else "","native":r["found_files"]}
    if not inp["excluded"]:prepare.extract((inp["repo"],inp["base"]))
    out=rank_one(inp);old[i]=out;extra.append(out)
target=ROOT/"sensitivity300";target.mkdir(exist_ok=True)
pr=target/"extra_predictions.jsonl"
pr.write_text("".join(json.dumps(x,sort_keys=True)+"\n" for x in extra),encoding="utf8")
(target/"lock.json").write_text(json.dumps({"extra":hashlib.sha256(pr.read_bytes()).hexdigest(),"count":len(extra),"original":prepare.sha(ROOT/"predictions.jsonl")},indent=2),encoding="utf8")
sums=collections.defaultdict(lambda:collections.defaultdict(lambda:collections.Counter()))
per=[]
for r in raw:
    i=r["instance_id"];m=r["meta_data"];p=old[i];aex=p["date"]=="outside official author test"
    files={t for _,t in re.findall(r"^diff --git a/(\S+) b/(\S+)\s*$",m["patch"],flags=re.M)}
    na={v for v in files if safe_file(v)}
    for name,g in [("patch",files),("production_py",na)]:
        if not g:continue
        for a,pred in p["ranks"].items():
            d={"n":1,"hit":int(bool(set(pred)&g)),"complete":int(g<=set(pred))}
            for grp in ("all","extra26" if aex else "author_test"):sums[name][grp][a+" hits"]+=d["hit"];sums[name][grp][a+" complete"]+=d["complete"]
        for grp in ("all","extra26" if aex else "author_test"):sums[name][grp]["n"]+=1
        per.append({"id":i,"scope":name,"outside":aex,"targets":sorted(g),"measures":{a:[int(bool(set(pred)&g)),int(g<=set(pred))] for a,pred in p["ranks"].items()}})
(target/"rows.jsonl").write_text("".join(json.dumps(x,sort_keys=True)+"\n" for x in per),encoding="utf8")
(target/"summary.json").write_text(json.dumps(sums,indent=2),encoding="utf8")
for name,t in sums.items():
    for group,v in t.items():print(name,group,[v[k] for k in ("n","native hits","event hits","flat hits","native complete","event complete")])

