"""Blind answering process. Its only task input contains prebuilt token arrays keyed by hash."""
from engine import run
from io46 import D,PRIVATE,get,put,sha,hexb
from time import perf_counter

def main():
    seal=get(D/'input-seal.json');assert sha(D/'prompts.json.gz')==seal['prompts']
    prompts=get(D/'prompts.json.gz');assert len(prompts)==seal['unique']
    ident=sha(D/'input-seal.json');progress=PRIVATE/('outputs-'+ident+'.jsonl')
    import json
    out={}
    if progress.exists():
        for line in progress.read_text(encoding='utf8').splitlines():
            k,r=json.loads(line);assert k in prompts and k not in out;out[k]=r
    start=perf_counter()
    with progress.open('a',encoding='utf8') as stream:
        for k in sorted(prompts,key=lambda v:hexb(('r46-inference|'+v).encode())):
            if k in out:continue
            r=run(prompts[k]);assert r['prompt']==len(prompts[k]) and 0<=r['generated']<=24
            stream.write(json.dumps([k,r],ensure_ascii=False)+'\n');stream.flush();out[k]=r
            if len(out)%256==0:print('answered',len(out),round(perf_counter()-start,2),flush=True)
    assert set(out)==set(prompts)
    checks=sorted(prompts,key=lambda v:hexb(('r46-repeat|'+v).encode()))[:32]
    replay={k:run(prompts[k]) for k in checks}
    assert all(replay[k]['answer']==out[k]['answer'] for k in checks)
    put(D/'answers.json.gz',out);put(D/'replay.json',replay)
    put(D/'answer-seal.json',dict(input=ident,answer=sha(D/'answers.json.gz'),code=sha(D/'answer.py'),
        engine=sha(D/'engine.py'),replay=sha(D/'replay.json'),n=len(out),run_seconds=perf_counter()-start))
    print('sealed all',len(out),flush=True)

if __name__=='__main__':main()
