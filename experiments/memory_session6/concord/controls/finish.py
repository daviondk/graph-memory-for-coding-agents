import subprocess,sys,time
from util import *
def wait_for(p,limit=7200):
    start=time.monotonic()
    while not p.exists():
        if time.monotonic()-start>limit:raise TimeoutError(str(p))
        time.sleep(5)
def run(s,*args):
    print(now(),s,*args,flush=True)
    subprocess.run([sys.executable,'-B','-u',str(ROOT/s),*args],cwd=ROOT,check=True)
def main():
    wait_for(ROOT/'decision_lock.json')
    run('offline_actor.py')
    wait_for(ROOT/'judge_lock.json');wait_for(BASE/'judge/verdicts.json.gz')
    run('judge.py','--verify');run('analysis.py');run('verify.py');run('report.py')
    if (BASE/'highlight/design_lock.json').exists():
        wait_for(BASE/'highlight/decision_lock.json');wait_for(BASE/'highlight_judge/verdicts.json.gz')
        run('analysis.py','--highlight');run('verify.py');run('report.py')
    print(now(),'complete',flush=True)
if __name__=='__main__':main()

