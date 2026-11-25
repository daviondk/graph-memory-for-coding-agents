"""Independent paired comparisons and overlap audit; requires only the standard library."""
from bisect import bisect_right
from collections import Counter, defaultdict
import gzip
import hashlib
import json
import math
from pathlib import Path
from statistics import NormalDist

D = Path(__file__).resolve().parent
WORK = D.parents[1]
F = WORK/'graph_memory_round20/factor_reader'
G = WORK/'graph_memory_round20/residual_graph'
R = WORK/'graph_memory_round19/trained_rank'
TRUTH = WORK/'graph_memory_round18/isetrace_official/gold-spans.json.gz'
BUDGETS = (256, 512, 1024, 2048, 4096, 8192)
METRICS = ('coverage_512','coverage_1024','coverage_2048','full_support_2048',
           'recall_5','mrr','coverage_auc','full_support_auc')


def read(p):
    data=p.read_bytes()
    return json.loads(gzip.decompress(data) if p.suffix=='.gz' else data)


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def index(rows):
    out={r['q']:r for r in rows}
    assert len(out)==len(rows)
    return out


def spans(unit):
    return tuple(sorted((s['event_id'],s['json_pointer'],s['char_start'],s['char_end'])
                        for s in unit['source_spans']))


def gold_bitmasks(units, truth):
    # Assign one bit per character in the union of gold spans; one pooling-unit mask
    # can cover overlapping author annotations without double-counting.
    intervals=defaultdict(list)
    for s in truth:
        intervals[s['event_id'],s['json_pointer']].append((s['char_start'],s['char_end']))
    chunks=defaultdict(list);offset=0
    for k in sorted(intervals):
        merged=[]
        for a,b in sorted(intervals[k]):
            if merged and merged[-1][1]>=a:merged[-1]=(merged[-1][0],max(merged[-1][1],b))
            else:merged.append((a,b))
        for a,b in merged:
            chunks[k].append((a,b,offset))
            offset+=b-a
    assert offset>0
    masks=[]
    for unit in units:
        mask=0
        for ev,ptr,a,b in spans(unit):
            for lo,hi,start in chunks.get((ev,ptr),()):
                x,y=max(a,lo),min(b,hi)
                if x<y:
                    mask|=((1<<(y-x))-1)<<(start+x-lo)
        masks.append(mask)
    return masks,offset


def metrics(order, prices, masks, total):
    seen=0;hits=[0];spent=[0];first=None
    for rank,j in enumerate(order,1):
        seen|=masks[j]
        if first is None and masks[j]:first=rank
        hits.append(seen.bit_count())
        spent.append(spent[-1]+prices[j])
    keys=[bisect_right(spent,b)-1 for b in BUDGETS]
    cov=[hits[i]/total for i in keys]
    fs=[int(hits[i]==total) for i in keys]
    def auc(values):
        # Six budgets are equally spaced on log2 scale; normalized trapezoids.
        return (sum(values[1:-1])+(values[0]+values[-1])/2)/5
    return dict(zip(METRICS,[cov[1],cov[2],cov[3],fs[3],hits[min(5,len(order))]/total,
                              0.0 if first is None else 1/first,auc(cov),auc(fs)],strict=True))


def compare_pools(test_rows, full_rows):
    queries=set(full_rows);saw={};unit_total=0;max_error=0;tested_scalars=0
    fs=read(F/'hash64-seal.json')['files'];gs=read(G/'forecast-seal.json')['forecasts']
    ds=read(R/'forecast-seal.json')
    gold=read(TRUTH)
    split={r['q']:r['t'] for r in read(R/'split.json.gz')['test']}
    assert set(split)==queries==set(gold)
    for k in range(8):
        dense=R/f'forecasts-main-{k}.json.gz'
        ff=F/f'hash64-ranks-{k}.json.gz';gg=G/f'forecasts-rgcn-{k}.json.gz'
        assert sha(ff)==fs[ff.name] and sha(gg)==gs[gg.name]
        assert sha(dense) in json.dumps(ds)
        parents=index(read(dense));ours=index(read(ff));native=index(read(gg))
        assert set(parents)==set(ours)==set(native) and not set(saw)&set(parents)
        for q,r in parents.items():
            traj=r['t']
            assert traj==split[q]==ours[q]['t']==native[q]['t']==full_rows[q]['t'] and all(a[q]['t']==traj for a in test_rows.values())
            rr=r['rr'];ids={z['node_id']:j for j,z in enumerate(rr)}
            assert len(rr)==len(ids)
            unit_total+=len(rr);saw[q]=traj
            ordered=[]
            for node in native[q]['rr']:
                j=ids[node['node_id']]
                assert spans(node)==spans(rr[j]) and node['token_count']==rr[j]['token_count']>0
                ordered.append(j)
            prices=[v['token_count'] for v in rr]
            masks,total=gold_bitmasks(rr,gold[q])
            for name,ranking in [('rgcn',ordered),('degree',ours[q]['ranks']['degree']),('factor',ours[q]['ranks']['factor'])]:
                assert len(ranking)==len(ids)==len(set(ranking)) and set(ranking)==set(range(len(ids)))
                m=metrics(ranking,prices,masks,total);ref=full_rows[q] if name=='rgcn' else test_rows[name][q]
                for key,v in m.items():
                    gap=abs(v-ref[key]);max_error=max(max_error,gap);tested_scalars+=1
                    assert gap<1e-12,(q,name,key,gap)
    assert set(saw)==queries and len(queries)==2000 and len(set(saw.values()))==1207
    return dict(queries=len(queries),trajectories=len(set(saw.values())),matched_candidate_occurrences=unit_total,
                every_rank_is_permutation=True,node_id_token_cost_source_intervals_exact=True,
                independently_recomputed_scalars=tested_scalars,max_abs_discrepancy=max_error,gold_sha256=sha(TRUTH),split_sha256=sha(R/'split.json.gz'))


def main():
    test=F/'metrics-test-rows.json.gz';full=F/'metrics-full-rows.json.gz'
    assert read(F/'metrics-test.json')['rows']==sha(test) and read(F/'metrics-full.json')['rows']==sha(full)
    ours=read(test);base=read(full)['rgcn']
    assert set(ours)=={'dense','degree','factor'} and all(set(a)==set(base) for a in ours.values())
    audit=compare_pools(ours,base)
    cp=read(G/'checkpoint.json');checkpoints=cp['records']
    assert all(z['train_task_count']==3894 and z['dev_task_count']==500 for z in checkpoints)
    assert cp['trainer']['random_seed']==13
    records=[]
    for name in ('degree','factor'):
        for metric in METRICS:
            diff={q:r[metric]-base[q][metric] for q,r in ours[name].items()}
            n=len(diff);mean=math.fsum(diff.values())/n
            grouped=defaultdict(list)
            for q,x in diff.items():grouped[base[q]['t']].append(x-mean)
            g=len(grouped)
            se=(g/(g-1)*math.fsum(math.fsum(v)**2 for v in grouped.values()))**.5/n
            z=mean/se
            records.append(dict(arm=name,metric=metric,mean_difference_pp=100*mean,cluster_SE_pp=100*se,z=z,
                                two_sided_p=math.erfc(abs(z)/math.sqrt(2))))
    count=len(records);adjusted=0
    critical=NormalDist().inv_cdf(1-.05/(2*count))
    for rank,r in enumerate(sorted(records,key=lambda r:r['two_sided_p'])):
        adjusted=max(adjusted,min(1,(count-rank)*r['two_sided_p']))
        r['holm_adjusted_p']=adjusted
        r['reject_FWER_05']=adjusted<=.05
        r['holm_position']=rank+1
        r['bonferroni_simultaneous_95_ci_pp']=[r['mean_difference_pp']+s*critical*r['cluster_SE_pp'] for s in (-1,+1)]
    result=dict(method='Two-sided Gaussian approximation with paired cluster sandwich SE using G/(G-1); Holm step-down across all 16 contrasts. Optional simultaneous conservative Bonferroni CIs from the same SE. Clusters are 1207 trajectories, estimand is query-weighted.',
                limits='One matched R-GCN seed on a previously examined benchmark; adjusts for the specified 16 comparisons only. No model-seed, corpus or earlier analysis selection uncertainty.',
                candidate_audit=audit,r_gcn=dict(seed=13,train_queries=3894,dev_queries=500,checkpoint_epoch=cp['epoch'],checkpoint_weight_sha=cp['sha']),
                input_sha256={p.name:sha(p) for p in (test,full)},code_sha256=sha(Path(__file__)),
                rejected=sum(v['reject_FWER_05'] for v in records),rows=records)
    (D/'holm-audit.json').write_text(json.dumps(result,sort_keys=True,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf8')
    print(audit);print('rejected',result['rejected'])
    for r in sorted(records,key=lambda r:r['holm_position'])[:4]:print(r['arm'],r['metric'],r['mean_difference_pp'],r['holm_adjusted_p'])
if __name__=='__main__':main()

