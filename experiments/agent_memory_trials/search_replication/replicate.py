"""Execute an independently sealed replication using the primary runner and scorer."""
import datetime as dt
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parent
MODEL = "gpt-6-luna"
SHARED = ROOT.parent / "shared"
sys.path.insert(0, str(SHARED))
import run_model


def check():
    seal = json.loads((ROOT / "replication_freeze.json").read_bytes())
    for filename, checksum in seal["sha256"].items():
        assert hashlib.sha256((ROOT / filename).read_bytes()).hexdigest() == checksum, filename
    original = json.loads((ROOT / "freeze.json").read_bytes())
    for entry in original["files"]:
        assert hashlib.sha256((ROOT/entry["path"]).read_bytes()).hexdigest()==entry["sha256"], entry["path"]


def probe():
    path = ROOT / "transport_probe.json"
    if path.exists():
        return json.loads(path.read_bytes())["supported"]
    cli = shutil.which("codex")
    args = [cli,"exec","--ignore-user-config","--ignore-rules","--ephemeral","--skip-git-repo-check",
            "-s","read-only","-m",MODEL,"-c",'model_reasoning_effort="low"',"--json","--color","never","-"]
    prompt = 'Use no tools. Reply with only the JSON object {"ping":1}.'
    start = dt.datetime.now(dt.timezone.utc).isoformat()
    t0 = time.monotonic()
    with tempfile.TemporaryDirectory(prefix="search-replication-probe-") as work:
        try:
            p = subprocess.run(args,cwd=work,input=prompt.encode(),capture_output=True,timeout=135,check=False)
            rc, out, err = p.returncode, p.stdout, p.stderr
        except subprocess.TimeoutExpired as exc:
            rc,out,err = 124,exc.stdout or b"",exc.stderr or b""
    raw = out.decode("utf-8","replace")
    events = [json.loads(line) for line in raw.splitlines() if line.startswith("{")]
    messages = [e["item"]["text"] for e in events if e.get("type")=="item.completed"
                and e.get("item",{}).get("type")=="agent_message"]
    complete = [e for e in events if e.get("type")=="turn.completed"]
    supported = bool(rc==0 and messages and complete)
    record = dict(started_utc=start,model=MODEL,cli_version=subprocess.check_output([cli,"--version"],text=True).strip(),
                  prompt=prompt,args=args[1:],returncode=rc,elapsed_s=round(time.monotonic()-t0,4),
                  stdout=raw,stderr=err.decode("utf-8","replace"),supported=supported,
                  usage=complete[-1].get("usage",{}) if complete else {})
    path.write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding="utf-8")
    return supported


if __name__ == "__main__":
    check()
    mode, = sys.argv[1:]
    if mode == "probe":
        ok = probe()
        print("supported =", ok, flush=True)
        raise SystemExit(0 if ok else 2)
    if mode == "run":
        assert json.loads((ROOT/"transport_probe.json").read_bytes())["supported"]
        run_model.MODEL = MODEL
        sys.argv = ["run_model.py",str(ROOT/"requests.jsonl"),str(ROOT/"runs"),"--workers","2"]
        run_model.main()
    elif mode == "score":
        import score
        score.main()
    else:
        raise ValueError(mode)
