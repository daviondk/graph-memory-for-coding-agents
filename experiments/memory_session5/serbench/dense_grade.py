import collections,gzip,hashlib,json,sys
from grade import read,score_predictions,ROOT,np
def rank():
    meta=json.loads((ROOT/'dense_runtime.json').read_bytes())
    with (ROOT/'dense_vectors.npy').open('rb') as f:assert hashlib.file_digest(f,'sha256').hexdigest()==meta['vectors_sha256']
    vectors=np.load(ROOT/'dense_vectors.npy',mmap_mode='r')
    rs=[]
    for row in read(ROOT/'dense_inputs.jsonl.gz'):
        ids=[pair[0] for pair in row['candidates']]
        docs=np.asarray(vectors[[pair[1] for pair in row['candidates']]],dtype=np.float32)
        docs/=np.linalg.norm(docs,axis=1)[:,None]
        scores={}
        for name,q in row['queries'].items():
            query=vectors[q].astype('float32');query/=np.linalg.norm(query);scores[name]=docs@query
        for m in ['addresses','tail','arguments']:
            def ranks(score):
                order=np.argsort(-score,kind='stable');return np.argsort(order)+1
            scores['fusion_'+m]=1/(60+ranks(scores['state']))+1/(60+ranks(scores[m]))
        for name,values in scores.items():
            order=np.argsort(-values,kind='stable')[:8];rs.append({'state_id':row['state_id'],'method':name,'ranked_evidence_ids':[ids[i] for i in order]})
    return rs
def evaluate(rs):
    items=read(ROOT/'cal_candidates.jsonl.gz');labels=read(ROOT/'upstream/data/cal500/labels.jsonl.gz')
    per,summary=score_predictions(rs,labels,[5,8],dataset=items);repos={r['state_id']:r['repo'] for r in items}
    by=collections.defaultdict(dict)
    for x in per:by[x['method']][x['state_id']]=x
    names=sorted(set(repos.values()));draws=np.random.default_rng(17112026).integers(0,len(names),(10000,len(names)))
    deltas={}
    for a,b in [('addresses','tail'),('addresses','arguments'),('addresses','state'),('addresses','issue'),
                ('fusion_addresses','fusion_tail'),('fusion_addresses','state')]:
        difs={}
        for metric in ('mss_complete@5','mss_complete@8','group_recall@5'):
            sums=collections.defaultdict(list)
            for s,r in by[a].items():sums[repos[s]].append(r[metric]-by[b][s][metric])
            d=np.array([sum(sums[n]) for n in names]);ct=np.array([len(sums[n]) for n in names]);ds=[x for v in sums.values() for x in v]
            difs[metric]={'delta':sum(ds)/len(ds),'ci':np.quantile(d[draws].sum(axis=1)/ct[draws].sum(axis=1),[.025,.975]).tolist(),'W':sum(x>0 for x in ds),'L':sum(x<0 for x in ds)}
        deltas[a+' minus '+b]=difs
    return per,{'arms':summary,'contrasts':deltas}
def save(path,rs):
    with gzip.open(ROOT/path,'wt',encoding='utf-8') as f:
        for r in rs:f.write(json.dumps(r,separators=(',',':'))+'\n')
if __name__=='__main__':
    rs=rank()
    if '--verify' in sys.argv:
        assert rs==read(ROOT/'dense_predictions.jsonl.gz')
    else:
        save('dense_predictions.jsonl.gz',rs)
        (ROOT/'dense_decision_sha256.txt').write_text(hashlib.sha256((ROOT/'dense_predictions.jsonl.gz').read_bytes()).hexdigest())
    per,out=evaluate(rs)
    if '--verify' in sys.argv:
        assert per==read(ROOT/'dense_per_state.jsonl.gz') and out==json.loads((ROOT/'dense_results.json').read_bytes());print('PASS dense vectors → rankings → official scores')
    else:
        save('dense_per_state.jsonl.gz',per);(ROOT/'dense_results.json').write_text(json.dumps(out,indent=2))
        print({k:(v['mss_complete@5'],v['mss_complete@8']) for k,v in out['arms'].items()})
        print(out['contrasts']['addresses minus tail'])
