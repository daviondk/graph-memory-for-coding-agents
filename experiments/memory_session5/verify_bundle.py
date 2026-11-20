"""Verify manifest if present and replay each reported track from a moved checkout."""
from pathlib import Path
import hashlib,json,os,subprocess,sys,time
ROOT=Path(__file__).resolve().parent
def sha(f):
    with f.open('rb') as handle:return hashlib.file_digest(handle,'sha256').hexdigest()
SUITES=[
 ('packets',['verify.py']),
 ('packets',['all_costs.py']),
 ('packets',['live_score.py','--verify']),
 ('packets',['live_audit.py']),
 ('packets',['allocation_audit.py']),
 ('live',['verify_final.py']),
 ('diagnosis',['verify.py']),
 ('literature/policy',['verify.py']),
 ('serbench',['grade.py','--verify']),
 ('serbench',['trace_grade.py','--verify']),
 ('serbench',['dense_grade.py','--verify']),
 ('serbench',['fixed_grade.py','--verify'])]
def check():
    manifest=ROOT/'MANIFEST.json'
    if manifest.exists():
        fs=json.loads(manifest.read_bytes())['files']
        for n,expected in fs.items():
            dest=ROOT/n
            assert dest.stat().st_size==expected['bytes'] and sha(dest)==expected['sha256'],n
        print('Manifest passed:',len(fs),'files',flush=True)
    env=dict(os.environ,PYTHONUTF8='1',OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1',PYTHONDONTWRITEBYTECODE='1')
    done=[]
    for sub,args in SUITES:
        start=time.monotonic()
        cp=subprocess.run([sys.executable,'-B',*args],cwd=ROOT/sub,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=600)
        s=cp.stdout.decode('utf-8','replace')
        if cp.returncode:raise RuntimeError(f'{sub}/{args[0]} failed: {s[-4600:]}')
        done.append({'suite':sub+'/'+args[0],'args':args[1:],'seconds':round(time.monotonic()-start,2),'output':s[-4100:]})
        print('PASS',sub,*args,done[-1]['seconds'],'s',flush=True)
    return done
if __name__=='__main__':
    done=check()
    if len(sys.argv)>1:Path(sys.argv[1]).write_text(json.dumps(done,ensure_ascii=False,indent=2),encoding='utf8')
