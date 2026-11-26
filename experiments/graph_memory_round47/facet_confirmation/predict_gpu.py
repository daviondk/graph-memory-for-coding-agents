"""Frozen GPU replication of R45 cosine scoring plus independently frozen training-only probabilities."""
from pathlib import Path
import gzip,json,hashlib,os,socket,subprocess,sys,time,re
import numpy as np
import requests
D=Path(__file__).resolve().parent;W=D.parents[1];R47=D.parent/'facet_reader';R45=W/'graph_memory_round45/qwen_panel214';R39=W/'graph_memory_round39/author_baseline'
sys.path.insert(0,str(R39))
from reference import process_state,CACHE,NAME,DIGEST,EXE,PUB
RUN=CACHE/'runs-r47-facet-confirmation'
PROTO='617e48d9c27ff770f6fe873705397798770430f83996d1b51959b365662b1e51'
def sha(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def read(p):
    b=p.read_bytes();return json.loads(gzip.decompress(b) if p.suffix=='.gz' else b)
def write(file,obj):
    p=D/file;b=(json.dumps(obj,sort_keys=True,separators=(',',':'),allow_nan=False)+'\n').encode();t=p.with_suffix(p.suffix+'.tmp')
    t.write_bytes(gzip.compress(b,mtime=0,compresslevel=4) if p.suffix=='.gz' else b);t.replace(p)
def prior(p,n):
    assert sha(p/n)==read(p/'manifest.json')['files'][n];return read(p/n)
def main():
    assert os.environ.get('R47_CONFIRM_LEASE')=='1' and sha(D/'PROTOCOL_RU.md')==PROTO
    assert sha(R47/'manifest.json')=='bc49b664345dcb30c91ef75378d19d995c0361e8c66ff6bb920322688418ad5d' and sha(CACHE/NAME)==DIGEST
    panel=prior(R47,'panels.json');probs=prior(R47,'predicted-roles.json.gz');features=prior(R47,'predictions.json.gz');prev=prior(R45,'qwen-scores.json.gz');anchor=prior(R45,'panel.json')['order'][0]
    existing=prior(R45,'gpu-seal.json')['inputs'];assert sha(R39/'reference.py')==existing['preprocessing'] and sha(EXE)==existing['exe']
    sequence=[anchor]+sorted(panel['dev'],key=lambda q:hashlib.sha256(('r47-confirm-dev/'+q).encode()).digest())
    assert len(sequence)==102 and len(set(sequence))==102
    ids=set(sequence)
    with gzip.open(PUB/'items.jsonl.gz','rt',encoding='utf8') as f:states={z['state_id']:z for z in map(json.loads,f) if z['state_id'] in ids}
    assert set(states)==ids
    sig=dict(source=sha(R39/'reference.py'),previous=sha(R47/'manifest.json'),model=DIGEST,exe=sha(EXE),protocol=PROTO,program=sha(Path(__file__)),anchor=anchor)
    listener=socket.socket();listener.bind(('127.0.0.1',0));port=listener.getsockname()[1];listener.close();RUN.mkdir(exist_ok=True)
    args=[str(EXE),'-m',str(CACHE/NAME),'-ngl','99','-fit','off','--embeddings','--pooling','last','-c','4096','-b','2048','-ub','2048','-t','3','-tb','3','-np','4','--host','127.0.0.1','--port',str(port),'--no-warmup','-lv','5']
    logpath=RUN/('gpu-'+str(time.time_ns())+'.log');http=requests.Session();http.trust_env=False;address='http://127.0.0.1:'+str(port)
    raw={};ranks={};receipts={};ticks=time.perf_counter()
    with logpath.open('wb') as log:
        child=subprocess.Popen(args,stdout=log,stderr=log,creationflags=subprocess.CREATE_NO_WINDOW,env=dict(os.environ,CUDA_VISIBLE_DEVICES='0'))
        try:
            for _ in range(90):
                if child.poll() is not None:raise RuntimeError('GPU service failed')
                try:
                    if http.get(address+'/health',timeout=1).ok:break
                except requests.RequestException:pass
                time.sleep(1)
            else:raise RuntimeError('GPU service readiness timeout')
            for ix,q in enumerate(sequence):
                save=RUN/(hashlib.sha256(q.encode()).hexdigest()+'.json')
                if save.exists():
                    z=read(save);assert z['sig']==sig and z['q']==q;entry=z['record']
                else:
                    entry=process_state(http,address,states[q]);t=save.with_suffix('.tmp');t.write_text(json.dumps(dict(sig=sig,q=q,record=entry),sort_keys=True),encoding='utf8');t.replace(save)
                receipts[q]=sha(save)
                if q==anchor:
                    old=prev[q];assert old['lengths']==entry['lengths'] and set(old['scores'])==set(entry['scores'])
                    diff=max(abs(v-old['scores'][i]) for i,v in entry['scores'].items());matched=old['ranks']==entry['ranks']
                    assert matched and diff<1e-3,('anchor mismatch',diff,matched)
                    audit=dict(q=q,rank_match=matched,max_abs_cosine_delta=diff,n=len(entry['scores']))
                    write('anchor.json',audit);continue
                item=features[q];cs=item['ids'];p=np.asarray(probs[q]['union']);obs=item['seen'];sc=entry['scores'];assert list(sorted(sc))==cs
                order=sorted(range(len(cs)),key=lambda i:(-sc[cs[i]],cs[i]));u=np.zeros(len(cs));u[order]=1/np.sqrt(1+np.arange(len(cs)));u+=.65*p/p.max()
                a=sorted(order,key=lambda i:-u[i]);tail=[i for i in order if obs[i]]
                rank=dict(qwen=order,union=a,qwen_mask=[i for i in order if not obs[i]]+tail,union_mask=[i for i in a if not obs[i]]+tail)
                assert [cs[i] for i in order[:8]]==entry['ranks']['qwen'] and [cs[i] for i in rank['qwen_mask'][:8]]==entry['ranks']['qwen_seen']
                raw[q]=entry;ranks[q]=dict(ids=cs,seen=obs,repo=item['repo'],p=p.tolist(),rank=rank)
                if ix%10==0 or ix==len(sequence)-1:
                    write('progress.json',dict(states=ix,expected=101,elapsed=time.perf_counter()-ticks,tokens=sum(x['tokens'] for x in raw.values())))
                    print('Complete',ix,'/101',round(time.perf_counter()-ticks,1),'seconds.',flush=True)
        finally:child.terminate();child.wait(timeout=25)
    lines=logpath.read_text('utf8',errors='replace').splitlines();evidence=[t.strip() for t in lines if re.search(r'offloaded [1-9][0-9]*/[0-9]+ layers to GPU|using device CUDA0|CUDA0 model buffer size|CUDA0 \(NVIDIA',t,re.I)]
    assert evidence and len(ranks)==101
    write('qwen-scores.json.gz',raw);write('predictions.json.gz',ranks);write('forecast-seal.json',dict(sig=sig,pred=sha(D/'predictions.json.gz'),raw=sha(D/'qwen-scores.json.gz'),
        receipts=receipts,order=sequence[1:],device=evidence,anchor=sha(D/'anchor.json'),log=sha(logpath),elapsed=time.perf_counter()-ticks))
if __name__=='__main__':main()

