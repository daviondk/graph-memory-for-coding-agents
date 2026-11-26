from functools import lru_cache
from time import monotonic,sleep
import requests
from base47 import *
URL='http://127.0.0.1:18866'
http=requests.Session();http.trust_env=False
def post(path,body):
    r=http.post(URL+path,json=body,timeout=90);r.raise_for_status();return r.json()
@lru_cache(maxsize=20000)
def enc(s,special=False):return post('/tokenize',dict(content=s,add_special=False,parse_special=special))['tokens']
@lru_cache(maxsize=16000)
def dec(ts):return post('/detokenize',dict(tokens=list(ts)))['content']
def produce(ts):
    v=post('/completion',dict(prompt=ts,temperature=0,top_k=1,seed=460001,n_predict=96,cache_prompt=False,
        ignore_eos=False,stop=['\n'],stream=False))
    return dict(answer=v['content'].strip(),tokens=v['tokens_predicted'],stop=v['stop_type'])
def model_check():
    plan=signed(R46,'plan.json');deadline=monotonic()+60
    while True:
        try:
            if http.get(URL+'/health',timeout=2).json().get('status')=='ok':break
        except requests.RequestException:pass
        if monotonic()>=deadline:raise RuntimeError('Model load timeout')
        sleep(.5)
    props=http.get(URL+'/props',timeout=15).json()
    assert Path(props['model_path'])==MODEL and sha(MODEL)==plan['model'] and sha(SERVER)==plan['server']
    assert props['total_slots']==1 and props['build_info']==plan['props']['build_info']
