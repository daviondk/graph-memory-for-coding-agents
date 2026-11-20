"""Prior training and baseline artifacts are consumed read-only. Test gold is opened by grade.py."""
import os
for env_key in ("OMP_NUM_THREADS","OPENBLAS_NUM_THREADS","MKL_NUM_THREADS","RAYON_NUM_THREADS"):
    os.environ[env_key] = "1"
import gzip
import hashlib
import json
import pickle
import sys
import time
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime,timezone
from pathlib import Path
import numpy as np
import pyarrow.parquet as pq
import sklearn
from sklearn.ensemble import HistGradientBoostingClassifier

D=Path(__file__).resolve().parent
WORK=D.parents[1]
R=WORK/"graph_memory_round4/repo"
E=R.parent/"encoder"
R5=WORK/"graph_memory_round5/retrieval"
sys.dont_write_bytecode=True
sys.path.insert(0,str(R))
from data_io import files, panel_name, rows
from memory import encode, features
from archive_java import author_function, Adapter
from native_run import load_module
from field_model import make

def now():return datetime.now(timezone.utc).isoformat()
def load(p):return json.loads(Path(p).read_bytes())
def save(name,v):(D/name).write_text(json.dumps(v,ensure_ascii=False,indent=2),encoding='utf8')
def readgz(p):
    with gzip.open(p,'rt',encoding='utf8') as f:yield from map(json.loads,f)
def writegz(name,data):
    with gzip.open(D/name,'wt',encoding='utf8') as f:
        for row in data:f.write(json.dumps(row,separators=(',',':'))+'\n')
def sha(p):
    with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def digest(s):return hashlib.sha256(s.encode()).hexdigest()

def roster():
    old=load(R/'roster.json'); strict=load(R/'paired_roster.json'); wide=load(R/'strict_roster.json')
    arc=load(R5/'roster.json'); plan={}; existing_repos=set()
    for p in files('java','train')+files('java','test')+files('python','test'):
        names=pq.read_table(p,columns=['repo_name']).column(0).to_pylist()
        selections={}
        own=dict(old[p.stem])
        selections['train' if 'train' in p.stem else 'primary']=own
        if p.stem.startswith('java') and 'test' in p.stem:
            selections['strict']={i:k for i,k in wide[p.stem] if k in strict[panel_name(p.stem)]}
        existing_repos.update(names[i] for x in selections.values() for i in x)
        plan[str(p)]={k:[[i,x] for i,x in m.items()] for k,m in selections.items()}
    for p in sorted((R/'archive_inputs').glob('*.parquet')):
        inds=arc[panel_name(p.stem)]
        plan[str(p)]={'archive':[[i,i] for i in inds]}
        names=pq.read_table(p,columns=['repo_name']).column(0).to_pylist()
        existing_repos.update(names[i] for i in inds)
    for p in files('python','test'):
        # Python official sharding has a single file per stratum.
        assert p.stem.endswith('_0000') and len(files('python','test'))==4
        names=pq.read_table(p,columns=['repo_name']).column(0).to_pylist()
        count=Counter(); chosen=[]
        for j in sorted(range(len(names)),key=lambda j:digest(f'R6-fresh-v1|{p.stem}|{j}')):
            if names[j] in existing_repos or count[names[j]]>=4:continue
            chosen.append([j,j]);count[names[j]]+=1
            if len(chosen)==150:break
        plan[str(p)]['fresh']=sorted(chosen)
    save('roster.json',plan)
    sources=[R/'models.pkl',R/'memory.py',R/'experiment.py',R/'roster.json',R/'paired_roster.json',
             R/'strict_roster.json',R/'repo_author_similarity.py',R/'repo_author_utils.py',
             R/'publisher_repobench.py',R/'publisher_arms.py',R/'publisher_common.py',R5/'roster.json',
             R5/'neural_predictions.jsonl.gz',R/'archive.pred.jsonl.gz',E/'predictions.jsonl.gz',
             R/'strict_java.pred.jsonl.gz',R/'python.pred.jsonl.gz',R/'java.pred.jsonl.gz',
             R/'paired_java_cfr.json',R/'paired_java_cff.json',R/'lexical_java.jsonl.gz',
             R/'lexical_python.jsonl.gz',R/'../..'/'graph_memory_round3/repo/inputs/codegen_tokenizer.json']
    for cache in ['cache','strict_cache']:
        for p in (R/cache).glob('*'):
            if p.suffix in {'.json','.npz'}:sources.append(p)
    lock=dict(utc=now(),protocol=sha(D/'PROTOCOL_RU.md'),code={n:sha(D/n) for n in ['field_model.py','run.py']},
              roster=sha(D/'roster.json'),input={p:sha(p) for p in plan},
              dependencies={str(p.relative_to(WORK)):sha(p) for p in sources},numpy=np.__version__,sklearn=sklearn.__version__)
    save('method_lock.json',lock)
    print('locked', {k:sum(len(v.get(k,[])) for v in plan.values()) for k in ['train','primary','strict','archive','fresh']},flush=True)

def pack(path, stage, ids):
    p=Path(path)
    train=stage=='train'
    cols=['code','context','repo_name']+(['gold_snippet_index'] if train else [])
    panel=panel_name(p.stem)
    cache='cache' if stage in {'train','primary'} else ('strict_cache' if stage=='strict' else None)
    data=lookup=source=None
    if cache:
        data=np.load(R/cache/(p.stem+'.npz'))
        source=data['f3'];offset=data['offset']
        meta=load(R/cache/(p.stem+'.json'))
        lookup={r[1] if stage=='strict' else r[0]:(j,r) for j,r in enumerate(meta)}
    if stage in {'archive','fresh'}:
        jacc=author_function('repo_author_similarity.py','jaccard_similarity')
        tok=Adapter()
        load_module('common','publisher_common.py');load_module('arms','publisher_arms.py')
        pub=load_module('repobench','publisher_repobench.py')
    meta_out=[];xx=[];yy=[];ww=[];zmap=dict(ids)
    for i,row in enumerate(rows(p,cols)):
        if i not in zmap:continue
        idx=zmap[i];repo=row['repo_name'];code=row['code'];docs=row['context'];n=len(docs)
        q='\n'.join(code.splitlines()[-3:]);h=digest(code)
        if cache:
            j,m=lookup[idx];a,b=offset[j:j+2]
            if stage=='strict':assert (m[0],m[2],m[4],len(m[3]))==(panel,repo,h,n)
            else:assert (m[1],m[2],m[4])==(repo,n,h)
            base=source[a:b,:43]
        else:
            base=features(code,encode(docs),3)
        field,links=make(q,docs)
        shift=1+int(digest('R6-placebo|'+q)[:12],16)%max(1,n-1)
        xx.append(np.column_stack([base,field,links,np.roll(links,shift,axis=0)]))
        refs={}
        if stage in {'archive','fresh'}:
            refs['jaccard']=sorted(range(n),key=lambda j:jacc(q,docs[j],tok),reverse=True)
            refs['bm25']=pub.bm25_rank(q,docs)
        meta_out.append([stage,panel,idx,repo,n,h,digest(q),refs])
        if train:
            g=row['gold_snippet_index'];assert m[-1]==g and 0<=g<n
            yy.extend(k==g for k in range(n));ww.extend(1 if k==g else 1/max(1,n-1) for k in range(n))
    assert len(meta_out)==len(zmap)
    print(stage,p.stem,len(meta_out),flush=True)
    return meta_out,np.concatenate(xx) if xx else np.zeros((0,116),np.float32),yy,ww

def transform(tasks):
    records=[];x=[];y=[];w=[]
    with ProcessPoolExecutor(3) as pool:
        jobs=[pool.submit(pack,*task) for task in tasks]
        for job in jobs:
            m,a,b,c=job.result();records.extend(m)
            if m:x.append(a)
            y.extend(b);w.extend(c)
    return records,np.concatenate(x),np.array(y),np.array(w)

def column_map(width):
    # first 43 coincide exactly with incumbent; 41 direct + 16 incoming/outgoing + 16 shuffled.
    width_direct=width-32
    return {'full':list(range(width_direct+16)),
            'direct':list(range(width_direct)),
            'placebo':list(range(width_direct))+list(range(width_direct+16,width)),
            'only_fields':list(range(43,width_direct))}

def main():
    roster()
    plan=load(D/'roster.json')
    tasks=lambda train:[(p,k,ids) for p,v in plan.items() for k,ids in v.items() if bool(k=='train')==train and ids]
    start=time.monotonic();train,x,y,w=transform(tasks(True));models={}
    cols=column_map(x.shape[1])
    for arm,ids in cols.items():
        m=HistGradientBoostingClassifier(max_iter=80,max_leaf_nodes=15,min_samples_leaf=28,
            learning_rate=.10,l2_regularization=1,random_state=261119,early_stopping=False)
        models[arm]=m.fit(x[:,ids],y,sample_weight=w)
    with (D/'models.pkl').open('wb') as f:pickle.dump(models,f)
    training=set(r[3] for r in train)
    save('fit_lock.json',dict(utc=now(),sha=sha(D/'models.pkl'),method=sha(D/'method_lock.json'),
         n=len(train),candidates=len(y),projects=len(training),columns=cols,elapsed_s=time.monotonic()-start))
    pred_start=time.monotonic()
    cases,allx,_,_=transform(tasks(False))
    with (R/'models.pkl').open('rb') as f:old=pickle.load(f)
    scores={a:m.predict_proba(allx[:,cols[a]])[:,1] for a,m in models.items()}
    scores['r4']=old[3,'graph'].predict_proba(allx[:,:43])[:,1]
    expected={}
    for lang in ['java','python','strict_java']:
        for panel,idx,k,repo,cost,h,e,arms in readgz(R/(lang+'.pred.jsonl.gz')):
            if k!=3:continue
            key=('strict' if lang=='strict_java' else 'primary',panel,idx)
            expected[key]=[repo,h,arms['graph'],arms.get('publisher_bm25')]
    lex={}
    for lang in ['java','python']:
        for p,i,k,v in readgz(R/('lexical_'+lang+'.jsonl.gz')):
            if k==3:lex[p,i]=v
    extra={}
    for r in readgz(E/'predictions.jsonl.gz'):
        if r['query']=='3':extra['strict',r['panel'],r['idx'],'unix']=r['rank']
    for conf in ['cff','cfr']:
        for p,i,k,n,v in load(R/('paired_java_'+conf+'.json')):
            if k==3:extra['strict',p,i,'semlith']=v
    for r in readgz(R5/'neural_predictions.jsonl.gz'):
        if r['query']==3:
            for a in ['unix','direct','graph']:
                # Keys here follow the R5 serialization (baseline unix or encoder).
                if a in r['orders']:extra['archive',r['panel'],r['idx'],'r5_'+a]=r['orders'][a]
    output=[]; off=0; matches=0
    for stage,panel,idx,repo,n,h,qhash,refs in cases:
        assert repo not in training
        arms={a:np.argsort(-vec[off:off+n],kind='stable').tolist() for a,vec in scores.items()}
        off+=n;key=stage,panel,idx
        if key in expected:
            proj,ph,v,bm=expected[key];assert (repo,h,arms['r4'])==(proj,ph,v)
            matches+=1;arms['bm25']=bm if stage=='strict' else lex[panel,idx]
        arms.update(refs)
        for a in ['unix','semlith','r5_unix','r5_graph','r5_direct']:
            if (*key,a) in extra:arms[a]=extra[*key,a]
        if stage=='strict':assert {'unix','semlith'}<=arms.keys()
        if stage=='archive':assert arms.get('r5_graph')==arms['r4'] and 'r5_direct' in arms
        assert all(sorted(v)==list(range(n)) for v in arms.values())
        output.append(dict(stage=stage,panel=panel,idx=idx,project=repo,n=n,input_hash=h,query_hash=qhash,orders=arms))
    writegz('decisions.jsonl.gz',output)
    save('decision_lock.json',dict(utc=now(),predictions=sha(D/'decisions.jsonl.gz'),fit=sha(D/'fit_lock.json'),
         n=len(output),r4_matched=matches,training_projects_overlap=0,elapsed_prediction_s=time.monotonic()-pred_start))
if __name__=='__main__':main()
