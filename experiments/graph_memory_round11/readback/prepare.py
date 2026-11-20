"""Select real editor views in the immutable R8 cohort. Keep the exact numbered payload."""
import gzip, hashlib, json, re
from pathlib import Path
ROOT=Path(__file__).resolve().parent
WORK=ROOT.parents[1]
def sha(b):return hashlib.sha256(b).hexdigest()
def write(name, obj):
    s=(json.dumps(obj,ensure_ascii=False,indent=None if name.endswith(".gz") else 2,sort_keys=True)+"\n").encode()
    (ROOT/name).write_bytes(gzip.compress(s,mtime=0) if name.endswith(".gz") else s)
def readlines(file):
    with gzip.open(file,"rt",encoding="utf8") as f:yield from map(json.loads,f)
def main():
    roster={r["id"]:r["panel"] for r in readlines(WORK/"graph_memory_round8/lazy/observations.gz")}
    sources=[("claude",WORK/"graph_memory_round6/version/external/source.gz")]
    sources += [("kimi",WORK/"graph_memory_round5/action_transfer"/f"source_{i}.gz") for i in range(8)]
    sources += [("kimi_replication",WORK/"graph_memory_round5/writer"/f"source_{i}.jsonl.gz") for i in range(8)]
    lock={};out={};excluded=0
    for panel,file in sources:
        lock[file.relative_to(WORK).as_posix()]=sha(file.read_bytes())
        for obj in readlines(file):
            task=obj["instance"]
            if roster.get(task)!=panel:continue
            assert task not in out
            views=[]
            for turn,(tool,arg,body) in enumerate(obj["events"]):
                if tool not in {"str_replace_editor","str_replace_based_edit_tool","edit_file"} or arg.get("command")!="view":continue
                path=str(arg.get("path","")).removeprefix("/testbed/").removeprefix("./")
                if not path.endswith(".py") or path.startswith("/") or ".." in path.split("/"):continue
                lines=[]
                for line in body.splitlines():
                    m=re.fullmatch(r" *([1-9]\d*)\t(.*)",line)
                    if m:lines.append((int(m[1]),m[2]))
                if not lines or len(set(x[0] for x in lines))!=len(lines):
                    excluded+=1;continue
                views.append(dict(turn=turn,path=path,lines=lines))
            out[task]=dict(panel=panel,repo=obj["official_repo"],views=views,events=len(obj["events"]))
    assert set(roster)==set(out)
    write("views.gz",out)
    write("input-lock.json",dict(sources=lock,files={n:sha((ROOT/n).read_bytes()) for n in ("prepare.py","views.gz","PROTOCOL_RU.md")},excluded=excluded))
if __name__=="__main__":main()
