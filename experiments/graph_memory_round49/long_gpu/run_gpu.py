"""Timed causal use of actual retained embeddings at the frozen persistent capacity."""
# Imports prefixed to avoid the legacy R39 panel.py module name.
from pathlib import Path
import sys,importlib.util,os,time,gzip,json,hashlib,struct,tempfile,socket,subprocess,re
import numpy as np,requests
from pdh import Engines,delta,active
D=Path(__file__).resolve().parent;W=D.parents[1];R39=W/'graph_memory_round39/author_baseline';AD=W/'graph_memory_round48/cache_admission';R48=W/'graph_memory_round48/embedding_reuse'
def mod(k,p):
    s=importlib.util.spec_from_file_location(k,p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
util=mod('r49_panel',D/'panel.py');sys.path.insert(0,str(R39))
from reference import CACHE,NAME,DIGEST,EXE,INSTRUCTION,TAIL,tokenize,embed
sys.path.insert(0,str(AD));from admission import Cache,capacity
from gdsf import GD
RUN=CACHE/'r49-real-vector-cache';COUNT=capacity(512);assert COUNT==31
def tokenkey(ns,v):return hashlib.sha256(ns+struct.pack('<I',len(v))+struct.pack('<'+'I'*len(v),*v)).digest()
class DigestKeys:
    def __getitem__(self,k):return k
class DigestInts:
    def __getitem__(self,k):return int.from_bytes(k,'big')
def drive(q,z,name,policy,resident,http,address,engine,pid,ns):
    # Disk I/O is outside service wall. Every condition starts with raw source-level item fields.
    eb=engine.read(pid);t0=time.perf_counter();c=sorted(z['candidate_evidence'],key=lambda u:u['evidence_id']);ids=[a['evidence_id'] for a in c]
    qq='Instruct: '+INSTRUCTION+'\nQuery: '+'\n'.join(z.get(k) or '' for k in ('information_need','current_subgoal','issue'));txt=[qq]+[a['source_path']+'\n'+a['content_excerpt'] for a in c]
    tt=time.perf_counter();ts=[a[:511]+[TAIL] for a in (tokenize(http,address,s) for s in txt)];tokenize_s=time.perf_counter()-tt
    keys=[tokenkey(ns,v) for v in ts[1:]];docs={k:len(ts[i]) for i,k in enumerate(keys,1)};fresh=name=='fresh';before=set(resident);seen=set(before);todo=[0]
    for j,k in enumerate(keys,1):
        if fresh or k not in seen:todo.append(j);seen.add(k)
    order=sorted(todo,key=lambda j:len(ts[j]));matrix=np.empty((len(ts),4096),np.float32);tm=0.;calls=0
    for i in range(0,len(order),4):
        ix=order[i:i+4];t=time.perf_counter();vec=embed(http,address,[ts[j] for j in ix]);tm+=time.perf_counter()-t;matrix[ix]=vec;calls+=1
    if not fresh:
        packet=resident.copy()
        for i in todo:
            if i:packet[keys[i-1]]=matrix[i]
        for i,k in enumerate(keys,1):matrix[i]=packet[k]
    sc=matrix[1:]@matrix[0];rank=np.argsort(-sc,kind='stable').tolist();wall=time.perf_counter()-t0
    if not fresh:
        if name=='lru':
            ranked=sorted(docs,key=lambda k:(docs[k],-int.from_bytes(k,'big')));hit,t=policy.operate({k:docs[k] for k in ranked});wanted=list(policy.entries())
        elif name=='proposed':hit,t=policy.operate(docs);wanted=list(policy.entries())
        else:hit,t=policy.update(docs);wanted=list(policy.res)
        assert hit==len(before&set(docs))
        # Independent copies of selected vectors; no shared view points to an earlier output matrix.
        resident.clear();resident.update((k,packet[k].copy()) for k in wanted);assert len(wanted)<=COUNT and all(a.base is None and a.nbytes==16384 for a in resident.values())
    committed=time.perf_counter()-t0;ed=engine.read(pid);hw=delta(eb,ed)
    info=dict(q=q,ids=ids,rank=rank,scores=sc.astype(float).tolist(),vector_sha=[hashlib.sha256(v.tobytes()).hexdigest() for v in matrix],
        wall_rank=wall,wall_commit=committed,rpc_wall=tm,tokenizer_wall=tokenize_s,device_engines=hw,compute_engine_s=active(hw),
        tokens=sum(len(ts[i]) for i in todo),docs=len(keys),unique=len(docs),hit=len(before&set(docs)) if not fresh else 0,tokens_full=sum(map(len,ts)),calls=calls,query_tokens=len(ts[0]),
        doc_keys=[k.hex() for k in keys],doc_tokens=list(map(len,ts[1:])),resident_in=sorted(k.hex() for k in before),resident_out=sorted(k.hex() for k in resident),
        persistent_bytes=(1280+len(resident)*(16384+64)) if not fresh else 0)
    return info
def main():
    assert os.environ.get('R49_GPU_LEASE')=='1';panel=util.read(D/'panel.json');assert util.sha(D/'PROTOCOL_RU.md')==panel['protocol'] and util.sha(CACHE/NAME)==DIGEST
    assert util.sha(AD/'manifest.json')==panel['admission'];source=util.read(R48/'input-seal.json');ns=bytes.fromhex(source['namespace']);assert source['config']['runtime']==util.sha(EXE)
    selected=panel['selected'];targets={q for z in selected for q in z['seq']}
    with gzip.open(util.PUB/'items.jsonl.gz','rt',encoding='utf8') as s:items={z['state_id']:z for z in map(json.loads,s) if z['state_id'] in targets}
    RUN.mkdir(exist_ok=True);sock=socket.socket();sock.bind(('127.0.0.1',0));port=sock.getsockname()[1];sock.close();addr='http://127.0.0.1:'+str(port);sess=requests.Session();sess.trust_env=False;met=Engines()
    args=[str(EXE),'-m',str(CACHE/NAME),'-ngl','99','-fit','off','--embeddings','--pooling','last','-c','4096','-b','2048','-ub','2048','-t','3','-tb','3','-np','4','--host','127.0.0.1','--port',str(port),'--no-warmup','-lv','3']
    signature=dict(panel=util.sha(D/'panel.json'),protocol=panel['protocol'],runner=util.sha(Path(__file__)),pdh=util.sha(D/'pdh.py'),admission=util.sha(AD/'admission.py'),gdsf=util.sha(AD/'gdsf.py'),qwen=util.sha(R39/'reference.py'),model=DIGEST,exe=util.sha(EXE),namespace=source['namespace'])
    log=RUN/('gpu-'+str(time.time_ns())+'.log');out={};receipts={};start=time.perf_counter()
    with log.open('wb') as f:
        proc=subprocess.Popen(args,stdout=f,stderr=f,creationflags=subprocess.CREATE_NO_WINDOW,env=dict(os.environ,CUDA_VISIBLE_DEVICES='0'))
        try:
            for _ in range(90):
                if proc.poll() is not None:raise RuntimeError('GPU server stopped')
                try:
                    if sess.get(addr+'/health',timeout=1).ok:break
                except requests.RequestException:pass
                time.sleep(1)
            else:raise RuntimeError('GPU readiness timeout')
            warm_start=met.read(proc.pid);_v=embed(sess,addr,[[731,1012,592,t,TAIL] for t in range(4)]);warm=delta(warm_start,met.read(proc.pid))
            print('WDDM warmup engines',warm,flush=True)
            for i,z in enumerate(selected):
                repo=z['repo'];r={};receipt=RUN/(z['priority']+'.json')
                if receipt.exists():
                    historical=util.read(receipt);assert historical['sig']==signature and historical['seq']==z['seq'];r=historical['modes']
                else:
                    for name in z['methods']:
                        method=GD('batch',COUNT,DigestInts()) if name=='gdsf' else None if name=='fresh' else Cache('hot_lru' if name=='lru' else 'proposed',COUNT,DigestKeys())
                        actual={};r[name]=[drive(q,items[q],name,method,actual,sess,addr,met,proc.pid,ns) for q in z['seq']]
                    tmp=receipt.with_suffix('.tmp');tmp.write_bytes(util.canon(dict(sig=signature,seq=z['seq'],modes=r)));tmp.replace(receipt)
                out[repo]=r;receipts[repo]=util.sha(receipt)
                util.put('progress.json',dict(chains=i+1,total=len(selected),seconds=time.perf_counter()-start));print('Completed full chain',i+1,'/',len(selected),'elapsed',round(time.perf_counter()-start,1),flush=True)
        finally:proc.terminate();proc.wait(timeout=25);met.close()
    lines=log.read_text('utf8',errors='replace').splitlines();ev=[t.strip() for t in lines if re.search(r'offloaded [1-9][0-9]*/[0-9]+ layers to GPU|using device CUDA0|CUDA0 model buffer size|CUDA0 \(NVIDIA',t,re.I)]
    assert ev;util.put('raw-runs.json.gz',out);util.put('run-seal.json',dict(sig=signature,raw=util.sha(D/'raw-runs.json.gz'),receipts=receipts,warmup=warm,log=util.sha(log),backend=ev,elapsed=time.perf_counter()-start))
if __name__=='__main__':main()

