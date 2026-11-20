import json,os,subprocess,sys,time
from sources import ROOT,VERS,sha,save
if __name__=='__main__':
    rows=json.loads((ROOT/'sources.json').read_text(encoding='utf8'))
    hashes={n:sha((ROOT/n).read_bytes()) for n in ['PROTOCOL.md','roster.py','roster.json','sources.py','sources.json','observe.py']}
    save(ROOT/'observation_lock.json',hashes)
    for entry in rows:
        if 'skip' in entry:continue
        pkg,v=entry['pkg'],entry['v']
        modes=['plain','traced'] if int(sha((pkg+v).encode())[:2],16)%2==0 else ['traced','plain']
        for mode in modes:
            path=ROOT/'runs'/pkg/v/(mode+'.json')
            if path.exists():continue
            env={**os.environ,'PYTHONHASHSEED':'0','UNICODE_VERSION':'auto','PYTHONUTF8':'1'}
            subprocess.run([sys.executable,'-S',str(ROOT/'observe.py'),pkg,v,mode],env=env,check=True,timeout=90)
        print('completed',pkg,v,flush=True)

