"""Strict upstream scoring with repeated-sampling uncertainty clustered by repository."""
import collections,gzip,hashlib,json,sys
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'upstream/src'))
from serbench.scoring import score_predictions,validate_predictions

def read(path):
    with (gzip.open(path,'rt',encoding='utf-8') if path.suffix=='.gz' else path.open(encoding='utf-8')) as f:return [json.loads(line) for line in f]
def compute():
    lock=json.loads((ROOT/'decision_lock.json').read_bytes())
    for file,h in lock.items():assert hashlib.sha256((ROOT/file).read_bytes()).hexdigest()==h
    preds=read(ROOT/'cal_predictions.jsonl.gz');labels=read(ROOT/'upstream/data/cal500/labels.jsonl.gz')
    cals=read(ROOT/'cal_candidates.jsonl.gz');test=read(ROOT/'test_candidates.jsonl.gz')
    folds={r['state_id']:r for r in read(ROOT/'cal_folds.jsonl.gz')}
    byrepo=collections.defaultdict(set)
    for r in folds.values():byrepo[r['repo']].add(r['outer_fold'])
    assert len(byrepo)==174 and all(len(v)==1 for v in byrepo.values()) and not (set(byrepo)&{r['repo'] for r in test})
    validate_predictions(read(ROOT/'test500_predictions.jsonl'),test,strict=True)
    per,summary=score_predictions(preds,labels,[5,8],dataset=cals,strict=True)
    grouped=collections.defaultdict(dict)
    for r in per:grouped[r['state_id']][r['method']]=r
    repos=sorted(byrepo);rng=np.random.default_rng(17112026)
    draws=rng.integers(0,len(repos),size=(10000,len(repos)))
    contrasts={}
    for baseline in ['independent','diversity','sdk_bm25','masked_bm25']:
        item={}
        for metric in ['mss_complete@5','mss_complete@8','group_recall@5']:
            group=collections.defaultdict(list)
            for sid,d in grouped.items():group[folds[sid]['repo']].append(d['pair_completion'][metric]-d[baseline][metric])
            dif=np.array([sum(group[r]) for r in repos]);cnt=np.array([len(group[r]) for r in repos]);boot=dif[draws].sum(axis=1)/cnt[draws].sum(axis=1)
            ds=[v for z in group.values() for v in z];item[metric]={'delta':float(np.mean(ds)),'ci':np.quantile(boot,[.025,.975]).tolist(),'wins':sum(v>0 for v in ds),'losses':sum(v<0 for v in ds)}
        contrasts[baseline]=item
    groups={r['state_id']:len(r['required_evidence_groups']) for r in labels}
    slices={}
    for k,flag in [('one',lambda g:g==1),('two_plus',lambda g:g>=2)]:
        sub=[d for sid,d in grouped.items() if flag(groups[sid])]
        slices[k]={'n':len(sub),'complete5':{name:sum(x[name]['mss_complete@5'] for x in sub) for name in summary}}
    out={'upstream':summary,'contrasts':contrasts,'descriptive_groups':slices,'groups':dict(collections.Counter(groups.values())),'repos':len(repos),'instances':len({x['instance_id'] for x in cals}),'cal_observed_id_rows':sum(bool(r['observed_evidence_ids']) for r in cals),'test_observed_id_rows':sum(bool(r['observed_evidence_ids']) for r in test)}
    return per,out
if __name__=='__main__':
    per,out=compute()
    if '--verify' in sys.argv:
        assert json.loads(json.dumps(out))==json.loads((ROOT/'results.json').read_bytes())
        assert per==read(ROOT/'official_per_state.jsonl.gz')
        print('PASS official grade 2500 predictions on 500 states and 500 held-out submissions validated; cluster intervals reproduced')
    else:
        (ROOT/'results.json').write_text(json.dumps(out,indent=2))
        with gzip.open(ROOT/'official_per_state.jsonl.gz','wt',encoding='utf-8') as f:
            for r in per:f.write(json.dumps(r,separators=(',',':'))+'\n')
        print(out['groups'],out['descriptive_groups'])
        print({k:[v['mss_complete@5'],v['mss_complete@8'],v['group_recall@5']] for k,v in out['upstream'].items()})
        print(out['contrasts']['independent'])
