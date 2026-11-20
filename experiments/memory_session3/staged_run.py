"""Serialize the dedicated ALFWorld WSL extractions and local GPU usage under the original headroom guard."""
from pathlib import Path
import json,subprocess,time,urllib.request,sys,datetime
ROOT=Path(__file__).resolve().parent;A=ROOT/'alfworld';R=Path('D:/CodexResearch/x20-3-27b-runtime')
WSL=['wsl','-d','CodexX20MSR','--exec']; docker=WSL+['docker']
def event(label,**info):
    with (A/'stages.jsonl').open('a') as f:print(json.dumps({'utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'stage':label,**info}),file=f,flush=True)
def wait(until,seconds=900):
    end=time.monotonic()+seconds
    while not until():
        if time.monotonic()>end:raise RuntimeError('Stage exceeded deadline')
        time.sleep(2)
def ok(cmd):return subprocess.run(cmd,capture_output=True).returncode==0
def gpu_ready():
    try:return urllib.request.urlopen('http://127.0.0.1:18839/health',timeout=3).status==200
    except OSError:return False
def main():
    event('hold GPU until baseline WSL workers finish; all prior repair calls persisted')
    wait(lambda:(A/'eval.log').is_file() and 'completed 134' in (A/'eval.log').read_text(errors='ignore',encoding='utf-8-sig'))
    running=subprocess.check_output(docker+['ps','--format','{{.Names}}']).decode().split()
    assert running==['x20s3-alfworld'],running
    subprocess.run(docker+['stop','x20s3-alfworld'],check=True,stdout=subprocess.DEVNULL)
    subprocess.run(['wsl','--terminate','CodexX20MSR'],check=True,stdout=subprocess.DEVNULL)
    event('baseline complete; released dedicated WSL, retrying planner')
    if (R/'service-resumed.json').exists():(A/'repair_service.json').write_bytes((R/'service-resumed.json').read_bytes())
    with (A/'planner_service.log').open('ab') as logs:
        proc=subprocess.Popen([sys.executable,'-u',str(R/'managed_server.py')],stdout=logs,stderr=logs,creationflags=subprocess.CREATE_NO_WINDOW)
        try:
            def ready():
                if proc.poll() is not None:raise RuntimeError('Model runtime exited before readiness')
                return gpu_ready()
            wait(ready,260)
            event('planner service ready')
            with (A/'planner_retry.log').open('wb') as log:
                subprocess.run([sys.executable,'-u',str(A/'plan.py')],stdout=log,stderr=log,check=True)
        finally:
            if proc.poll() is None:proc.terminate()
            proc.wait(timeout=20)
    event('plans locked; native model stopped')
    with (A/'daemon_restart.log').open('wb') as f:
        daemon=subprocess.Popen(WSL+['dockerd','--host=unix:///var/run/docker.sock','--iptables=false','--bridge=none'],stdout=f,stderr=f,creationflags=subprocess.CREATE_NO_WINDOW)
    wait(lambda:ok(docker+['info']),70)
    subprocess.run(docker+['start','x20s3-alfworld'],check=True,stdout=subprocess.DEVNULL)
    with (A/'planner_eval.log').open('wb') as log:
        subprocess.run(docker+['exec','x20s3-alfworld','python','/study/x20-bench-workspace/work/memory_session3/alfworld/planner_roll.py'],check=True,stdout=log,stderr=log)
    subprocess.run([sys.executable,str(A/'score.py')],check=True)
    event('all ten ALFWorld arms independently executed and scored')
if __name__=='__main__':main()
