"""Freeze independent eligible issues and predetermined fixed-quota query routing."""
import collections
import json
import math
from pathlib import Path
import sys
from pyarrow import parquet

ROOT=Path(__file__).resolve().parent
WORK=ROOT.parents[1]
R17=WORK/'graph_memory_round17/line_action'
SELECTION=R17.parent/'line_selection'
INPUT=WORK/'graph_memory_round16/anchor_transfer'
sys.path.insert(0,str(R17))
import study as original
from study import read,sha,compact,canonical,lexical,prompt
from predict import tokens
def put(n,x):
    import gzip
    b=compact(x);(ROOT/n).write_bytes(gzip.compress(b,mtime=0) if n.endswith('.gz') else b)
def hashed(namespace,*parts):return sha(('/'.join([namespace,*parts])).encode())
def items(regions,visible):
    count=sum(b-a+1 for p,a,b in regions)
    if count==60:return original.block_menu(regions,visible)
    out={}
    for path,s,e in sorted(regions):
        for start in range(s,e+1,12):
            end=min(e,start+11)
            out[f'{path}:{start}-{end}']={'p':path,'s':start,'e':end,'lines':[visible[path,n] for n in range(start,end+1)]}
    return out
def calculate_gap(issue,menu):
    order=canonical(menu)
    docs={k:tokens(menu[k]['p']+'\n'+'\n'.join(menu[k]['lines'])) for k in order}
    df=collections.Counter(w for words in docs.values() for w in words)
    scores={k:sum(math.log((1+len(order))/(1+df[w]))+1 for w in sorted(words & tokens(issue))) for k,words in docs.items()}
    ranked=sorted(order,key=lambda x:-scores[x])
    assert ranked[0]==lexical(issue,menu)
    gap=scores[ranked[0]]-scores[ranked[1]] if len(ranked)>1 else None
    return ranked[0],gap,scores
def prepare():
    old=read(R17/'MANIFEST_SHA256.json'); assert old['study.py']==sha((R17/'study.py').read_bytes())
    assert old['menus.json.gz']==sha((R17/'menus.json.gz').read_bytes())
    sx=read(SELECTION/'prediction-lock.json')
    for n,h in sx['files'].items():assert sha((SELECTION/n).read_bytes())==h
    for n,h in sx['inputs'].items():assert sha((WORK/n).read_bytes())==h
    training={r['id'] for r in read(R17/'menus.json.gz')};assert len(training)==24
    forecasts={(r['instance_id'],r['source']):r['pred']['lexical24'] for r in read(SELECTION/'predictions.json.gz') if r['panel']=='independent'}
    logs=collections.defaultdict(list)
    for r in read(INPUT/'input-priors.json.gz'):
        i=r['instance_id'];model=r['source'];regions=forecasts[i,model]
        n=sum(e-s+1 for p,s,e in regions);rank=0 if n==60 else 1 if n else 2
        logs[i].append((rank,hashed('r18/gate/source',i,model),r,regions))
    relevant=set(logs)-training;assert len(logs)==54 and len(relevant)==30
    verified=WORK/'graph_memory_round3/real_swe/official_verified.parquet'
    issues={r['instance_id']:r['problem_statement'] for r in parquet.read_table(verified,columns=['instance_id','problem_statement']).to_pylist()}
    menus=[];assign=[];prompts={}
    for i in sorted(relevant):
        _,__,r,regions=min(logs[i],key=lambda v:v[:2]);source=r['source']
        visible={(v['path'],n):s for v in r['views3'] for n,s in v['lines']}
        menu=items(regions,visible)
        choice=gap=h=None;scores={}
        if menu:
            choice,gap,scores=calculate_gap(issues[i],menu)
            obj=prompt(issues[i],menu);raw=compact(obj);h=sha(raw)
            assert h not in prompts
            prompts[h]=raw.decode()
        menus.append({'id':i,'source':source,'repo':r['repo'],'base':r['base_commit'],'menu':menu})
        assign.append({'id':i,'source':source,'lines':sum(len(b['lines']) for b in menu.values()),'sha':h,'gap':gap,'static_choice':choice,'scores':scores})
    eligible=[x for x in assign if x['sha']]
    n=len(eligible);quota=n//2
    gapids={r['id'] for r in sorted(eligible,key=lambda x:(x['gap'] if x['gap'] is not None else math.inf,hashed('r18/gate/tiebreak',x['id'])))[:quota]}
    randomids={r['id'] for r in sorted(eligible,key=lambda x:hashed('r18/gate/control',x['id']))[:quota]}
    for r in assign:
        r['route_gap']=r['id'] in gapids;r['route_hash']=r['id'] in randomids
    roster={'prior_task_ids':sorted(training),'eligible':n,'quota':quota,'all':len(assign),'complete':sum(x['lines']==60 for x in assign),
            'nonempty_partial':sum(0<x['lines']<60 for x in assign),'empty':sum(x['lines']==0 for x in assign),'route_overlap':len(gapids&randomids),
            'inputs':{'prior_menu_manifest':sha((R17/'MANIFEST_SHA256.json').read_bytes()),'r17_source':sha((R17/'study.py').read_bytes()),'forecast_lock':sha((SELECTION/'prediction-lock.json').read_bytes())}}
    put('menus.json.gz',menus);put('prompts.json.gz',prompts);put('route.json',assign);put('roster.json',roster)
    put('design.lock.json',{n:sha((ROOT/n).read_bytes()) for n in ['gate.py','PROTOCOL_RU.md','menus.json.gz','prompts.json.gz','route.json','roster.json']})
    print('cohort',roster['all'],n,quota,'partial',roster['nonempty_partial'],flush=True)
def run():
    original.ROOT=ROOT
    original.run()
if __name__=='__main__':{'prepare':prepare,'run':run}[sys.argv[1]]()
