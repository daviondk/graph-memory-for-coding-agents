from pathlib import Path
import hashlib
import datetime
import json
import subprocess
ROOT=Path(__file__).resolve().parent
UP=Path('D:/CodexResearch/x20-session3-quixbugs')
IMAGE='sha256:32df0bfeee97df19f63624477dfe58338e132caf0fe762cf89a1df87b52ab120'
ARMS=['empty','recent','witness','full']
def sha(s):return hashlib.sha256(s.encode('utf8')).hexdigest()
def obj(s):return json.dumps(s,ensure_ascii=True,sort_keys=True,separators=(',',':'))
def save(n,v):
    path=ROOT/n; path.parent.mkdir(parents=True,exist_ok=True); tmp=path.with_suffix(path.suffix+'.tmp')
    tmp.write_text(json.dumps(v,ensure_ascii=False,indent=1)+'\n',encoding='utf8');tmp.replace(path)
def read(n):return json.loads((ROOT/n).read_text(encoding='utf8'))
def utc():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def grade(name,code,cases):
    script=(ROOT/'container_runner.py').read_text(encoding='utf8')
    # Use stdin for the larger script/data. No host volumes, no network, no root.
    docker=['wsl','-d','CodexX20MSR','--exec','docker','run','--rm','-i','--network','none','--read-only','--user','65534:65534','--cap-drop','ALL','--security-opt','no-new-privileges','--pids-limit','24','--memory','320m','--cpus','1','--workdir','/tmp','--entrypoint','python',IMAGE,'-I','-c',script]
    p=subprocess.run(docker,input=obj({'name':name,'code':code,'cases':cases}).encode(),capture_output=True,timeout=120+3*len(cases))
    if p.returncode:raise RuntimeError(p.stderr.decode('utf8','replace')[-1300:])
    return json.loads(p.stdout)
def freeze(paths):
    return {str(fn):hashlib.sha256((ROOT/fn).read_bytes()).hexdigest() for fn in paths}

