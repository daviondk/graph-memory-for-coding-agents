"""Collect public input metadata without using a credential helper or checking out task source."""
from pathlib import Path
import concurrent.futures, json, os, subprocess, time
ROOT=Path(__file__).resolve().parent
env={**os.environ,"GIT_TERMINAL_PROMPT":"0","GCM_INTERACTIVE":"Never"}
records=[json.loads(s) for s in (ROOT/"input/loc_outputs.jsonl").read_text(encoding="utf8").splitlines()]
repos=sorted({r["meta_data"]["repo"] for r in records})
def fetch(repo):
    dest=ROOT/"mirrors"/repo.replace("/","__")
    if not dest.exists():
        cmd=["git","-c","credential.helper=","clone","--quiet","--bare","--filter=blob:none","--single-branch","--no-tags",
             "https://github.com/"+repo+".git",str(dest)]
        p=subprocess.run(cmd,env=env,capture_output=True,timeout=350)
        if p.returncode:
            return {"repo":repo,"returncode":p.returncode,"error":p.stderr.decode(errors="replace")[-500:]}
    ids=sorted({r["meta_data"]["base_commit"] for r in records if r["meta_data"]["repo"]==repo})
    verified=subprocess.run(["git","-c","credential.helper=","-C",str(dest),"cat-file","--batch-check=%(objecttype)"],
        input="\n".join(ids)+"\n",text=True,capture_output=True,timeout=90,env={**env,"GIT_NO_LAZY_FETCH":"1"})
    kinds=verified.stdout.splitlines()
    result={"repo":repo,"head":subprocess.check_output(["git","-C",str(dest),"rev-parse","HEAD"]).decode().strip(),
            "bases":len(ids),"present":sum(x=="commit" for x in kinds),"returncode":verified.returncode}
    print(result,flush=True)
    return result
if __name__=="__main__":
    (ROOT/"mirrors").mkdir(exist_ok=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        output=list(pool.map(fetch,repos))
    (ROOT/"mirror_receipt.json").write_text(json.dumps(output,indent=2),encoding="utf8")

