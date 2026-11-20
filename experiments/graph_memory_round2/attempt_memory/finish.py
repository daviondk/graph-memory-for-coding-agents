import datetime,subprocess,sys,time
from prepare import HERE,read,sha,save
def execute(script,*args):
    subprocess.run([sys.executable,"-W","ignore","-B",str(HERE/script),*args],cwd=HERE,check=True)
if __name__=="__main__":
    pre=["PROTOCOL.md","input_lock.json","prepare.py","llm.py","generate.py","capture_worker.py","observe.py","policy.py","score.py"]
    save(HERE/"method_lock.json",{"utc":datetime.datetime.now(datetime.timezone.utc).isoformat(),"sha":{f:sha((HERE/f).read_bytes()) for f in pre}})
    execute("policy.py","old")
    for _ in range(1800):
        if (HERE/"candidate_lock.json").exists():break
        time.sleep(1)
    else:raise RuntimeError("Candidate generation timed out")
    execute("observe.py","fresh");execute("policy.py","fresh")
    names=["decisions_old.json","decisions_fresh.json","observed_old.json","observed_fresh.json","candidate_lock.json","method_lock.json"]
    save(HERE/"decision_lock.json",{f:sha((HERE/f).read_bytes()) for f in names})
    execute("score.py")

