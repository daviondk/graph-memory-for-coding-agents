"""Submit each locked payload once, after continuation outcome freeze."""
import json
import os
import time
import requests
from prepare import HERE,BASE,read,sha,save,stamp,token,prepare

URL='http://127.0.0.1:18839/replicate/0/v1/chat/completions'
def append(p,x):
    with p.open('a',encoding='utf8') as f:
        f.write(json.dumps(x,ensure_ascii=False)+'\n');f.flush();os.fsync(f.fileno())

def main():
    assert (HERE/'design_lock.json').is_file()
    prepare()
    while not (BASE/'continuation'/'end_lock.json').is_file():time.sleep(5)
    jobs=read(HERE/'schedule.json');payloads=read(HERE/'payloads.json')
    ledger=HERE/'model_calls.jsonl'
    done={}
    if ledger.exists():done={r['key']:r for r in map(json.loads,ledger.read_text(encoding='utf8').splitlines())}
    for job in jobs:
        key=job['key'];params=payloads[key]
        digest=token(json.dumps(params,ensure_ascii=False))
        if key in done:
            assert done[key]['payload_sha256']==digest
            continue
        start=stamp();begin=time.monotonic()
        r=requests.post(URL,json=params,timeout=320)
        if not r.ok:
            append(HERE/'transport_failures.jsonl',{**job,'utc':start,'status':r.status_code,'body':r.text})
        r.raise_for_status();out=r.json()
        record={**job,'payload_sha256':digest,'response_id':out['id'],'usage':out['usage'],'start':start,'end':stamp(),
                'seconds':time.monotonic()-begin,'raw':out['choices'][0]['message'].get('content'),
                'native_model':out.get('model'),'finish_reason':out['choices'][0].get('finish_reason')}
        append(ledger,record);done[key]=record
    assert len(done)==40 and len({r['response_id'] for r in done.values()})==40
    save(HERE/'calls_lock.json',{'utc':stamp(),'continuation_hash':sha(BASE/'continuation'/'end_lock.json'),
                                 'registration_sha256':sha(HERE/'design_lock.json'),'model_calls_sha256':sha(ledger),'n':40})
    print('40 sealed native completions',flush=True)
if __name__=='__main__':main()

