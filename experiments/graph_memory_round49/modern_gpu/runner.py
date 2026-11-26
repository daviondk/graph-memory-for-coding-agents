"""Physical matched GPU experiment using the unchanged measurement routine from long_gpu."""
from pathlib import Path
from collections import defaultdict
import hashlib, os, gzip, json, socket, subprocess, time, sys
import requests
D = Path(__file__).resolve().parent
LONG = D.parent/'long_gpu'
CONTROL = D.parent/'cache_controls'
sys.path.insert(0,str(LONG))
import run_gpu as physical
sys.path.insert(0,str(CONTROL))
from policies import S3FIFO,Sieve
P = physical
RUN = P.CACHE/'r49-modern-physical'
ORDER = ['PFV','VFP','FVP','PVF','VPF','FPV','PFV','FVP']
NAMES = {'P':'proposed','F':'s3','V':'sieve'}
PLAN = 'f3aa4a64e970fbc0ee137530288e29e211afcb517b900ec01796d55430532402'


def put(name,v):
    b=P.util.canon(v)+b'\n'
    if name.endswith('.gz'):b=gzip.compress(b,mtime=0,compresslevel=4)
    target=D/name;tmp=target.with_suffix(target.suffix+'.tmp')
    tmp.write_bytes(b);tmp.replace(target)


class BatchUpdate:
    def __init__(self,mode):
        self.impl=S3FIFO() if mode=='s3' else Sieve()

    @property
    def res(self):
        return self.impl.residents()

    def update(self, docs):
        old=self.impl.residents()
        seq=sorted(docs,key=lambda k:(k in old,docs[k],-int.from_bytes(k,'big')))
        for k in seq:self.impl.access(k)
        hits=old & docs.keys()
        return len(hits),sum(docs[k] for k in hits)


def main():
    assert os.environ.get('R49_GPU_LEASE')=='1' and P.util.sha(D/'PROTOCOL_RU.md')==PLAN
    panel=P.util.read(LONG/'panel.json'); prior=P.util.read(LONG/'run-seal.json')['sig']
    assert P.util.sha(LONG/'manifest.json')=='6ce356c3e992e6907537566b21df182baa39f7f6b939191dead604a33aefd059'
    assert P.util.sha(CONTROL/'manifest.json')=='28cb4e4d897e34078d7d0c79355fa2a12c03bc8c2baeae41f98fb93b20ca6898'
    assert P.util.sha(P.EXE)==prior['exe'] and P.util.sha(P.CACHE/P.NAME)==prior['model']
    signature=dict(protocol=PLAN,runner=P.util.sha(Path(__file__)),long=P.util.sha(LONG/'manifest.json'),controls=P.util.sha(CONTROL/'manifest.json'),source=prior)
    ns=bytes.fromhex(prior['namespace']);targets={q for c in panel['selected'] for q in c['seq']}
    with gzip.open(P.util.PUB/'items.jsonl.gz','rt',encoding='utf-8') as f:
        items={r['state_id']:r for r in map(json.loads,f) if r['state_id'] in targets}
    RUN.mkdir(exist_ok=True)
    sock=socket.socket();sock.bind(('127.0.0.1',0));port=sock.getsockname()[1];sock.close();addr='http://127.0.0.1:'+str(port)
    sess=requests.Session();sess.trust_env=False;met=P.Engines()
    args=[str(P.EXE),'-m',str(P.CACHE/P.NAME),'-ngl','99','-fit','off','--embeddings','--pooling','last','-c','4096','-b','2048','-ub','2048','-t','3','-tb','3','-np','4','--host','127.0.0.1','--port',str(port),'--no-warmup','-lv','3']
    log=RUN/('gpu-'+str(time.time_ns())+'.log');t0=time.perf_counter();results={};hashes={}
    with log.open('wb') as f:
        proc=subprocess.Popen(args,stdout=f,stderr=f,creationflags=subprocess.CREATE_NO_WINDOW,env=dict(os.environ,CUDA_VISIBLE_DEVICES='0'))
        try:
            for _ in range(90):
                if proc.poll() is not None: raise RuntimeError('Embedding server stopped')
                try:
                    if sess.get(addr+'/health',timeout=1).ok:break
                except requests.RequestException:pass
                time.sleep(1)
            else:raise RuntimeError('GPU readiness timeout')
            b=met.read(proc.pid);P.embed(sess,addr,[[731,1012,592,x,P.TAIL] for x in range(4)]);warm=P.delta(b,met.read(proc.pid))
            assert P.active(warm)>0;print('Warmup PID CUDA seconds',P.active(warm),flush=True)
            for i,z in enumerate(panel['selected']):
                repo=z['repo'];path=RUN/(z['priority']+'.json');out={}
                if path.exists():
                    rec=P.util.read(path);assert rec['signature']==signature;out=rec['rows']
                else:
                    for letter in ORDER[i]:
                        mode=NAMES[letter]
                        pol=P.Cache('proposed',31,P.DigestKeys()) if mode=='proposed' else BatchUpdate(mode)
                        vec={};rows=[]
                        for q in z['seq']:
                            r=P.drive(q,items[q],mode,pol,vec,sess,addr,met,proc.pid,ns)
                            ghost=len(pol.impl.ghost) if mode=='s3' else 0;r['ghost_keys']=ghost
                            r['persistent_bytes']=256+len(vec)*(16384+64)+(1024 if mode=='proposed' else 40*ghost)
                            assert P.active(r['device_engines'])>0 and r['persistent_bytes']<=524288
                            rows.append(r)
                        out[mode]=rows
                    tmp=path.with_suffix('.tmp');tmp.write_bytes(P.util.canon(dict(signature=signature,rows=out)));tmp.replace(path)
                results[repo]=out;hashes[repo]=P.util.sha(path)
                put('progress.json',dict(completed=i+1,total=8,elapsed=time.perf_counter()-t0))
                print('Completed chain',i+1,'/ 8 in',round(time.perf_counter()-t0,1),'s',flush=True)
        finally:
            proc.terminate();proc.wait(timeout=25);met.close();sess.close()
    assert P.NAME.encode() in log.read_bytes()
    put('receipts.json.gz',results)
    put('seal.json',dict(signature=signature,receipts=P.util.sha(D/'receipts.json.gz'),files=hashes,order=ORDER,warmup=warm,seconds=time.perf_counter()-t0,log=P.util.sha(log)))


if __name__ == '__main__':main()

