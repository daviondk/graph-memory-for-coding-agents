from pathlib import Path
import os,hashlib,gzip,json
for k in ('OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','OMP_NUM_THREADS'):os.environ[k]='1'
import numpy as np
D=Path(__file__).resolve().parent;W=D.parents[1]
A=W/'graph_memory_round42/causal_ablation';R=W/'graph_memory_round43/relation_budget';Q=W/'graph_memory_round39/query_types';P=W/'graph_memory_round34/interval_witness'
def read(p):
    b=p.read_bytes();return json.loads(gzip.decompress(b) if p.suffix=='.gz' else b)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def save(p,x):
    data=(json.dumps(x,sort_keys=True,separators=(',',':'),allow_nan=False)+'\n').encode()
    p.write_bytes(gzip.compress(data,mtime=0) if p.suffix=='.gz' else data)
def labels():
    assert sha(D/'PROTOCOL_RU.md')=='d4e0d336b65104d02228a51fb69751de4b5dd4c72b111ed7c679e397e700a1be'
    assert sha(R/'manifest.json')=='9bfd04e1a265952d840c39d72971fec1ee303df43f765c01883fc8497a5e82e5'
    assert sha(A/'manifest.json')=='8b25a974d199d58609244ddb7154df7d4121c07c1a94d23678be407375094f3e'
    prior={x['q']:x for x in read(R/'outcomes.json.gz')}
    typ=read(Q/'strata.json.gz');atoms=read(P/'test-atoms.json.gz');rows=[]
    for sh in range(8):
        fp=A/f'test-{sh}.npz';idx=A/f'test-{sh}.json.gz'
        assert sha(fp)==read(A/'manifest.json')['files'][fp.name]
        with np.load(fp) as arr:
            e=arr['edge'];mc=arr['meta'];at=0
            for q,t,n,ext in read(idx):
                s=slice(at,at+n);at+=n;f=(e[s,4:6]>0).any(axis=1);ext=np.array(ext)
                cost=int(np.rint(np.expm1(mc[s,1])).sum())
                endpoints=set(ext[f].tolist());visible=set(ext.tolist())
                full=sum(b-a for _,a,b,_ in atoms[q]);available=sum(b-a for _,a,b,ids in atoms[q] if visible.intersection(ids))
                flow=sum(b-a for _,a,b,ids in atoms[q] if endpoints.intersection(ids))
                v=prior[q];assert (full==available)==v['eligible'] and full>0 and v['t']==t==typ[q]['t']
                rows.append(dict(q=q,t=t,pilot=v['pilot'],kind=typ[q]['kind'],events=typ[q]['events'],full=full,available=available,
                    incidence=flow,cost=cost,candidates=n,endpoint_candidates=len(endpoints),
                    fs={a:[v['arms'][str(seed)][a][0] for seed in (13,17,29,37,41)] for a in ('rich','value','value_bit','resource','cross')}))
            assert at==len(e)
    assert len(rows)==2000
    save(D/'question-strata.json.gz',rows)
    save(D/'labels.json',dict(labels=sha(D/'question-strata.json.gz'),outcomes=sha(R/'outcomes.json.gz'),source=sha(P/'test-atoms.json.gz'),types=sha(Q/'strata.json.gz')))

def analyze():
    base=[r for r in read(D/'question-strata.json.gz') if not r['pilot'] and r['available']==r['full']]
    assert len(base)==901
    groups,ix=np.unique([r['t'] for r in base],return_inverse=True)
    arms=('value','rich','resource','value_bit','cross')
    x=np.array([[r['fs'][a] for a in arms] for r in base]).transpose(0,2,1)
    masks={'all':np.ones(len(base),bool),'hit':np.array([r['incidence']>0 for r in base])}
    masks['none']=~masks['hit']
    masks['all_characters']=np.array([r['full']==r['incidence'] for r in base]);masks['partial']=masks['hit']&~masks['all_characters']
    feasible=np.array([r['cost']>2048 and r['endpoint_candidates']>0 for r in base])
    masks['matched_hit']=feasible&masks['hit'];masks['matched_none']=feasible&masks['none']
    for mode in ('direct_recall','linked_recall','multi_fact_recall'):
        masks[mode]=np.array([r['kind']==mode for r in base])
    masks['single_event']=np.array([r['events']==1 for r in base]);masks['joint_events']=~masks['single_event']
    names=list(masks);dens=[];sums=[];out={}
    for name,mask in masks.items():
        den=np.bincount(ix[mask],minlength=len(groups))
        totals=np.zeros((len(groups),5,len(arms)));np.add.at(totals,ix[mask],x[mask]);dens.append(den);sums.append(totals)
        out[name]=dict(n=int(mask.sum()),traces=int((den>0).sum()),means=dict(zip(arms,x[mask].mean(axis=(0,1)).tolist())))
    stacked=np.stack(sums,axis=1).reshape(len(groups),-1);denmat=np.column_stack(dens)
    rng=np.random.default_rng(440217);boots=[]
    for _ in range(100):
        sel=rng.integers(len(groups),size=(100,len(groups)));w=np.stack([np.bincount(v,minlength=len(groups)) for v in sel])
        d=w@denmat;assert (d>0).all()
        a=(w@stacked).reshape(100,len(names),5,len(arms))/d[:,:,None,None]
        seeds=rng.integers(5,size=(100,5))
        boots.append(a[np.arange(100)[:,None],:,seeds,:].mean(axis=1))
    boot=np.concatenate(boots);vals=boot[:,:,0]-boot[:,:,1]
    for i,name in enumerate(names):
        out[name]['value_vs_rich_ci']=np.quantile(vals[:,i],[.025,.975]).tolist()
    interactions=[]
    for left,right in [('hit','none'),('matched_hit','matched_none'),('linked_recall','direct_recall'),('multi_fact_recall','direct_recall'),('joint_events','single_event')]:
        l=out[left]['means'];r=out[right]['means'];k=vals[:,names.index(left)]-vals[:,names.index(right)]
        interactions.append(dict(left=left,right=right,delta=l['value']-l['rich']-r['value']+r['rich'],ci=np.quantile(k,[.025,.975]).tolist()))
    save(D/'results.json',dict(groups=out,interactions=interactions,source=sha(D/'question-strata.json.gz'),bootstrap=10000,seed=440217))
    print([(g,out[g]['n'],*[round(out[g]['means'][a]*100,2) for a in ('value','rich')]) for g in names]);print(interactions[:2])

if __name__=='__main__':labels();analyze()
