from pathlib import Path
import gzip,json,hashlib,base64
from collections import Counter
import numpy as np
D=Path(__file__).resolve().parent
def read(p):return json.loads(p.read_bytes())
def rr(p):
    with gzip.open(p,'rt',encoding='utf8') as f:yield from map(json.loads,f)
def sha(x):return hashlib.sha256(x).hexdigest()
def main():
    res=read(D/'result.json');bounded=read(D/'bounded_results.json');lock=read(D/'bounded_lock.json')
    census={};panels={'unbounded':[z for z in rr(D/'items.jsonl.gz') if z['point']=='cut'],'pre_edit':[z for z in rr(D/'items.jsonl.gz') if z['point']=='before'],'bounded':list(rr(D/'bounded_items.jsonl.gz'))}
    for panel,rows in panels.items():
        assert len(rows)==253 and len({(r['id'],r['cut']) for r in rows})==253
        ids=sorted({z['repo'] for z in rows});groups=np.array([ids.index(z['repo']) for z in rows]);n=np.bincount(groups)
        report={}
        for a,b in ([('address','base'),('lru_address','lru_editor'),('address','lru_address')] if panel=='bounded' else [('address','base')]):
            v=np.array([int(z['methods'][a]['full'])-int(z['methods'][b]['full']) for z in rows]);s=np.bincount(groups,weights=v)
            rg=np.random.default_rng(31118);re=rg.integers(len(n),size=(10000,len(n)));ci=np.quantile(s[re].sum(1)/n[re].sum(1),[.025,.975]).tolist();dis=[]
            for code in range(2**len(n)):
                sign=[1 if code>>ii&1 else -1 for ii in range(len(n))];dis.append(abs(s@sign)>=abs(s.sum()))
            report[a+'-'+b]=dict(by_repo={p:[int(s[j]),int(n[j])] for j,p in enumerate(ids)},cluster_repo_ci=ci,exact_repo_p=float(np.mean(dis)),gain_tasks=len({z['id'] for z,vv in zip(rows,v) if vv>0}),loss_tasks=len({z['id'] for z,vv in zip(rows,v) if vv<0}),loo=[float((s.sum()-s[j])/(n.sum()-n[j])) for j in range(len(n))])
        census[panel]=report
    seen=Counter();maxsize=Counter();caps=Counter()
    for k in range(8):
        cut={(iid,t):pack for iid,t,pack in rr(D/f'bounded_cuts_{k}.gz')}
        for iid,t,dig in rr(D/f'bounded_steps_{k}.gz'):
            for a,(size,digest) in dig.items():
                seen[a]+=1;maxsize[a]=max(maxsize[a],size);assert size<=4096
                if (iid,t) in cut:
                    raw=base64.b64decode(cut[iid,t][a]);assert sha(raw)==digest and size==len(raw) and raw[0] in (0,1);caps[a]+=1
    assert set(seen.values())=={3386} and len(set(caps.values()))==1
    comp=read(D/'source_receipt.json');pair=Counter();size=0
    for r in comp['records']:pair.update(r['counts']);size+=r['size']
    audit=dict(repo_analysis=census,checked_steps=seen,checked_cuts=caps,max_bytes=maxsize,source_tasks=len(comp['records']),source_bytes=size,source_counts=pair,primary_data=sha((D/'bounded_items.jsonl.gz').read_bytes()))
    (D/'audit.json').write_text(json.dumps(audit,indent=1),encoding='utf8')
if __name__=='__main__':main()

