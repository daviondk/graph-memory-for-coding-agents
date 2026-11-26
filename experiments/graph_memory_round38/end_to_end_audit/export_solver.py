"""Create an immutable-by-verification solver input from the untouched pinned source."""
from inputs import COMMIT,D,R,row,sha,save
from pathlib import Path
from hashlib import sha256
import argparse,json,tarfile
DEFAULT=Path("D:/CodexResearch/x20-r38-traitlets-solver-export")
def main(out):
    out=out.resolve(); directory=out/"repo"; directory.mkdir(parents=True,exist_ok=True)
    expected={}
    with tarfile.open(R/"base.tar.gz") as t:
        for m in t:
            if m.isdir():continue
            assert m.isfile()
            p=Path(m.name).relative_to("traitlets-"+COMMIT)
            assert not p.is_absolute() and ".." not in p.parts and ".git" not in p.parts
            target=directory/p;raw=t.extractfile(m).read()
            if target.exists():assert target.read_bytes()==raw
            else:target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(raw)
            expected[p.as_posix()]=sha256(raw).hexdigest()
    assert {p.relative_to(directory).as_posix() for p in directory.rglob("*") if p.is_file()}==set(expected)
    assert not any(p.name==".git" for p in directory.rglob("*"))
    text=row()["problem_statement"].encode("utf-8");task=out/"problem_statement.txt"
    if task.exists():assert text==task.read_bytes()
    else:task.write_bytes(text)
    assert {p.name for p in out.iterdir()}=={"repo","problem_statement.txt"}
    digest=sha256(json.dumps(expected,sort_keys=True,separators=(",",":")).encode()).hexdigest()
    save(D/"solver-export.json",dict(directory=str(out),members=len(expected),sha_tree=digest,
        prompt_schema="v1 exact UTF-8 VibeMemBench problem_statement; no prefix, suffix or newline added",
        prompt_sha=sha(task),task_file=task.name,dataset_origin="Tongyi-ConvAI/VibeMemBench",base=COMMIT))
    print("Solver export",out,len(expected),digest,sha(task))
if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--out",type=Path,default=DEFAULT);main(p.parse_args().out)
