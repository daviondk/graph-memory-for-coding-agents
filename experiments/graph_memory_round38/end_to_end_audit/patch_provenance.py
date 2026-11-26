"""Compare historical upstream PR changes to the target stable patch ID after dropping test files."""
from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
from pathlib import PurePosixPath
import json,re,subprocess
from inputs import D,R,fetch,save
def production_diff(data):
    blocks=re.split(rb"(?=^diff --git )",data,flags=re.MULTILINE)
    selected=[]
    for b in blocks:
        if not b.startswith(b"diff --git "):continue
        path=b.splitlines()[0].split(b" b/")[-1].decode("utf8")
        p=PurePosixPath(path)
        if p.parts and p.parts[0]=="traitlets" and path.endswith(".py") and not set(p.parts)&{"test","tests"} and not p.name.startswith("test_"):selected.append(b)
    return b"".join(selected)
def patchid(diff):
    if not diff:return None
    return subprocess.check_output(["git","patch-id","--stable"],input=diff).decode().split()[0]
def run(row):
    n=row["public_pr"]["number"];url=f"https://patch-diff.githubusercontent.com/raw/ipython/traitlets/pull/{n}.diff"
    data=fetch(url); pd=production_diff(data)
    return dict(pr=n,url=url,diff_hash=sha256(data).hexdigest(),production_patch_id=patchid(pd))
def main():
    old=json.loads((D/"history.json").read_text(encoding="utf8"))["records"]
    with ThreadPoolExecutor(4) as ex: rows=list(ex.map(run,old))
    target=patchid(production_diff((R/"patch.diff").read_bytes()))
    same=sum(r["production_patch_id"]==target for r in rows)
    save(D/"prior-provenance.json",dict(target_id=target,nonempty=sum(r["production_patch_id"] is not None for r in rows),matched=same,records=rows,scope="stable patch-id of full tracked non-test Python implementation diff under traitlets/; semantic equivalence untested"))
    print("historical nonempty",sum(r["production_patch_id"] is not None for r in rows),"exact patch-id matches",same)
if __name__=="__main__":main()
