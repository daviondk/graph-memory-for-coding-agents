"""Post-result exploratory history compression grades with the same upstream scorer."""
from collections import defaultdict
import gzip,hashlib,json,sys
from grade import read,ROOT,np,score_predictions
def analyze():
    for n,h in json.loads((ROOT/'trace_lock.json').read_bytes()).items():assert hashlib.sha256((ROOT/n).read_bytes()).hexdigest()==h
    items=read(ROOT/'cal_candidates.jsonl.gz');labels=read(ROOT/'upstream/data/cal500/labels.jsonl.gz')
    per,summary=score_predictions(read(ROOT/'trace_predictions.jsonl.gz'),labels,[5,8],dataset=items)
    cost=read(ROOT/'trace_cost.jsonl.gz')
    armstats={}
    for name,v in summary.items():
        bs=[r['qwen_token_counts'][name] for r in cost]
        armstats[name]={'mean_tokens':np.mean(bs).item(),'max_tokens':max(bs),'mean':v}
        assert name=='complete' or max(bs)<=192
    by={};repos={r['state_id']:r['repo'] for r in items}
    for x in per:by.setdefault(x['method'],{})[x['state_id']]=x['mss_complete@5']
    names=sorted(set(repos.values()));draws=np.random.default_rng(17112026).integers(0,len(names),(10000,len(names)))
    contrasts={}
    for b in by:
        z=defaultdict(list)
        for s,x in by['addresses'].items():z[repos[s]].append(x-by[b][s])
        ds=np.array([sum(z[r]) for r in names]);counts=np.array([len(z[r]) for r in names])
        obs=[x for vals in z.values() for x in vals]
        contrasts[b]={'delta':sum(obs)/len(obs),'ci':np.quantile(ds[draws].sum(axis=1)/counts[draws].sum(axis=1),[.025,.975]).tolist(),'win':sum(x>0 for x in obs),'loss':sum(x<0 for x in obs)}
    return per,{'arms':armstats,'addresses_minus':contrasts,'n':len(cost)}
if __name__=='__main__':
    per,out=analyze()
    if '--verify' in sys.argv:
        assert json.loads((ROOT/'trace_results.json').read_bytes())==out
        assert per==read(ROOT/'trace_per_state.jsonl.gz');print('PASS 3500 history grades; emitted tokens and contrasts')
    else:
        with gzip.open(ROOT/'trace_per_state.jsonl.gz','wt',encoding='utf-8') as writer:
            for r in per:writer.write(json.dumps(r,separators=(',',':'))+'\n')
        (ROOT/'trace_results.json').write_text(json.dumps(out,indent=2))
        for n,v in out['arms'].items():print(n,v['mean_tokens'],v['mean']['mss_complete@5'],v['mean']['mss_complete@8'],out['addresses_minus'][n])
