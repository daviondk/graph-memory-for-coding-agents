"""Run already locked programs in the original pinned, offline, read-only image."""
import concurrent.futures,datetime,json,os,subprocess,sys,time
from pathlib import Path
from generate import ROOT,UP,load,save,sha,canon
from oracle import valid
REPAIR=ROOT.parent
IMAGE='sha256:32df0bfeee97df19f63624477dfe58338e132caf0fe762cf89a1df87b52ab120'
PREFIX=['wsl','-d','CodexX20MSR','--exec','docker']
COMMAND=PREFIX+['run','--rm','-i','--network','none','--read-only','--user','65534:65534','--cap-drop','ALL',
    '--security-opt','no-new-privileges','--pids-limit','24','--memory','288m','--cpus','1','--workdir','/tmp',
    '--entrypoint','python',IMAGE,'-I','-c']
def gate():
    milestones=[json.loads(x) for x in (REPAIR.parent/'alfworld/stages.jsonl').read_text(encoding='utf8').splitlines()]
    locked=next(x for x in milestones if 'plans locked' in x['stage'])
    d=subprocess.run(PREFIX+['info','--format','{{.ServerVersion}}'],capture_output=True,text=True,check=True,timeout=15)
    return {'gate':locked,'docker_server':d.stdout.strip(),'image':IMAGE,'utc':datetime.datetime.now(datetime.timezone.utc).isoformat()}
def seal():
    paths=['generate.py','oracle.py','runner.py','execute.py','PROTOCOL.md','cases.json','generation.json']
    seal={'utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'sha256':{p:sha((ROOT/p).read_bytes()) for p in paths},'solver_output_lock_sha256':sha((REPAIR/'output_lock.json').read_bytes())}
    if (ROOT/'lock.json').exists():
        old=load(ROOT/'lock.json');assert seal['sha256']==old['sha256'] and seal['solver_output_lock_sha256']==old['solver_output_lock_sha256']
    else:save('lock.json',seal)
def main():
    seal();save('docker.json',gate())
    old=load(REPAIR/'output_lock.json')['files']
    assert all(sha((REPAIR/f).read_bytes())==h for f,h in old.items())
    cases=load(ROOT/'cases.json')
    assignments={name:{} for name in cases};jobs={}
    def register(name,arm,code):
        h=sha(code.encode('utf8'));assignments[name][arm]=h;jobs[name,h]=code
    for name in cases:
        for arm,folder in [('reference','correct_python_programs'),('original','python_programs')]:
            register(name,arm,(UP/folder/(name+'.py')).read_text(encoding='utf8'))
    for entry in load(REPAIR/'decisions.json'):
        register(entry['name'],entry['arm'],entry['candidate'])
    save('assignments.json',assignments)
    script=(ROOT/'runner.py').read_text(encoding='utf8')
    (ROOT/'receipts').mkdir(exist_ok=True)
    def run(pair):
        name,h=pair;out='receipts/'+name+'-'+h+'.json';dest=ROOT/out
        if dest.exists():return
        payload=canon({'name':name,'code':jobs[pair],'cases':cases[name]}).encode()
        proc=subprocess.run(COMMAND+[script],input=payload,capture_output=True,timeout=90)
        if proc.returncode:raise RuntimeError((name,h,proc.stderr.decode('utf8','replace')[-450:]))
        rows=json.loads(proc.stdout)
        assert [r['key'] for r in rows]==[c['key'] for c in cases[name]]
        for row,case in zip(rows,cases[name]):
            v=row['observation'];row['ok']=v['status']=='return' and valid(name,case['input'],v['value'])
        save(out,rows);print(name,h[:8],flush=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(run,jobs))
    print('complete',len(jobs),'unique program hashes incl controls',flush=True)
if __name__=='__main__':main()
