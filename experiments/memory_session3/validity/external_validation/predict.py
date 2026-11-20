"""Project out observations before producing masks; freeze decisions before scoring."""
import collections,csv,json,time,sys,platform
from sources import ROOT,sha,save
from scope import reuse
def read(p):return json.loads(p.read_text(encoding='utf8'))
def main():
    release=collections.defaultdict(list)
    for x in read(ROOT/'sources.json'):
        if not x.get('skip'):release[x['pkg']].append(x['v'])
    oracle={}; ledger=[]
    for pkg,vs in release.items():
        for v in vs:
            t=read(ROOT/'runs'/pkg/v/'traced.json')
            oracle[pkg,v]=[{k:r[k] for k in ['key','entry','covered']} for r in t]
    start=time.perf_counter()
    for pkg,vs in release.items():
        for old,new in zip(vs,vs[1:]):
            new_meta={r['key']:r['entry'] for r in oracle[pkg,new]}
            for r in oracle[pkg,old]:
                ledger.append({'pkg':pkg,'old':old,'new':new,'key':r['key'],**reuse(pkg,old,new,r,new_meta[r['key']])})
    with (ROOT/'decisions.csv').open('w',encoding='utf8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(ledger[0]));w.writeheader();w.writerows(ledger)
    lock={n:sha((ROOT/n).read_bytes()) for n in ['decisions.csv','PROTOCOL.md','predict.py','scope.py','roster.json','sources.json','observation_lock.json','testmon_pair.py']}
    save(ROOT/'prediction_lock.json',{'sha256':lock,'rows':len(ledger),'selection_seconds':time.perf_counter()-start,'platform':platform.platform(),'python':sys.version})
    print('blinded',len(ledger),flush=True)
if __name__=='__main__':main()

