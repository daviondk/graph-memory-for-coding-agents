"""Cohort and address-only observation projection, without scores or predictions."""
import collections
import gzip
import hashlib
import json
from pathlib import Path
import re

HERE = Path(__file__).resolve().parent
WORK = HERE.parents[1]
GROUPS = {
    "claude": ("graph_memory_round3/real_swe", "graph_memory_round3/real_swe_followup",
               "graph_memory_round4/writer"),
    "kimi": ("graph_memory_round5/writer", "graph_memory_round5/action_transfer"),
}
REPOS = {"astropy/astropy","matplotlib/matplotlib","mwaskom/seaborn","scikit-learn/scikit-learn",
         "sympy/sympy","pydata/xarray","pytest-dev/pytest","pylint-dev/pylint","sphinx-doc/sphinx"}
BAD = re.compile(r"\b(?:CVE[- ]?\d*|exploit\w*|vulnerab\w*|intrusion|sql injection|injection attack|"
                 r"remote code execution|command injection|privilege escalation|denial of service|"
                 r"cross.site scripting|XSS|arbitrary code execution|malicious|path traversal|"
                 r"shellcode|malware|sandbox escape|auth(?:entication)? bypass)\b", re.I)
LINE = re.compile(r"^ *([1-9][0-9]*)\t")
TOOLS = {"str_replace_editor","str_replace_based_edit_tool","edit_file"}

def dumps(obj):
    return json.dumps(obj,sort_keys=True,ensure_ascii=True,separators=(",",":"))

def save(path,obj):
    path.write_text(json.dumps(obj,indent=2,ensure_ascii=True,sort_keys=True)+"\n",encoding="utf8")

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def rows(path):
    with gzip.open(path,"rt",encoding="utf8") as ins:
        for line in ins:
            yield json.loads(line)

def project(event):
    tool,args,body=event
    if tool not in TOOLS:
        return None
    path=str(args.get("path") or "").removeprefix("/testbed/").removeprefix("./")
    if not path.endswith(".py") or path.startswith("/") or ".." in path.split("/"):
        return None
    cmd=args.get("command")
    if cmd=="view":
        kind="view"
    elif cmd=="str_replace" and re.search(r"(?:The file .*? has been edited\.|successfully replaced)",body[:1300],re.I):
        kind="edit"
    else:
        return None
    nums=sorted({int(m[1]) for line in body.splitlines() if (m:=LINE.match(line))})
    if not nums:
        return None
    first=nums[0]
    last=first
    for n in nums[1:]:
        if n!=last+1:
            break
        last=n
    return [kind,path,(first-1)//16,(last-1)//16]

def main():
    sources={}
    tasks={g:{} for g in GROUPS}
    receipts={}
    filtered=collections.Counter()
    for group,folders in GROUPS.items():
        for folder in folders:
            base=WORK/folder
            index={r["id"]:r for r in json.loads((base/"receipts.json").read_bytes())}
            for file in sorted(base.glob("source_*.jsonl.gz")):
                sources[str(file.relative_to(WORK).as_posix())]=digest(file)
                for task in rows(file):
                    iid=task["instance"]
                    if task["official_repo"] not in REPOS:
                        filtered[group+"_scope"]+=1
                        continue
                    if BAD.search(task["issue"]):
                        filtered[group+"_textfilter"]+=1
                        continue
                    assert iid not in tasks[group]
                    tasks[group][iid]=task
                    meta=index[iid]
                    receipts[group,iid]={k:meta.get(k) for k in ("url","source_sha256")}
    duplicates=tasks["claude"].keys() & tasks["kimi"].keys()
    for iid in duplicates:
        tasks["claude"].pop(iid)
    assert not(tasks["claude"].keys()&tasks["kimi"].keys())
    with gzip.GzipFile(filename=str(HERE/"observations.jsonl.gz"),mode="wb",mtime=0) as out:
        for group in GROUPS:
            for iid,task in sorted(tasks[group].items()):
                projected=[project(ev) for ev in task["events"]]
                out.write((dumps(dict(panel=group,id=iid,repo=task["official_repo"],events=projected))+"\n").encode())
    roster=[{"panel":g,"id":i,"repo":v["official_repo"],**receipts[g,i]}
            for g in GROUPS for i,v in sorted(tasks[g].items())]
    save(HERE/"roster.json",roster)
    save(HERE/"freeze.json",{"files":{n:digest(HERE/n) for n in ["PROTOCOL.md","prepare.py","predict.py",
        "score.py","observations.jsonl.gz","roster.json"]},"source_files":sources,"excluded":dict(filtered),
        "cross_agent_issue_overlap_assigned_to_kimi":len(duplicates),
        "n_tasks":{g:len(tasks[g]) for g in GROUPS}})
    print("frozen",len(roster),"tasks from",len(sources),"files")

if __name__=="__main__":
    main()
