"""Offline comparison across the matched physical arms and the untimed prior fresh oracle."""
from collections import defaultdict
from pathlib import Path
import gzip,hashlib,json,sys
import numpy as np
D=Path(__file__).resolve().parent
LONG=D.parent/'long_gpu'
CONTROL=D.parent/'cache_controls'
MODES=('proposed','s3','sieve')
METRICS=('wall_rank','wall_commit','compute_engine_s','rpc_wall','tokenizer_wall','tokens','calls','hit')


def read(path):
    data=path.read_bytes()
    return json.loads(gzip.decompress(data) if path.suffix=='.gz' else data)

def output(file,data):
    blob=json.dumps(data,sort_keys=True,separators=(',',':'),allow_nan=False).encode()+b'\n'
    (D/file).write_bytes(gzip.compress(blob,mtime=0) if file.endswith('.gz') else blob)

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()

def main():
    pan=read(LONG/'panel.json');native=read(CONTROL/'R49-outcomes.json.gz');source=read(LONG/'raw-runs.json.gz');oracle=read(LONG/'ordinal-judgments.json.gz')
    sys.path.insert(0,str(D.parents[1]/'memory_session5/serbench/upstream/src'))
    from serbench import _reference_scorer as official
    raw=read(D/'receipts.json.gz');seal=read(D/'seal.json')
    assert sha(D/'receipts.json.gz')==seal['receipts'] and sha(D/'runner.py')==seal['signature']['runner']
    repos=[z['repo'] for z in pan['selected']]
    selected={q for z in pan['selected'] for q in z['seq']}
    gold_path=D.parents[1]/'memory_session5/serbench/upstream/data/cal500/labels.jsonl.gz'
    with gzip.open(gold_path,'rt',encoding='utf8') as f: gold={row['state_id']:row for row in map(json.loads,f) if row['state_id'] in selected}
    keys={'s3':'s3_costhot','sieve':'sieve_costhot','proposed':'proposed'}
    groups={};qc={};matched={}
    for c in pan['selected']:
        name=c['repo'];rr=raw[name];current={a:{k:0 for k in METRICS} for a in MODES}
        for j,q in enumerate(c['seq']):
            ref=source[name]['fresh'][j];ids=ref['ids'];g=oracle[q];qc[q]={}
            truth=gold[q]
            matched[q]=dict(repo=name,ids=ids,rank=ref['rank'],scores=ref['scores'],vector_sha=ref['vector_sha'],labels=g)
            for mode in MODES:
                z=rr[mode][j];cost=native[q];hit,saved=cost['batch'][keys[mode]]
                assert z['q']==q and z['hit']==hit and cost['total']-cost['within']-saved==z['tokens'] and ids==z['ids'] and z['rank']==np.argsort(-np.asarray(z['scores']),kind='stable').tolist()
                assert z['wall_commit']>=z['wall_rank']>=z['rpc_wall']>0 and sum(x for k,x in z['device_engines'].items() if 'cuda' in k.lower())>0
                assert len(z['resident_out'])<=31 and z['persistent_bytes']<=524288
                rrk=[ids[i] for i in z['rank']];out={}
                for k in [5,8]:
                    val=official.score_prediction(rrk[:k],truth,k)
                    out['mss'+str(k)]=val['mss_complete@'+str(k)]
                    out['group'+str(k)]=val['group_recall@'+str(k)]
                out['vector_matches']=sum(a==b for a,b in zip(ref['vector_sha'],z['vector_sha']));out['n_vectors']=len(z['vector_sha'])
                out['rank_equal']=ref['rank']==z['rank'];out['top5_equal']=ref['rank'][:5]==z['rank'][:5];out['top8_equal']=ref['rank'][:8]==z['rank'][:8]
                out['max_score_error']=max(abs(a-b) for a,b in zip(ref['scores'],z['scores']));qc[q][mode]=out
                for key in METRICS:current[mode][key]+=z[key]
        groups[name]=current
    bs=np.random.default_rng(492321).multinomial(8,np.full(8,0.125),size=20000)
    contrasts={};tot={m:{k:sum(g[m][k] for g in groups.values()) for k in METRICS} for m in MODES}
    for m in ('s3','sieve'):
        out={}
        for k in METRICS:
            base=np.array([groups[n][m][k] for n in repos]);prop=np.array([groups[n]['proposed'][k] for n in repos]);mean=1-prop.sum()/base.sum()
            boot=1-(bs@prop)/(bs@base)
            out[k]=dict(advantage=float(mean),ci=np.quantile(boot,[.025,.975]).tolist(),wins=int((prop<base).sum()),losses=int((prop>base).sum()),sum_difference=float((base-prop).sum()))
        contrasts[m]=out
    bymode={}
    for m in MODES:
        vals=[v[m] for v in qc.values()]
        agg={k:sum(v[k] for v in vals) for k in ['mss5','mss8','group5','group8','vector_matches','n_vectors','rank_equal','top5_equal','top8_equal']}
        agg['max_score_error']=max(v['max_score_error'] for v in vals);bymode[m]=agg
    output('oracle.json.gz',matched);output('quality.json.gz',qc)
    output('results.json',dict(states=24,repos=repos,totals=tot,groups=groups,comparisons=contrasts,quality=bymode,official_scorer=sha(Path(official.__file__)),source=sha(D/'seal.json')))
    print('Matched end-to-end savings:',{m:contrasts[m]['wall_rank'] for m in contrasts},'quality',bymode['proposed'])


if __name__=='__main__':main()

