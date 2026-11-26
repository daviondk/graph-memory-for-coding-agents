"""Verify and copy only the final portable SERBench study, omitting all private reversible token buffers."""
from pathlib import Path
import gzip,hashlib,json,subprocess,sys,shutil
D=Path(__file__).resolve().parent
def hashfile(p):
    with p.open("rb") as f:return hashlib.file_digest(f,"sha256").hexdigest()
def dump(p,v):p.write_text(json.dumps(v,sort_keys=True,separators=(",",":"),ensure_ascii=False)+"\n",encoding="utf8")
def load(p):return json.loads(p.read_bytes())
def main():
    ver=(("verify.py","--final"),("verify_fusion.py",),("verify_matched.py",),("verify_metrics.py",),("verify_budget.py",))
    assert load(D/"progress.json")["states"]==214
    outputs={}
    for cmd in ver:
        p=subprocess.run([sys.executable,"-B",*cmd],cwd=D,check=True,stdout=subprocess.PIPE,text=True)
        outputs[" ".join(cmd)]=p.stdout.strip()
    dump(D/"verification.json",outputs)
    required={"REPORT_RU.md","MATCHED_REPORT_RU.md","BUDGET_REPORT_RU.md","verification.json","results.json","matched-results.json","budget-results.json",
              "qwen-scores.json.gz","cal-ordinal-judgments.json.gz","matched-numeric.json.gz","fusion-results.json","matched-token-seal.json"}
    extensions={".py",".ps1",".md",".json",".gz"}
    files={p.name:hashfile(p) for p in sorted(D.iterdir()) if p.is_file() and p.suffix in extensions and p.name not in ("progress.json","manifest.json","matched-tokens.json.gz")}
    assert required<=set(files) and all("tmp" not in k for k in files)
    dump(D/"manifest.json",dict(scope="Completed SERBench Cal500 Qwen3-Embedding-8B matched-mask experiment. Separate secondary extensions for RRF, equal budgets and identical visible texts.",files=files))
    destination=Path(sys.argv[1]).resolve()
    assert destination!=D
    destination.mkdir(exist_ok=True)
    for n in sorted({*files,"manifest.json"}):
        target=destination/n;source=D/n
        if target.exists():assert hashfile(target)==hashfile(source)
        else:shutil.copyfile(source,target)
    assert {p.name for p in destination.iterdir() if p.is_file()}==set(files)|{"manifest.json"}
    for cmd in ver:subprocess.run([sys.executable,"-B",*cmd],cwd=destination,check=True)
    print("Independent snapshot",len(files),"files excluding manifest,",sum((destination/n).stat().st_size for n in files),"bytes.",hashfile(destination/"manifest.json"))
if __name__=="__main__":main()
