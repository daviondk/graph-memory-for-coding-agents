"""Freeze inputs and create a label-free source projection for each selected query."""
import gzip
import hashlib
import json
import os
import sys
from pathlib import Path
from collections import defaultdict
for key in ('RAYON_NUM_THREADS','OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS'):
    os.environ[key]='1'
HERE=Path(__file__).resolve().parent
WORK=HERE.parents[1]
R20=WORK/'graph_memory_round20'
R19=WORK/'graph_memory_round19'
PRIVATE=Path('D:/CodexResearch/x20-published-reader')
MODEL=PRIVATE/'model'
REV='6a967332efedfe5aca9b85b8310cc68d9ac6f881'
WEIGHT='3127f7ead12786b4ab740191105d8a8e0febe6f8109e479ea0c1e9238fd79398'
FINE=R20/'fine_train/model.json'
E5=Path('D:/CodexResearch/x20-isetrace-runtime/inputs/tokenizer.json')
SPLIT=WORK/'graph_memory_round22/native_multiseed/official580/split.json.gz'
sys.path.insert(0,str(R20/'fine_read'))
import reader as rd
import numpy as np
def h(data):return hashlib.sha256(data).hexdigest()
def sha(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def load(p):return json.loads(gzip.decompress(p.read_bytes()) if p.suffix=='.gz' else p.read_bytes())
def save(p,obj):
    p.parent.mkdir(parents=True,exist_ok=True)
    data=json.dumps(obj,sort_keys=True,ensure_ascii=False,separators=(',',':'),allow_nan=False).encode()+b'\n'
    temp=p.with_suffix(p.suffix+'.partial')
    temp.write_bytes(gzip.compress(data,mtime=0) if p.suffix=='.gz' else data)
    temp.replace(p)
def choose(stage,n):
    rows=load(SPLIT)[stage][:500] if stage=='dev' else load(SPLIT)[stage]
    groups=defaultdict(list)
    for row in rows:groups[row['t']].append(row['q'])
    def key(kind,s):return h(f'r23-verbatim-{kind}-v1|{stage}|{s}'.encode())
    return [{'t':t,'q':min(groups[t],key=lambda q:key('query',q))} for t in sorted(groups,key=lambda t:key('traj',t))[:n]]
def roots(stage,i):
    return (rd.source('dev' if stage=='dev' else 'dense',i),rd.blocks_path('dev' if stage=='dev' else 'dense',i),rd.DEV if stage=='dev' else rd.stream.CACHE)
def plan():
    receipt=HERE/'plan.json'
    doc={'protocol':sha(HERE/'PROTOCOL_RU.md'),'split':sha(SPLIT),'sha_model':{p.name:sha(p) for p in sorted(MODEL.iterdir()) if p.is_file()},'weights':WEIGHT,'hf_revision':REV,'fine_model':sha(FINE),'e5_tokenizer':sha(E5),'fine_features':sha(Path(rd.__file__)),'selection':{s:choose(s,n) for s,n in [('dev',4),('test',192)]}}
    assert doc['sha_model']['model.safetensors']==WEIGHT
    if receipt.exists():assert doc==load(receipt)
    else:save(receipt,doc)
    return doc
def prepare(stage):
    rec=load(HERE/'plan.json')
    selected={r['t']:r['q'] for r in rec['selection'][stage]}
    model=load(FINE)['models']['full'];per={}
    for i in range(8):
        ranks_path,geometry_path,cache=roots(stage,i)
        ranks={r['t']:r['rr'][:16] for r in load(ranks_path) if selected.get(r['t'])==r['q']}
        with gzip.open(geometry_path,'rt',encoding='utf-8') as src:
            for line in src:
                base=json.loads(line);t=base['t']
                if t not in ranks:continue
                q=selected[t];rr=ranks[t];raw=load(cache/f'{i}-{t}.json.gz');ad=base['addresses']
                query=dict(raw['q'])[q];parents=[];kept_indices={}
                for node in rr:
                    assert len(node['source_spans'])==1
                    sp=node['source_spans'][0];addr=(sp['event_id'],sp['json_pointer']);idx=ad.index(list(addr))
                    a,b=sp['char_start'],sp['char_end'];field=raw['fields'][addr[0]]
                    assert 0<=a<b<=len(field)
                    parents.append([idx,a,b]);kept_indices[idx]=field
                valid=[z for z in base['blocks'] if any(e==z[0] and a<=z[1] and z[2]<=b for e,a,b in parents)]
                local={'addresses':ad,'blocks':valid};geom=rd.geometry(local,raw,rr)
                assert all(geom[2])
                x,rp,rl=rd.features(query,rr,valid,geom)
                z=x[:,model['columns']]
                p=1/(1+np.exp(-np.clip((z-model['mean'])/model['scale']@model['coef']+model['offset'],-200,200)))
                rows=[[int(e),int(a),int(b),int(c),int(parent),float(prob/c)] for (e,a,b,c,_),parent,prob in zip(valid,rp,p,strict=True)]
                obj={'q':q,'t':t,'i':i,'query':query,'ad':ad,'fields':kept_indices,'parents':parents,'blocks':rows}
                srcfile=PRIVATE/stage/f'{q[6:]}.json.gz';save(srcfile,obj)
                per[q]={'t':t,'sha':sha(srcfile),'parents':len(rr),'blocks':len(rows),'raw':sha(cache/f'{i}-{t}.json.gz'),'rank_file':ranks_path.name,'geometry_file':geometry_path.name}
    assert len(per)==len(selected)
    save(HERE/f'{stage}-inputs.json',{'subset':per,'source_ranks':{roots(stage,i)[0].name:sha(roots(stage,i)[0]) for i in range(8)},'source_geometry':{roots(stage,i)[1].name:sha(roots(stage,i)[1]) for i in range(8)},'plan':sha(HERE/'plan.json'),'code':sha(Path(__file__))})
if __name__=='__main__':
    plan()
    if len(sys.argv)>1:prepare(sys.argv[1])
