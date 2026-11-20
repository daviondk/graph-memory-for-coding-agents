"""Freeze fixed evidence, generate packets, and seal before grading."""
import bz2,concurrent.futures,gzip,hashlib,importlib.util,json,os,sys,time
from pathlib import Path

D=Path(__file__).resolve().parent
def read(p):return json.loads(p.read_bytes())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def lock(file,paths,**extra):
    (D/file).write_text(json.dumps(dict(utc=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),files={os.path.relpath(p,D).replace('\\','/'):sha(p) for p in paths},**extra),indent=1))
def check(name):
    for k,v in read(D/name)['files'].items(): assert sha(D/k)==v,k


def build(i):
    import build_memory
    build_memory.main(i)
    return i


def main():
    ids=read(D/'cohort.json')['ids']
    if sys.argv[1]=='freeze':
        assert not (D/'policy_lock.json').exists()
        paths=[D/f for f in ['PROTOCOL_RU.md','derive.py','collect_tasks.py','cohort.json','build_memory.py','issue_signals.py','driver.py','infer.py','grade.py','score_cpu.py','score_gpu.py','start_server.ps1']]
        paths += [D.parent/f for f in ['collect_tasks.py','build_memory.py','cohort.json','infer.py','grade.py','start_server.ps1','model_receipt.json','runtime_receipt.json','environment.txt']]
        paths += [D/'tasks'/i/'public.json' for i in ids]
        paths += [D/'tasks'/i/'ready.json' for i in ids]
        lock('policy_lock.json',paths,ids=ids,gpu=ids[:12]);return
    check('policy_lock.json')
    if sys.argv[1]=='build':
        os.environ['TOKENIZERS_PARALLELISM']='false'
        with concurrent.futures.ProcessPoolExecutor(4) as ex:
            for i in ex.map(build,ids): print(i,flush=True)
        lock('packet_lock.json',[D/'tasks'/i/'packets.json.gz' for i in ids]+[D/'policy_lock.json'])
    elif sys.argv[1]=='verify-flat':
        # Invoke the unmodified parent ranker on 3 cohort positions, intercept delivery only.
        path=D.parent/'build_memory.py'
        spec=importlib.util.spec_from_file_location('parent_ranker',path)
        m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);m.D=D
        verified=[]
        for i in [ids[0],ids[15],ids[-1]]:
            saved=json.loads(gzip.decompress((D/'tasks'/i/'packets.json.gz').read_bytes()))
            def check_flat(_,r):
                assert saved['packets']['flat']==r['packets']['flat'] and saved['paths']==r['paths'] and saved['tokens']['flat']==r['tokens']['flat']
            m.dump=check_flat;m.main(i);verified.append(i)
        (D/'flat_verification.json').write_text(json.dumps(verified))


if __name__=='__main__':main()
