"""Build separate blind observations and held-out recorded events from fixed public metadata."""
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import PurePosixPath
import re, time, urllib.parse, urllib.request
import pyarrow.parquet as pq
from common import *
ALLOW={"astropy/astropy","matplotlib/matplotlib","pydata/xarray","scikit-learn/scikit-learn","scipy/scipy","numpy/numpy","sympy/sympy"}
RISK=re.compile(r"\b(?:security|insecure|vulnerab\w*|exploits?|exploitation|payload|attacks?|attackers?|injection|malicious|untrusted|CVE(?:-\d+)?|unsafe\s+(?:load|deserializ\w*)|arbitrary\s+code|privilege|path\s+traversal|remote\s+code|denial.of.service|buffer\s+overflow|SQL|XSS|crypto(?:graph\w*)?|credentials?|passwords?|authenticat\w*|hacking|poisoning|weapons?|pathogen\w*|ransomware)\b",re.I)
def prod(path):
    p=PurePosixPath(path)
    return p.suffix==".py" and bool(re.fullmatch(r"[\w/.\-]+",path)) and not p.is_absolute() and ".." not in p.parts and not {x.lower() for x in p.parts}.intersection({"tests","testing","test","doc","docs","examples","benchmarks","scripts","security","crypto","cryptography","utilities_security"}) and not p.name.startswith("test_") and not p.name.endswith("_test.py") and not RISK.search(path.replace("_"," ").replace("/"," "))
def download(row):
    repo,commit,path=row
    key=digest("\0".join(row));dst=P/"files"/key
    url="https://raw.githubusercontent.com/"+repo+"/"+commit+"/"+urllib.parse.quote(path)
    try:
        for attempt in range(3):
            try:
                if not dst.exists():
                    with urllib.request.urlopen(url,timeout=20) as stream:data=stream.read(3*1024*1024+1)
                    if len(data)>3*1024*1024:raise ValueError("over3MiB")
                    dst.write_bytes(data)
                return [key,repo,commit,path,sha(dst),dst.stat().st_size],None
            except OSError:
                if attempt==2:raise
                time.sleep(1+attempt)
    except (OSError,ValueError) as exc:return [key,repo,commit,path,None,0],str(exc)
def main():
    inputs();(P/"files").mkdir(exist_ok=True)
    meta={r["instance_id"]:r for r in pq.read_table(P/"verified.parquet",columns=["repo","instance_id","base_commit","problem_statement"]).to_pylist()}
    assert len(meta)==500
    counts=Counter();q,targets,blinds={},[],[];refs=set()
    for line in (P/"swe-explore.jsonl").open(encoding="utf8"):
        row=json.loads(line);counts["all_benchmark"]+=1
        if row["dataset"]!="verified":continue
        counts["verified"]+=1;issue=row["instance_id"];m=meta.get(issue)
        if not m or m["repo"] not in ALLOW:continue
        counts["repo_allowlisted"]+=1
        if RISK.search(m["problem_statement"]):counts["excluded_issue_by_text"]+=1;continue
        counts["eligible_issue_description"]+=1
        assert re.fullmatch(r"[0-9a-f]{40}",m["base_commit"])
        q[issue]=m["problem_statement"]
        for path,records in row["read_step_info"].items():
            if not prod(path):continue
            ref=(m["repo"],m["base_commit"],path)
            series=defaultdict(lambda:defaultdict(set))
            for r in records:
                series[r["traj_path"]][int(r["step_idx"])].add((int(r["start"]), int(r["end"])))
            for traj,steps in sorted(series.items()):
                counts["trajectory_files"]+=1;ordered=sorted(steps)
                if len(ordered)<2:counts["single_step"]+=1;continue
                first,second=ordered[:2]
                if len(steps[first])!=1 or len(steps[second])!=1:counts["ambiguous_step"]+=1;continue
                v=next(iter(steps[first]));y=next(iter(steps[second]))
                if min(*v,*y)<1 or v[1]<v[0] or y[1]<y[0]:counts["unbounded_or_reversed"]+=1;continue
                ident=digest("\0".join((issue,traj,path,str(first),str(second))))
                refs.add(ref);counts["candidates"]+=1
                blinds.append(dict(id=ident,issue=issue,repo=m["repo"],file=digest("\0".join(ref)),trajectory=traj,step=first,visible=v))
                targets.append(dict(id=ident,step=second,target=y))
    with ThreadPoolExecutor(6) as pool: files=list(pool.map(download,sorted(refs)))
    assert len({x["id"] for x in blinds})==len(blinds)
    save(P/"questions.json",q);save(P/"source-map.json",[x[0] for x in files]);save(P/"gold.json.gz",targets)
    save(D/"observations.json.gz",blinds)
    save(D/"dataset.json",dict(counts=counts,source_requests=len(files),absent=[(x[0][0],x[1]) for x in files if x[1]],source_sha=sha(P/"source-map.json"),labels_sha=sha(P/"gold.json.gz"),issues_sha=sha(P/"questions.json"),observations_sha=sha(D/"observations.json.gz"),tokenizer_sha=sha(T),protocol_sha=sha(D/"PROTOCOL_RU.md")))
if __name__=="__main__":main()

