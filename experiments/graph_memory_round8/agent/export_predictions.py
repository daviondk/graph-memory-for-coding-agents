"""Export post-hoc the sealed proposals as SWE-bench-compatible JSONL (empty patch for unapplied edits)."""
import difflib
import json
import subprocess
import os
from pathlib import Path
import evaluate
import harness as h

def main():
    ids=evaluate.answers()
    grader=evaluate.grader()
    assign=h.read(h.D/"assign.json")
    verified={}
    for alias,label in h.METHODS.items():
        rows=[]
        for i in ids:
            task=h.D/"tasks"/i; work=task/"base"; patch=""
            grade=h.read(task/"grades_v2/solver.json")[alias]
            if grade["applied"]:
                reply=h.read(h.D/"calls"/(assign[i][alias]+".json.gz"))["response"]["choices"][0]["message"]["content"]
                cfg=h.read(task/"public_input.json.gz")
                edits=grader.propose(work,grader.changes(reply),set(cfg["paths"]))
                for p,b in edits.items():
                    old=(work/p).read_text(encoding="utf-8").splitlines(keepends=True)
                    new=b.decode().splitlines(keepends=True)
                    for line in difflib.unified_diff(old,new,fromfile="a/"+p,tofile="b/"+p,lineterm="\n"):
                        if not line.endswith("\n"):
                            patch+=line+"\n\\ No newline at end of file\n"
                        else:
                            patch+=line
                check=subprocess.run(["git","apply","--check","--whitespace=nowarn","-"],input=patch.encode(),cwd=work,
                                     env={**os.environ,"GIT_CEILING_DIRECTORIES":str(work.parent)},capture_output=True)
                assert check.returncode==0,(i,check.stderr)
            rows.append(dict(instance_id=i,model_name_or_path=f"r8-qwen38-27b-{label}",model_patch=patch))
        path=h.D/f"predictions_{label}.jsonl"
        with path.open("w",encoding="utf8",newline="\n") as f:
            for x in rows:f.write(json.dumps(x,ensure_ascii=False)+"\n")
        verified[label]={"predictions":len(rows),"nonempty_validated":sum(bool(x["model_patch"]) for x in rows),"sha256":h.filehash(path)}
    h.write(h.D/"predictions_verification.json",verified)
if __name__=="__main__":main()
