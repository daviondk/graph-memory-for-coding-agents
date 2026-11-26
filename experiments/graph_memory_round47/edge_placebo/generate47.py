"""Blind inference on prompt tokens; signed, byte-identical cap-96 prompts can be reused."""
import json
from time import perf_counter
from base47 import *
from engine47 import produce,model_check
def main():
    check();model_check()
    freeze=get(D/'input-seal.json');assert freeze['prompts']==sha(D/'prompts.json.gz')
    prompts=get(D/'prompts.json.gz');oldp=signed(R46,'prompts.json.gz');olda=signed(LONG,'answers.json.gz')
    out={};new=[];reuse=[]
    for k,seq in prompts.items():
        if k in oldp:
            assert seq==oldp[k];out[k]=olda[k];reuse.append(k)
        else:new.append(k)
    progress=P47/('answers-'+freeze['prompts']+'.jsonl')
    if progress.exists():
        for line in progress.read_text(encoding='utf8').splitlines():
            k,row=json.loads(line);assert k in new and k not in out;out[k]=row
    start=perf_counter()
    with progress.open('a',encoding='utf8') as log:
        for k in sorted(new,key=lambda x:hexb(('r47-infer|'+x).encode())):
            if k in out:continue
            out[k]=produce(prompts[k])
            log.write(json.dumps([k,out[k]],ensure_ascii=False)+'\n');log.flush()
    audit={}
    for name,group in [('old',reuse),('new',new)]:
        selection=sorted(group,key=lambda x:hexb(('r47-repeat|'+x).encode()))[:32]
        audit[name]={k:produce(prompts[k]) for k in selection}
    assert set(out)==set(prompts)
    put(D/'answers.json.gz',out);put(D/'replay.json',audit)
    counts={s:sum(v!=out[k] for k,v in data.items()) for s,data in audit.items()}
    put(D/'answer-seal.json',dict(input=sha(D/'input-seal.json'),model=sha(MODEL),runtime=sha(SERVER),
        source=sha(LONG/'seal.json'),answers=sha(D/'answers.json.gz'),audit=sha(D/'replay.json'),code=sha(D/'generate47.py'),
        engine=sha(D/'engine47.py'),new=len(new),reused=len(reuse),audit_different=counts,seconds=perf_counter()-start))
    print('sealed',len(new),len(reuse),counts,flush=True)
if __name__=='__main__':main()
