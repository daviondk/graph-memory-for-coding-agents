"""Read only the Vibe containers whose IDs were allocated by the R12 harness."""
import collections, gzip, hashlib, json, os, re, subprocess, time
from pathlib import Path
D=Path(__file__).resolve().parent
S=D.parents[1]/"graph_memory_round12/vibe"
def h(b):return hashlib.sha256(b).hexdigest()
def save(name,data):(D/name).write_text(json.dumps(data,indent=2)+"\n",encoding="utf8")
def events():
    return [json.loads(line) for line in (D/"events.jsonl").read_bytes().splitlines()] if (D/"events.jsonl").exists() else []
def sid(path):return "|".join(path.relative_to(S/"episodes/python").parts[:3])
def main():
    paths=S/"episodes/python";meta={r["instance_id"]:r for r in json.loads((S/"cohort.json").read_bytes())["targets"]}
    if not (D/"assignment.json").exists():
        save("assignment.json",dict(excluded=sorted(sid(p) for p in paths.rglob("finished.json")),
            active_at_start=sorted(sid(p) for p in paths.rglob("container_id.txt") if not p.with_name("finished.json").exists()),
            protocol=h((D/"PROTOCOL_RU.md").read_bytes()),observer=h((D/"observe.py").read_bytes())))
    assignment=json.loads((D/"assignment.json").read_bytes())
    excluded=set(assignment["excluded"]);(D/"patches").mkdir(exist_ok=True)
    old={};last={};errors=collections.Counter()
    for r in events():old[r["episode"]]=r["request_count"];last[r["episode"]]=r["at"]
    while True:
        count=len((S/"requests.jsonl").read_bytes().splitlines())
        for receipt in sorted(paths.rglob("container_id.txt")):
            episode=sid(receipt)
            if episode in excluded or receipt.with_name("finished.json").exists():continue
            t=time.time()
            if old.get(episode)==count and t-last.get(episode,0)<6:continue
            cid=receipt.read_text(encoding="ascii").strip();assert re.fullmatch(r"[a-f0-9]{64}",cid)
            cmd=["wsl","-d","CodexX20MSR","--exec","docker","exec",cid,"git","--no-optional-locks","-C","/testbed",
                 "diff","--no-ext-diff","--no-textconv","--binary","--no-color","HEAD","--"]
            res=subprocess.run(cmd,capture_output=True,timeout=20)
            last[episode]=t;old[episode]=count
            if res.returncode:
                errors[episode]+=1;continue
            digest=h(res.stdout);dest=D/"patches"/(digest+".patch.gz")
            if not dest.exists():dest.write_bytes(gzip.compress(res.stdout,mtime=0))
            with (D/"events.jsonl").open("a",encoding="utf8") as f:
                f.write(json.dumps(dict(episode=episode,at=t,request_count=count,sha=digest,size=len(res.stdout)))+"\n")
        if len(list(paths.rglob("finished.json")))==len(json.loads((S/"order.json").read_bytes())):break
        time.sleep(2)
    records=events();selected={}
    for episode in (set(sid(x) for x in paths.rglob("finished.json"))-excluded):
        points=[r for r in records if r["episode"]==episode]
        selected[episode]=dict(count=len(points),versions=len({r["sha"] for r in points}),last=points[-1] if points else None,
             left_truncated=episode in assignment["active_at_start"],transient_read_errors=errors[episode])
    save("selection.json",selected)
    save("sealed.json",{f:h((D/f).read_bytes()) for f in ("assignment.json","events.jsonl","selection.json")})
if __name__=="__main__":main()
