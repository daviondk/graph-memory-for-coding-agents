"""Apply the original four memory policies and a budget-balanced anchor policy."""
import collections
import importlib.util
from pathlib import Path

from cohort import ROOT, WORK, load, save, sha

ORIGINAL = WORK/'graph_memory_round15/external_scoring/views.py'
def imported():
    spec=importlib.util.spec_from_file_location("original_views",ORIGINAL)
    mod=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    h=load(ORIGINAL.parent/'views-seal.json')['files']['views.py']
    assert sha(ORIGINAL.read_bytes())==h
    return mod.rank_views,h

def mix(views):
    ordered=list(dict.fromkeys(v['path'] for v in views))
    if not ordered:return {'files':[],'regions':[],'lines':0}
    ends=[ordered[0]]
    if len(ordered)>1:
        ends.append(next(v['path'] for v in reversed(views) if v['path']!=ordered[0]))
    preferred=(ends+[p for p in ordered if p not in ends])[:3]
    data={p:sorted({n for v in views if v['path']==p for n,_ in v['lines']}) for p in preferred}
    selected={p:[] for p in preferred}
    for p in ends:selected[p]=data[p][:60//len(ends)]
    left=60-sum(map(len,selected.values()))
    for p in preferred:
        extra=data[p][len(selected[p]):][:left]
        selected[p]+=extra
        left-=len(extra)
    regions=[]
    for p in preferred:
        for n in selected[p]:
            if regions and regions[-1][0]==p and regions[-1][2]+1==n: regions[-1][2]=n
            else:regions.append([p,n,n])
    return {'files':preferred,'regions':regions,'lines':60-left}

def main():
    for n,h in load(ROOT/'inputs.lock.json').items():assert sha((ROOT/n).read_bytes())==h
    ranking,h=imported()
    grouped=[]
    for r in load(ROOT/'input-priors.json.gz'):
        for k in (3,6):
            v=r['views'+str(k)]
            arms=ranking(v);arms['split']=mix(v)
            visible={(x['path'],n) for x in v for n,_ in x['lines']}
            for name,p in arms.items():
                actual={(f,n) for f,s,e in p['regions'] for n in range(s,e+1)}
                assert len(actual)==p['lines']<=60 and actual<=visible and len(p['files'])<=3
            assert len({x['lines'] for x in arms.values()})==1 or k==6
            grouped.append({'id':r['instance_id'],'repo':r['repo'],'base_commit':r['base_commit'],'source':r['source'],'window':k,'views':len(v),'arms':arms})
    save('forecast.json.gz',grouped)
    save('predictions.lock.json',{'files':{n:sha((ROOT/n).read_bytes()) for n in ('policies.py','inputs.lock.json','forecast.json.gz')},'original_r15_sha256':h})
    print(len(grouped))
if __name__=='__main__':
    main()
