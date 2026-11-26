"""Independent scalar frequency accumulator and iterative HGB traversal for all midpoint packets."""
import math
from common45 import *
import numpy as np

def cell(role,logrank):
    rank=round(math.expm1(logrank))
    return int(role)*5+sum(rank>edge for edge in (1,4,16,64))

def audit_table():
    counts=[[[0.]*4 for y in (0,1)] for i in range(10)];used=0
    for sh in range(8):
        with np.load(R42/f'train-{sh}.npz') as z:
            sem=z['sem13'];m=z['meta'];e=z['edge'];y=z['labels'];i=0
            for q,t,n,ids in signed(R42,f'train-{sh}.json.gz'):
                positives=int(y[i:i+n].sum());negatives=n-positives
                if positives and negatives:
                    used+=1
                    for j in range(i,i+n):
                        yi=int(y[j]);flag=int(e[j,4]>0)+2*int(e[j,5]>0)
                        counts[cell(m[j,0],sem[j,0])][yi][flag]+=.5/(positives if yi else negatives)
                i+=n
            assert i==len(y)
    saved=read(D/'table.json');diff=float(np.max(np.abs(np.array(counts)-saved['counts'])))
    offsets=[]
    for neg,pos in counts:
        combined=[a+b for a,b in zip(neg,pos)]
        inactive=sum(k>0 for k in combined)<2
        corr=[]
        for i,all_y in enumerate(combined):
            prior=(all_y+.25)/(sum(combined)+1)
            pp=(pos[i]+4*prior)/(sum(pos)+4);pn=(neg[i]+4*prior)/(sum(neg)+4)
            corr.append(0.0 if inactive else math.log(pp)-math.log(pn))
        offsets.append(corr)
    diff_log=float(np.max(np.abs(np.array(offsets)-saved['log_ratio'])))
    assert used==1966 and diff<1e-9 and diff_log<1e-12
    return offsets,diff,diff_log

def trees(model,x):
    # Each row follows its own node pointer. Previously terminal nodes stay fixed.
    ans=np.full(len(x),model['bias'],dtype=float);idx=np.arange(len(x))
    for tree in model['trees']:
        v=np.asarray(tree);col,left,right=(v[:,i].astype(int) for i in (0,2,3))
        nodes=np.zeros(len(x),dtype=int)
        while True:
            a=left[nodes];b=right[nodes]
            if np.array_equal(a,b):break
            nodes=np.where(a==b,nodes,np.where(x[idx,col[nodes]]<=v[nodes,1],a,b))
        ans+=v[nodes,4]
    return ans

def run():
    check_registration();offsets,diff,diff_log=audit_table()
    model=signed(R42,'models.json')['models']['rich']['hgb']
    receipt=read(D/'mid-forecast.json');checks=changed=0;maxcells=0
    for sh in range(8):
        pp=D/f'mid-{sh}.json.gz';assert sha(pp)==receipt['files'][pp.name];pack=read(pp)
        with np.load(R42/f'test-{sh}.npz') as z:
            m=z['meta'];e=z['edge'];cost=np.rint(np.expm1(m[:,1])).astype(int)
            bits=[int(a>0)+2*int(b>0) for a,b in e[:,4:6]];rows=signed(R42,f'test-{sh}.json.gz')
            for s in SEEDS:
                sem=z[f'sem{s}'];rich=trees(model,np.column_stack([sem,m]))
                rank=np.rint(np.expm1(sem[:,0])).astype(int)
                score=[v+offsets[cell(role,lr)][b] for v,role,lr,b in zip(rich,m[:,0],sem[:,0],bits)]
                j=0
                for q,t,n,ids in rows:
                    order=sorted(range(j,j+n),key=lambda k:(-score[k],rank[k]))
                    budget=2048;ind=[]
                    for k in order:
                        if cost[k]<=budget:
                            budget-=cost[k];ind.append(ids[k-j])
                    prior=pack[q][2][str(s)];assert ind==prior['table']
                    changed+=set(ind)!=set(prior['rich']);checks+=1;j+=n
                assert j==len(rank);maxcells+=j
    save(D/'audit.json',dict(mass_max_abs=diff,log_ratio_max_abs=diff_log,checked_lists=checks,
             candidate_scores=maxcells,changed_membership_vs_rich=changed,mid=sha(D/'mid-forecast.json'),
             table=sha(D/'table.json'),code=sha(D/'audit.py')))
    print('independent replay',checks,maxcells,changed,diff,diff_log,flush=True)

if __name__=='__main__':run()
