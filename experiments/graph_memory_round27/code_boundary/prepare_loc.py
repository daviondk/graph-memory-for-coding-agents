from collections import defaultdict
from prepare import *
LOC=Path("D:/CodexResearch/x20-r8-swerank-runtime/locbench-test-c44cf3b74e07ca642cec841b471a9939907c12a7.parquet")
REPOS={"pandas-dev/pandas","scikit-learn/scikit-learn","jax-ml/jax","scipy/scipy","sympy/sympy","matplotlib/matplotlib","numpy/numpy","dask/dask","modin-project/modin","uxarray/uxarray"}
def targets(patch):
    files=defaultdict(dict);path=None;i=None
    for line in patch.split("\n"):
        if line.startswith("diff --git "):path=None;i=None
        elif line.startswith("--- ") and i is None:
            path=line[6:] if line.startswith("--- a/") else None
        elif line.startswith("@@ "):
            hit=re.match(r"^@@ -(\d+)(?:,\d+)? \+\d+(?:,\d+)? @@",line)
            i=int(hit[1]) if hit and path and prod(path) else None
        elif i is not None:
            if line.startswith("-"):
                if line[1:].strip():files[path][i]=digest(line[1:].rstrip("\r"))
                i+=1
            elif line.startswith(" "):i+=1
    return {p:x for p,x in files.items() if x}
def main():
    inputs()
    assert sha(LOC)=="8df0833c2c1276c5837aab923d489ab97d7654529abe759d0f59242c4978a662"
    assert sha(D/"LOCBENCH_PROTOCOL_RU.md")=="d723a3f6a5290fbc219f1b53ccb1e0fea52bf488994c15ed99c4e69be3b148d6"
    meta=pq.read_table(LOC,columns=["repo","instance_id","base_commit","problem_statement"]).to_pylist()
    table=pq.ParquetFile(LOC)
    counts=Counter();blinds=[];gold=[];refs=set();quests={}
    for b in table.iter_batches(columns=["patch"],batch_size=1):
        idx=counts["all_benchmark"];counts["all_benchmark"]+=1;m=meta[idx]
        if m["repo"].lower() not in REPOS:continue
        counts["repo_allowlisted"]+=1
        if RISK.search(m["problem_statement"]):counts["excluded_issue_by_text"]+=1;continue
        assert re.fullmatch(r"[a-f0-9]{40}",m["base_commit"])
        issue=m["instance_id"];files=targets(b[0][0].as_py())
        if not files:counts["no_eligible_nonempty_deletion"]+=1;continue
        path=min(files,key=lambda x:digest(issue+"\0"+x))
        row=(m["repo"],m["base_commit"],path);refs.add(row);key=digest("\0".join(row))
        blinds.append(dict(id=digest(issue),issue=issue,repo=m["repo"],file=key))
        gold.append(dict(id=digest(issue),lines=files[path]))
        quests[issue]=m["problem_statement"]
    with ThreadPoolExecutor(6) as pool:maps=list(pool.map(download,sorted(refs)))
    counts["candidates"]=len(blinds)
    save(P/"loc-questions.json",quests);save(P/"loc-source-map.json",[x[0] for x in maps]);save(P/"loc-gold.json.gz",gold)
    save(D/"loc-observations.json.gz",blinds)
    save(D/"loc-dataset.json",dict(counts=counts,source_requests=len(maps),absent=[(x[0][0],x[1]) for x in maps if x[1]],source_sha=sha(P/"loc-source-map.json"),labels_sha=sha(P/"loc-gold.json.gz"),issues_sha=sha(P/"loc-questions.json"),observations_sha=sha(D/"loc-observations.json.gz"),protocol_sha=sha(D/"LOCBENCH_PROTOCOL_RU.md")))
if __name__=="__main__":main()

