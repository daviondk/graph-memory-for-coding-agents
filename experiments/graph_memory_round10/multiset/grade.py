"""Grade sealed readouts. Issue is the unit; two directions/salts stay paired."""
from collections import defaultdict,Counter
import json,math,statistics
import numpy as np
from common import ROOT,R9,PANELS,ARMS,load,put,verify,sha
def signif(values,indices):
    a=np.array(values);sim=a[indices].mean(1)
    w=int((a< -1e-12).sum());l=int((a>1e-12).sum());n=w+l
    p=min(1,2*sum(math.comb(n,i) for i in range(min(w,l)+1))/2**n) if n else 1
    return {'mean_fraction':float(a.mean()),'lo':float(np.quantile(sim,.025)),'hi':float(np.quantile(sim,.975)),'better':w,'same':len(a)-n,'worse':l,'sign_p':p}
def main():
    verify(load(ROOT/'read_seal.json'))
    raw=load(ROOT/'reads.json.gz')['rows']
    cases={};legacy=defaultdict(lambda:Counter())
    sources={}
    for panel in PANELS:
        src=R9/panel/'outcomes.json';sources[str(src)]=sha(src)
        for f in load(src):cases[panel,f['task'],f['direction'],f['node']]=f
        arc=R9/'budget'/panel/'rows.json.gz';sources[str(arc)]=sha(arc)
        for t,d,node,b,s,arm,reads,exact,flip in load(arc):
            if arm=='selected':legacy[panel,t,b,s].update(extra=reads-exact,n=1,stale=int(flip and not reads))
    records=[];data={};series=defaultdict(lambda:Counter());times=defaultdict(lambda:[[],[],[],[]])
    for panel,t,d,b,s,arm,mask,tr,tw,cap,used,reprn in raw:
        coord=panel,t,d
        if coord not in data:
            old=load(ROOT/'old'/panel/(t+'_'+d+'.json.gz'));fut=set(load(ROOT/'future'/panel/(t+'_'+d+'.json.gz'))['changed'])
            data[coord]=(old['nodes'],[bool(set(ss)&fut) for ss in old['sets']])
        nodes,truth=data[coord]
        assert cap==b*len(nodes) and used<=cap and mask<1<<len(nodes)
        stats=Counter()
        for i,(name,actual) in enumerate(zip(nodes,truth)):
            selected=bool(mask&(1<<i));assert selected or not actual,(panel,t,d,b,s,arm,name)
            key=panel,t,d,name
            if key not in cases:continue
            outcome=cases[key]
            assert actual==outcome['selected']['symbol']
            stats.update(n=1,exact=int(actual),selected=int(selected),extra=int(selected and not actual),false_negative=int(actual and not selected),flip=int(outcome['changed']),stale=int(outcome['changed'] and not selected),stale_exact=int(outcome['changed'] and not actual))
        series[panel,t,b,s,arm].update(stats)
        times[panel,b,arm][0].append(tw/1e6); times[panel,b,arm][1].append(tr/1e3);times[panel,b,arm][2].append(used);times[panel,b,arm][3].append(reprn)
        records.append([panel,t,d,b,s,arm,dict(stats)])
    put(ROOT/'graded.json.gz',{'columns':['panel','issue','direction','bytes_per_test','salt','arm','counts'],'rows':records})
    summary={};effects={};per_issue={}
    for panelset in [[PANELS[0]],[PANELS[1]],PANELS]:
        name=panelset[0] if len(panelset)==1 else 'pooled'
        issues=sorted({(p,t) for p,t,b,s,arm in series if p in panelset})
        groups=[[i for i,(p,t) in enumerate(issues) if p==pn] for pn in panelset]
        rng=np.random.default_rng(10097)
        ix=np.concatenate([rng.choice(g,size=(10000,len(g)),replace=True) for g in groups],axis=1)
        for b in [64,256]:
            bucket=summary.setdefault(name,{}).setdefault(b,{})
            for arm in ARMS+['r9_native']:
                get=lambda p,t,s:legacy[p,t,b,s] if arm=='r9_native' else series[p,t,b,s,arm]
                by_salt=[sum((get(p,t,s) for p,t in issues),Counter()) for s in range(32)]
                extras=[r['extra'] for r in by_salt]
                diff=[r['stale'] for r in by_salt]
                cell={'n_scored':by_salt[0]['n'],'mean_extra':statistics.mean(extras),'salt_sd':statistics.pstdev(extras),'min_extra':min(extras),'max_extra':max(extras),'salt0_extra':extras[0],'mean_stale':statistics.mean(diff),'stale_range':[min(diff),max(diff)]}
                if arm!='r9_native':
                    arr=[times[p,b,arm] for p in panelset]
                    costs=[[x for block in arr for x in block[i]] for i in range(4)]
                    cell.update(exact=by_salt[0]['exact'],false_negatives_all_salts=sum(r['false_negative'] for r in by_salt),flips=by_salt[0]['flip'],stale_under_exact=by_salt[0]['stale_exact'],write_cpu_ms_p50=float(np.median(costs[0])),write_cpu_ms_p95=float(np.quantile(costs[0],.95)),read_cpu_us_p50=float(np.median(costs[1])),read_cpu_us_p95=float(np.quantile(costs[1],.95)),mean_payload_used=float(np.mean(costs[2])),representations=dict(Counter(costs[3])))
                bucket[arm]=cell
                per_issue.setdefault(name,{}).setdefault(b,{}).setdefault(arm,{})
                for p,t in issues:
                    per_issue[name][b][arm][t]={'n':get(p,t,0)['n'],'mean_extra':statistics.mean(get(p,t,s)['extra'] for s in range(32))}
            for a,base in [('xor_map','r9'),('flat_bloofi','r9'),('bucket','r9'),('sparse_dict','r9'),('old_selector','r9'),('xor_map','sparse_dict'),('xor_map','flat_bloofi'),('xor_map','bucket')]:
                sums=per_issue[name][b];ratios=[(sums[a][t]['mean_extra']-sums[base][t]['mean_extra'])/sums[a][t]['n'] for p,t in issues]
                effects.setdefault(name,{}).setdefault(b,{})[a+'-'+base]=signif(ratios,ix)
    put(ROOT/'results.json',dict(summary=summary,effects=effects,per_issue=per_issue,sources=sources))
    for b in [64,256]:
        for a,x in summary['pooled'][b].items():print(b,a,'extra',x['mean_extra'],'stale',x['mean_stale'])
        print('primary',effects['pooled'][b]['xor_map-r9'])
if __name__=='__main__':main()
