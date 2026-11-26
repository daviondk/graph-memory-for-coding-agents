from pathlib import Path
from collections import defaultdict,Counter
import gzip,hashlib,json
D=Path(__file__).resolve().parent;W=D.parents[1];BASE=W/'graph_memory_round48/embedding_reuse';PREV=W/'graph_memory_round48/cache_admission';P47=W/'graph_memory_round47/facet_reader';PUB=W/'memory_session5/serbench/upstream/data/cal500'
def canon(v):return json.dumps(v,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode()
def h(v):return hashlib.sha256(v.encode() if isinstance(v,str) else v).hexdigest()
def sha(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def read(p):
    b=p.read_bytes();return json.loads(gzip.decompress(b) if p.suffix=='.gz' else b)
def put(k,v):
    p=D/k;b=canon(v)+b'\n';tmp=p.with_suffix(p.suffix+'.tmp');tmp.write_bytes(gzip.compress(b,mtime=0,compresslevel=4) if p.suffix=='.gz' else b);tmp.replace(p)
def main():
    assert sha(D/'PROTOCOL_RU.md')=='be4a19b07dfdfba41396dd4a454be8c9b9b9097e1e5d9965dd546f9f08d6096f'
    p=read(P47/'panels.json');allowed=set(p['train']);old=set(read(BASE/'inventory.json.gz'));assert not old&allowed
    trace=defaultdict(dict);meta={}
    with gzip.open(PUB/'items.jsonl.gz','rt',encoding='utf8') as f:
        for z in map(json.loads,f):
            q=z['state_id']
            if q not in allowed:continue
            ev=z['trajectory_prefix'];runs={e['run_id'] for e in ev}
            if len(runs)!=1 or not next(iter(runs)):continue
            hist=tuple(h(canon(e)) for e in ev);a=(z['repo'],z['instance_id'],z['base_commit'],next(iter(runs)))
            entry=trace[a]
            if hist not in entry or h('r48-representative'+q)<h('r48-representative'+entry[hist]):entry[hist]=q
            meta[q]=dict(group=h(canon(a)),repo=a[0],events=hist)
    si=[]
    for a,z in trace.items():
        for hx,q in z.items():
            if any(len(v)>len(hx) and v[:len(hx)]==hx for v in z):continue
            seq=[z[t] for t in sorted([k for k in z if k and hx[:len(k)]==k],key=len)]
            if len(seq)>=3:si.append(dict(scope=h(canon(a)),repo=a[0],seq=seq,priority=h('r49-long-hardware'+canon(seq).decode())))
    allchains=sorted(si,key=lambda x:x['priority']);selected=[];rr=set()
    designs=[['fresh','proposed','gdsf','lru'],['proposed','lru','fresh','gdsf'],['lru','gdsf','proposed','fresh'],['gdsf','fresh','lru','proposed']]
    for z in allchains:
        if z['repo'] in rr:continue
        z2=dict(z);z2['methods']=designs[len(selected)%4];selected.append(z2);rr.add(z['repo'])
        if len(selected)==8:break
    assert len(selected)==8 and len(rr)==8
    put('panel.json',dict(all=allchains,selected=selected,scope={q:meta[q] for z in allchains for q in z['seq']},eligible_train=len(allowed),prior_overlap=0,
         source=sha(P47/'panels.json'),prior=sha(BASE/'manifest.json'),admission=sha(PREV/'manifest.json'),protocol=sha(D/'PROTOCOL_RU.md'),program=sha(Path(__file__))))
    print('Sealed',len(si),'eligible chains;',len(selected),'selected;',sum(len(z['seq']) for z in selected),'states.')
if __name__=='__main__':main()

