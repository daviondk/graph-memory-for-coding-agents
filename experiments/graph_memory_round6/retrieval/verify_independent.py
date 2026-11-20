"""Independent top-1 score calculation and cluster resampling. No ranker or grader imported."""
import gzip,hashlib,json
from collections import Counter,defaultdict
from datetime import datetime,timezone
from pathlib import Path
import numpy as np
import pyarrow.parquet as pq

D=Path(__file__).resolve().parent
def load(p):return json.loads(Path(p).read_bytes())
def rows(p):
    with gzip.open(p,'rt',encoding='utf8') as f:yield from map(json.loads,f)
def sha(p):
    with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()

def bootstrap(y):
    g=sorted(y);cnt=np.array([len(y[k]) for k in g]); d=np.array([sum(y[k]) for k in g]);rng=np.random.default_rng(190611)
    b=[]
    for _ in range(40):
        ii=rng.integers(len(g),size=(250,len(g)))
        b.extend(d[ii].sum(1)/cnt[ii].sum(1))
    return np.quantile(b,[.025,.975])

def main():
    first=load(D/'results.json');primary=load(D/'method_lock.json')
    for fn,h in primary['code'].items():assert sha(D/fn)==h
    original=list(rows(D/'decisions.jsonl.gz'));target={}
    for filename,plan in load(D/'roster.json').items():
        if 'train' in plan:continue
        p=Path(filename);tab=pq.read_table(p,columns=['repo_name','gold_snippet_index'])
        for st,items in plan.items():
            for j,i in items:target[st,p.stem.rsplit('_',1)[0],i]=tab.column(1)[j].as_py()
    def compute(pred,labels,stage,lang,arm,base,reported):
        hits=Counter();deltas=defaultdict(list)
        for r in pred:
            s=r.get('stage','original')
            if s!=stage or not r['panel'].startswith(lang):continue
            g=labels[s,r['panel'],r['idx']]
            for a in [arm,base]:
                o=r['orders'][a];assert sorted(o)==list(range(r['n']));hits[a]+=int(o[0]==g)
            diff=int(r['orders'][arm][0]==g)-int(r['orders'][base][0]==g)
            deltas[r['project']].append(diff)
        ci=bootstrap(deltas)
        assert hits[arm]==reported['items']['full']['hits'][0] and hits[base]==reported['items'][base]['hits'][0]
        x=reported['diff']['full-'+base];assert abs(ci[0]-x['lo'][0])<.004 and abs(ci[1]-x['hi'][0])<.004
        return dict(hits=dict(hits),projects=len(deltas),n=sum(map(len,deltas.values())),independent_cluster_ci=ci.tolist())
    check={}
    for stage,base in [('primary','r4'),('strict','unix')]:
        check[stage]=compute(original,target,stage,'java','full',base,first['overall'][stage+'_java'])
    archive=D/'replication';tar={}
    for panel,ids in load(archive/'roster.json').items():
        col=pq.read_table(archive/(panel+'.parquet'),columns=['gold_snippet_index']).column(0)
        for i in ids:tar['original',panel,i]=col[i].as_py()
    val=load(archive/'results.json')
    check['independent_python_archive']=compute(rows(archive/'decisions.jsonl.gz'),tar,'original','python','alignment','r4',val['stats'])
    # Full original-file SHA-256 verification for both source members and all non-derived reporting inputs.
    src=load(archive/'source.json')['members']
    for k,info in src.items():
        p=archive/(k+('.gz' if k in {'cff','cfr'} else '.parquet'))
        assert sha(p)==info['sha']
    for name,meta in [(D/'paired.jsonl.gz',first['pairs_hash']),(archive/'pairs.jsonl.gz',val['pairs_sha']),
                      (D/'decisions.jsonl.gz',load(D/'decision_lock.json')['predictions'])]:
        assert sha(name)==meta
    check['utc']=datetime.now(timezone.utc).isoformat()
    (D/'verification.json').write_text(json.dumps(check,indent=2),encoding='utf8')
    print(check)
if __name__=='__main__':main()
