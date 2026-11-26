"""Independent token-only transfer evaluation. Reuse no measured GPU times."""
from pathlib import Path
import sys,gzip,json,hashlib,struct
from collections import defaultdict,Counter
import numpy as np
from run_gpu import util,Cache,GD,DigestKeys,DigestInts,tokenkey,COUNT
from inventory import TOK
D=util.D
def work():
    assert util.sha(D/'TRANSFER_RU.md')=='abb274653d56a1692e60026f4d2d47a9ac5b93e09f261b26629dbd73e99d7769'
    allowed=set(util.read(util.P47/'panels.json')['train']);old=set(util.read(util.BASE/'inventory.json.gz'));assert len(allowed)==179 and not allowed&old
    source=util.read(util.BASE/'input-seal.json');assert util.sha(TOK)==source['source'];tk=util.read(TOK);ns=bytes.fromhex(source['namespace']);rows={};groups=defaultdict(list);cache={};od={}
    with gzip.open(util.PUB/'items.jsonl.gz','rt',encoding='utf8') as f:
        for z in map(json.loads,f):
            q=z['state_id']
            if q not in allowed:continue
            ev=z['trajectory_prefix'];runs={e.get('run_id') for e in ev};g=util.h(util.canon([z['repo'],z['instance_id'],z['base_commit'],next(iter(runs)) if len(runs)==1 and next(iter(runs)) else q]))
            hist=[util.h(util.canon(e)) for e in ev];t=tk['states'][q];docs=[]
            for k in t['doc']:
                if k not in cache:
                    v=tk['tokens'][k][1];cache[k]=(tokenkey(ns,v),len(v))
                docs.append(cache[k])
            row=dict(repo=z['repo'],group=g,hist=hist,docs=[(k.hex(),n) for k,n in docs],query=len(tk['tokens'][t['three']][1]))
            rows[q]=row;groups[g].append(q);od[q]=dict(docs)
    pre={}
    for q,z in rows.items():
        candidates=defaultdict(list);hist=z['hist']
        for a in groups[z['group']]:
            h=rows[a]['hist']
            if h and len(h)<len(hist) and h==hist[:len(h)]:candidates[tuple(h)].append(a)
        pre[q]=[min(candidates[h],key=lambda q:util.h('r48-representative'+q)) for h in sorted(candidates,key=len)]
    return rows,pre,od
def cost(trace,docs,scope):
    ans={}
    for m in ('proposed','lru','gdsf'):
        pol=GD('batch',COUNT,DigestInts()) if m=='gdsf' else Cache('proposed' if m=='proposed' else 'hot_lru',COUNT,DigestKeys())
        for q in trace:
            d=docs[q]
            if m=='lru':d={k:d[k] for k in sorted(d,key=lambda k:(d[k],-int.from_bytes(k,'big')))}
            if m=='gdsf':hits,saved=pol.update(d)
            else:hits,saved=pol.operate(d)
        ans[m]=dict(hits=hits,inter=saved,net_tokens=scope['query']+sum(d.values())-saved)
    return ans
def sumup(qs,rows,obs):
    gg=defaultdict(list)
    for q in qs:gg[rows[q]['repo']].append(q)
    repos=sorted(gg);n=len(repos);rs={};vec=lambda field:np.array([sum(obs[q][field] for q in gg[r]) for r in repos]);den=vec('total')
    bs=np.random.default_rng(490731).multinomial(n,np.repeat(1/n,n),size=20000)
    totals={}
    for m in ('lru','gdsf','proposed'):
        a=[obs[q]['arm'][m] for q in qs];totals[m]=dict(inter=sum(v['inter'] for v in a),net=sum(v['net_tokens'] for v in a),hits=sum(v['hits'] for v in a))
    for m in ('lru','gdsf'):
        dv=np.array([sum(obs[q]['arm']['proposed']['inter']-obs[q]['arm'][m]['inter'] for q in gg[k]) for k in repos])
        rs[m]=dict(delta=dv.sum()/den.sum(),delta_tokens=int(dv.sum()),ci=np.quantile((bs@dv)/(bs@den),[.025,.975]).tolist(),macro=float(np.mean(dv/den)))
    return dict(states=len(qs),repos=n,total=int(sum(den)),within=int(sum(vec('within'))),arms=totals,contrasts=rs)
def main():
    rows,p,docs=work();pp=util.read(D/'panel.json');included={q for z in pp['selected'] for q in z['seq']};obs={}
    for q,z in rows.items():
        doc=sum(v for k,v in z['docs']);n=sum(docs[q].values());tot=z['query']+doc
        obs[q]=dict(repo=z['repo'],total=tot,within=doc-n,prior=p[q],arm=cost(p[q]+[q],docs,z))
    util.put('transfer-inputs.json.gz',rows);util.put('transfer-outcomes.json.gz',obs)
    panels={};qm={'all':list(rows),'not_hardware':[q for q in rows if q not in included],'hardware':sorted(included)}
    for name,fn in [('cold',lambda n:n==0),('one',lambda n:n==1),('two_plus',lambda n:n>=2)]:qm[name]=[q for q,v in p.items() if fn(len(v))]
    for k,qs in qm.items():panels[k]=sumup(qs,rows,obs)
    assert qm['hardware'] and len(qm['hardware'])==24
    util.put('transfer-results.json',dict(plan=util.sha(D/'TRANSFER_RU.md'),program=util.sha(Path(__file__)),inputs=util.sha(D/'transfer-inputs.json.gz'),outcomes=util.sha(D/'transfer-outcomes.json.gz'),
        source=util.sha(util.BASE/'input-seal.json'),previous_states_overlap=0,panels=panels))
    print('Full transfer',panels['all'])
if __name__=='__main__':main()

