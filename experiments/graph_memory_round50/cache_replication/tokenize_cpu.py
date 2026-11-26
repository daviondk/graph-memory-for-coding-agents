"""Tokenize only the released, prefiltered Test states. No embeddings or GPU inference."""
from lineage import *
import os,sys,requests,socket,subprocess,time,threading,struct
from concurrent.futures import ThreadPoolExecutor
R39=W/'graph_memory_round39/author_baseline'
sys.path.insert(0,str(R39))
from reference import CACHE,NAME,DIGEST,EXE,INSTRUCTION,TAIL,tokenize
sys.path.insert(0,str(FROZEN))
from build_inputs import norm,digest
def main():
    select=rd(D/'selection.json');bridge=rd(D/'bridge.json');assert bridge['gate'] and sha(D/'test-panel.json.gz')==select['test_panel']
    ids=rd(D/'test-panel.json.gz');prior=rd(W/'graph_memory_round49/long_gpu/run-seal.json')['sig']
    ns=bytes.fromhex(prior['namespace']);assert sha(EXE)==prior['exe'] and sha(CACHE/NAME)==prior['model']==DIGEST
    texts={};origin={};paths={}
    def index(s):
        k=h(s);texts[k]=s;return k
    # Extract only already approved rows and visible packet data.
    with gzip.open(PUB/'test500/items.jsonl.gz','rt',encoding='utf8') as f:
        for item in map(json.loads,f):
            q=item['state_id']
            if q not in ids:continue
            query='Instruct: '+INSTRUCTION+'\nQuery: '+'\n'.join(item.get(k) or '' for k in ('information_need','current_subgoal','issue'))
            docs=[]
            for obj in sorted(item['candidate_evidence'],key=lambda a:a['evidence_id']):
                path=norm(obj['source_path']);pid=digest(path);assert paths.setdefault(pid,path)==path
                parts=path.lower().split('/');test=any(part in ('test','tests','testing') for part in parts) or parts[-1].startswith('test_') or parts[-1].endswith('_test.py')
                docs.append((index(obj['source_path']+'\n'+obj['content_excerpt']),pid,int(obj.get('line_start') or 0),int(obj.get('line_end') or 0),int(test),int(path.lower().endswith('.py')),int(obj.get('observed_by_state',False))))
            opened=sorted({digest(norm(p)) for p in item['opened_files'] if isinstance(p,str)})
            origin[q]=(index(query),opened,docs)
    sock=socket.socket();sock.bind(('127.0.0.1',0));port=sock.getsockname()[1];sock.close();base='http://127.0.0.1:'+str(port)
    args=[str(EXE),'-m',str(CACHE/NAME),'-dev','none','-ngl','0','--embeddings','--pooling','last','-t','1','-tb','1','-c','512','-b','32','-ub','32','-np','1','--host','127.0.0.1','--port',str(port),'--no-warmup','-lv','1']
    local=threading.local()
    def job(k):
        if not hasattr(local,'http'):
            local.http=requests.Session();local.http.trust_env=False
        val=tokenize(local.http,base,texts[k])[:511]+[TAIL]
        ident=hashlib.sha256(ns+struct.pack('<I',len(val))+struct.pack('<'+'I'*len(val),*val)).hexdigest()
        return k,(ident,len(val))
    tic=time.perf_counter();encoded={}
    proc=subprocess.Popen(args,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,creationflags=subprocess.CREATE_NO_WINDOW,env=dict(os.environ,CUDA_VISIBLE_DEVICES='-1'))
    try:
        with requests.Session() as http:
            http.trust_env=False
            for _ in range(90):
                if proc.poll() is not None:raise RuntimeError('CPU tokenizer exited')
                try:
                    if http.get(base+'/health',timeout=1).ok:break
                except requests.RequestException:pass
                time.sleep(1)
            else:raise RuntimeError('CPU tokenizer not ready')
        with ThreadPoolExecutor(max_workers=4) as pool:
            for k,res in pool.map(job,sorted(texts)):encoded[k]=res
    finally:
        proc.terminate();proc.wait(timeout=20)
    rows={}
    for q,(qkey,opened,items) in origin.items():
        docs={};order=[];total=encoded[qkey][1]
        for key,path,a,b,test,py,vis in items:
            ident,n=encoded[key];total+=n
            if ident in docs:
                assert docs[ident][1]==path;docs[ident][-1]=max(docs[ident][-1],vis)
            else:
                docs[ident]=[n,path,a,b,test,py,vis];order.append(ident)
        rows[q]=dict(repo=ids[q]['repo'],issue=ids[q]['issue'],panel='Test500',prev=ids[q]['prior'],total=total,
                     within=total-encoded[qkey][1]-sum(v[0] for v in docs.values()),opened=opened,docs=docs,order=order)
    dump('inputs.json.gz',rows);dump('input-seal.json',dict(states=len(rows),unique_texts=len(texts),seconds=time.perf_counter()-tic,backend=sha(EXE),model=DIGEST,
        device='CPU, device none, ngl 0, CUDA_VISIBLE_DEVICES -1',namespace=ns.hex(),data=sha(D/'inputs.json.gz'),
        test_source=sha(PUB/'test500/items.jsonl.gz'),config=prior['namespace'],plan=sha(D/'ORIGINAL_IDS_RU.md'),code=sha(Path(__file__))))
    print('Tokenized',len(rows),'states,',len(texts),'unique inputs in',round(time.perf_counter()-tic,1),'seconds')
if __name__=='__main__':main()

