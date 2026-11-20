"""Secondary fixed stale-memory horizon sensitivity; all unscored nonadjacent pairs."""
import collections, csv
from sources import ROOT, canon, sha, save
from predict import read
from scope import reuse
from score import counts, rr

METHODS = ['always_replay','always_reuse','direct_file','dynamic_files','scopes','scopes_guards','observed_branches_guards']
OUT = ROOT / 'age'

def main():
    forecasts = []
    for study, base in [('initial', ROOT), ('external', ROOT / 'external_validation')]:
        versions = collections.defaultdict(list)
        for r in read(base / 'sources.json'):
            if not r.get('skip'): versions[r['pkg']].append(r['v'])
        for pkg, vs in versions.items():
            metadata = {}
            for v in vs:
                records = read(base / 'runs' / pkg / v / 'traced.json')
                metadata[v] = {r['key']: {k:r[k] for k in ['key','entry','covered']} for r in records}
            for i, old in enumerate(vs):
                for j in range(i+2,len(vs)):
                    new = vs[j]
                    for key, prior in metadata[old].items():
                        forecasts.append({'study':study,'pkg':pkg,'old':old,'new':new,'gap':j-i,'key':key,
                                          **reuse(pkg,old,new,prior,metadata[new][key]['entry'])})
    with (OUT/'decisions.csv').open('w', encoding='utf8', newline='') as f:
        w=csv.DictWriter(f, fieldnames=list(forecasts[0]));w.writeheader();w.writerows(forecasts)
    save(OUT/'lock.json',{'sha256':{path:sha((ROOT/path).read_bytes()) for path in ['age/PROTOCOL.md','scope.py','age_eval.py','age/decisions.csv','observation_lock.json','external_validation/observation_lock.json']}})
    values={}
    for study,base in [('initial', ROOT), ('external', ROOT/'external_validation')]:
        for f in (base/'runs').glob('*/*/plain.json'):
            for r in read(f):values[f.parent.parent.name,f.parent.name,r['key']]=r['value']
    groups=collections.defaultdict(list)
    for r in forecasts:
        pkg,old,new,key = [r[k] for k in ['pkg','old','new','key']]
        r['changed']=int(values[pkg,old,key]!=values[pkg,new,key])
        for group in ['all',r['study'],pkg,'gap '+str(r['gap'])]:
            groups[group].append(r)
    with (OUT/'per_check.csv').open('w', encoding='utf8', newline='') as f:
        w=csv.DictWriter(f, fieldnames=list(forecasts[0]));w.writeheader();w.writerows(forecasts)
    result={group:{m:counts(rows,m) for m in METHODS} for group,rows in groups.items()}
    save(OUT/'results.json',result)
    print(result['all'])
if __name__=='__main__':main()
