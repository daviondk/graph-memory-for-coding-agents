"""Replay the sealed prompt-only input in a dedicated local server; no answer keys available here."""
from pathlib import Path
from time import sleep,perf_counter
import hashlib
import json
import subprocess
import sys
import requests
ROOT=Path(__file__).resolve().parent
TRANSFER=ROOT.parent/'reader_transfer'
sys.path.insert(0,str(TRANSFER))
from io46 import SERVER,MODEL,PRIVATE,get,put,sha,hexb
PORT=18865
def main():
    plan=get(TRANSFER/'plan.json')
    assert sha(SERVER)==plan['server'] and sha(MODEL)==plan['model']
    inputs=TRANSFER/'prompts.json.gz'
    assert sha(inputs)==get(TRANSFER/'input-seal.json')['prompts']
    prompts=get(inputs)
    net=requests.Session();net.trust_env=False
    link=f'http://127.0.0.1:{PORT}'
    log=PRIVATE/('reader-length-'+sha(ROOT/'PROTOCOL_RU.md')[:12]+'.jsonl')
    out={}
    if log.is_file():
        for line in log.read_text('utf8').splitlines():
            k,row=json.loads(line);assert k in prompts and k not in out;out[k]=row
    args=[str(SERVER),'-m',str(MODEL),'--host','127.0.0.1','--port',str(PORT),'--parallel','1','--ctx-size','1024','--n-gpu-layers','all','--flash-attn','on','--threads','4','--no-warmup']
    start=perf_counter()
    with (PRIVATE/'reader-length-server.log').open('wb') as server_log:
        process=subprocess.Popen(args,stdout=server_log,stderr=subprocess.STDOUT,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        try:
            for i in range(160):
                if process.poll() is not None:raise RuntimeError('local server exited')
                try:
                    if net.get(link+'/health',timeout=1).status_code==200:break
                except requests.RequestException:pass
                sleep(.5)
            else:raise RuntimeError('local server unavailable')
            props=net.get(link+'/props',timeout=10).json()
            assert Path(props['model_path'])==MODEL and props['total_slots']==1
            with log.open('a',encoding='utf8') as f:
                for k in sorted(prompts,key=lambda k:hexb(('cap96|'+k).encode())):
                    if k in out:continue
                    r=net.post(link+'/completion',json={'prompt':prompts[k],'temperature':0,'top_k':1,'seed':460001,'n_predict':96,'cache_prompt':False,'ignore_eos':False,'stop':['\n'],'stream':False},timeout=90)
                    r.raise_for_status();v=r.json()
                    row=dict(answer=v['content'].strip(),tokens=v['tokens_predicted'],stop=v['stop_type'])
                    assert row['tokens']<=96
                    out[k]=row
                    f.write(json.dumps([k,row],ensure_ascii=False)+'\n');f.flush()
        finally:
            if process.poll() is None:process.terminate()
            process.wait(timeout=15)
    assert set(out)==set(prompts)
    put(ROOT/'answers.json.gz',out)
    put(ROOT/'seal.json',{'inputs':sha(inputs),'protocol':sha(ROOT/'PROTOCOL_RU.md'),'model':plan['model'],'server':plan['server'],'answers':sha(ROOT/'answers.json.gz'),'size':len(out),'seconds':perf_counter()-start,'cap':96})
    print('Sealed',len(out),'generations')
if __name__=='__main__':main()
