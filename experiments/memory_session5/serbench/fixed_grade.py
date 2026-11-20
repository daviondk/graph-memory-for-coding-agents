import gzip,hashlib,json,sys
from collections import defaultdict
from grade import ROOT,np,read,score_predictions
def run(verify):
    meta=ROOT/'fixed_layout.jsonl.gz'
    if not verify:
        with gzip.open(meta,'wt',encoding='utf8') as f:
            for row in read(ROOT/'fixed_queries.jsonl.gz'):
                ids=row.pop('ids');row['arms']=list(ids);row['n_tokens']={k:len(z) for k,z in ids.items()}
                row['sha_tokens']={k:hashlib.sha256(json.dumps(z).encode()).hexdigest() for k,z in ids.items()}
                f.write(json.dumps(row,separators=(',',':'))+'\n')
    queries=read(meta);vectors=np.load(ROOT/'dense_vectors.npy',mmap_mode='r')
    qvec=np.load(ROOT/'fixed_vectors.npy');pos=0;pred=[]
    states={r['state_id']:r for r in read(ROOT/'dense_inputs.jsonl.gz')}
    for r in queries:
        cs=states[r['state_id']]['candidates'];doc=vectors[[v for k,v in cs]].astype('float32')
        doc/=np.linalg.norm(doc,axis=1)[:,None]
        for arm in r['arms']:
            q=qvec[pos].astype('float32');pos+=1
            scores=doc@(q/np.linalg.norm(q));ix=np.argsort(-scores,kind='stable')[:8]
            pred.append({'method':arm,'state_id':r['state_id'],'ranked_evidence_ids':[cs[i][0] for i in ix]})
    assert pos==len(qvec)==2500
    predpath=ROOT/'fixed_predictions.jsonl.gz'
    if verify:assert pred==read(predpath)
    else:
        with gzip.open(predpath,'wt',encoding='utf8') as f:
            for r in pred:f.write(json.dumps(r,separators=(',',':'))+'\n')
    items=read(ROOT/'cal_candidates.jsonl.gz');labs=read(ROOT/'upstream/data/cal500/labels.jsonl.gz')
    per,summary=score_predictions(pred,labs,[5,8],dataset=items)
    by=defaultdict(dict);repo={r['state_id']:r['repo'] for r in items}
    for r in per:by[r['method']][r['state_id']]=r['mss_complete@5']
    names=sorted(set(repo.values()));draws=np.random.default_rng(17112026).integers(0,len(names),(10000,len(names)))
    ds={}
    for arm in by:
        z=defaultdict(list)
        for s,x in by['addresses'].items():z[repo[s]].append(x-by[arm][s])
        d=np.array([sum(z[r]) for r in names]);c=np.array([len(z[r]) for r in names]);ci=np.quantile(d[draws].sum(axis=1)/c[draws].sum(axis=1),[.025,.975])
        ds[arm]={'delta':d.sum()/c.sum(),'ci':ci.tolist(),'wins':sum(x>0 for vs in z.values() for x in vs),'losses':sum(x<0 for vs in z.values() for x in vs)}
    out={'arms':summary,'addresses_minus':ds,'unique_foreign':len({r['foreign_state'] for r in queries}),'same_length':sum(r['foreign_note_qwen']==r['own_note_qwen'] for r in queries),'shared_prefix_mean_tokens':np.mean([r['q_first'] for r in queries]).item()}
    if verify:assert json.loads((ROOT/'fixed_results.json').read_bytes())==out;print('PASS 2500 fixed-query dense decisions, wrong memory and CIs')
    else:
        (ROOT/'fixed_results.json').write_text(json.dumps(out,indent=2))
        print({k:v['mss_complete@5'] for k,v in summary.items()});print(ds)
if __name__=='__main__':run('--verify' in sys.argv)
