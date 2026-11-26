from io46 import *
import requests
from time import perf_counter
from statistics import median
from functools import lru_cache

BASE=f'http://127.0.0.1:{PORT}'
http=requests.Session();http.trust_env=False
def post(route,body):
    r=http.post(BASE+route,json=body,timeout=90);r.raise_for_status();return r.json()
@lru_cache(maxsize=50000)
def enc(text,special=False):
    return post('/tokenize',dict(content=text,parse_special=special,add_special=False))['tokens']
def run(tokens,warm=False):
    start=perf_counter()
    r=post('/completion',dict(prompt=tokens,temperature=0,top_k=1,seed=460001,n_predict=24,
        cache_prompt=False,ignore_eos=warm,stop=[] if warm else ['\n'],stream=False))
    return dict(answer=r['content'].strip(),generated=r['tokens_predicted'],prompt=len(tokens),
        elapsed=perf_counter()-start,stop=r.get('stop_type'),prompt_n=r['timings']['prompt_n'])

def warmup():
    props=http.get(BASE+'/props',timeout=10).json()
    assert Path(props['model_path'])==MODEL and props['total_slots']==1
    times=[];lens=[]
    for i in range(17):
        tokens=enc(f'<|im_start|>user\nExample {i}: list the names.\n',True)+enc('A public library catalog contains a book and an index. '*60)[:360]+enc('<|im_end|>\n<|im_start|>assistant\n',True)
        out=run(tokens,True)
        assert out['generated']==24
        if i:times.append(out['elapsed']);lens.append(out['prompt'])
    med=median(times)
    n=max([256]+[k for k in [256,512,768,1024] if (4*k+min(k,256))*med<=1680])
    blob=hashlib.sha1();blob.update(f'blob {RAW.stat().st_size}\0'.encode())
    with RAW.open('rb') as fd:
        while block:=fd.read(1<<20):blob.update(block)
    assert blob.hexdigest()=='fc4d1ad626d73d9dcaef00394a3a6d8e837f6448'
    src=Path(W/'graph_memory_round32/observed_transfer/transfer.py')
    plan=dict(n=n,seconds=times,prompt_lengths=lens,median=med,raw=sha(RAW),blob_sha1=blob.hexdigest(),dev=sha(DEV),
        model=sha(MODEL),server=sha(SERVER),props={k:props[k] for k in ['model_alias','model_ftype','build_info','total_slots']},
        chat_template=hexb(props['chat_template'].encode()),protocol=sha(D/'PROTOCOL_RU.md'),policy=sha(src),
        chooser=sha(W/'graph_memory_round31/observed_links/predict.py'),params=dict(temperature=0,seed=460001,n_predict=24))
    put(D/'plan.json',plan);print(n,med,sum(times),plan['model'],flush=True)

if __name__=='__main__':warmup()
