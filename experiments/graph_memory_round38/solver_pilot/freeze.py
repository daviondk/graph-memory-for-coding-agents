"""Seal the three independent checkout diffs and tool transcripts before scoring."""
import collections,difflib,gzip,hashlib,json,shutil
from pathlib import Path
D=Path(__file__).resolve().parent
BASE=Path("D:/CodexResearch/x20-r38-traitlets-paired")
def sha(data):return hashlib.sha256(data).hexdigest()
def main():
    plan=json.loads((D/"plan.json").read_bytes())
    packets=json.loads((D/"packets.json").read_bytes())
    original=BASE/"scout"/"repo"
    def inventory(repo):
        return {x.relative_to(repo).as_posix():sha(x.read_bytes()) for x in repo.rglob("*") if x.is_file()}
    assert inventory(original)==plan["base"]
    changes={}
    for code,arm in plan["roles"].items():
        actor=BASE/code
        assert sha((actor/"problem_statement.txt").read_bytes())==plan["issue_sha"]
        assert sha((actor/"memory.txt").read_bytes())==packets[code]["sha256"]
        repo=actor/"repo"
        tree=inventory(repo)
        assert set(tree)==set(plan["base"])
        files=sorted(p for p,digest in tree.items() if digest!=plan["base"][p])
        assert all(v.startswith("traitlets/") and "/tests/" not in v and v.endswith(".py") for v in files)
        parts=[]
        for name in files:
            a=(original/name).read_text(encoding="utf8").splitlines(keepends=True)
            b=(repo/name).read_text(encoding="utf8").splitlines(keepends=True)
            parts.append("diff --git a/"+name+" b/"+name+"\n"+"".join(difflib.unified_diff(a,b,fromfile="a/"+name,tofile="b/"+name)))
        diff="".join(parts).encode()
        (D/(code+".diff")).write_bytes(diff)
        transcript=(actor/"tool-log.jsonl").read_bytes()
        (D/(code+"-log.jsonl.gz")).write_bytes(gzip.compress(transcript,mtime=0))
        events=[json.loads(x) for x in transcript.splitlines()]
        # Concurrent read-only calls can take the same pre-call snapshot. Count completed
        # append records and preserve the original indices rather than renumbering source data.
        assert all(1<=r["index"]<=idx for idx,r in enumerate(events,1)) and len(events)<=18
        parallel_indices=sum(r["index"]!=idx for idx,r in enumerate(events,1))
        counts=dict(collections.Counter(r["action"] for r in events))
        changes[code]=dict(arm=arm,edits=files,patch_bytes=len(diff),diff_sha256=sha(diff),actions=len(events),
            tool_counts=counts,displayed_bytes=sum(r["bytes"] for r in events),failed_gateway=sum(r["output"].startswith("ERROR ") for r in events),
            overlapping_index_records=parallel_indices,raw_log_sha256=sha(transcript),memory_bytes=packets[code]["size"],problem_sha=plan["issue_sha"])
    (D/"solve-seal.json").write_bytes((json.dumps(dict(arms=changes,prefix=sha((D/"pack-seal.json").read_bytes()),
        common_prompt=sha((D/"SOLVER_PROMPT.md").read_bytes()),base_plan=sha((D/"plan.json").read_bytes())),
        sort_keys=True,indent=2)+"\n").encode())
    print([(c,v["actions"],v["patch_bytes"],v["displayed_bytes"]) for c,v in changes.items()])
if __name__=="__main__":
    main()

