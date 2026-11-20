"""Independent comparison and fairness diagnostic of static per-package env scopes."""
from collections import defaultdict
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from verify import rows,read,canonical,bit,seals,aggregate
from sources import save
from external_state import HERE,PROFILES,VERS,VARIED

def main():
    seals(HERE,read(HERE/'lock.json')['sha256'])
    values={};keys={};groups=defaultdict(list)
    for pkg in VERS:
        for i in range(4):
            plain={r['key']:canonical(r['value']) for r in read(HERE/'runs'/f'{pkg}-{i}-plain.json')}
            traced=read(HERE/'runs'/f'{pkg}-{i}-trace.json')
            assert len(plain)==len(traced)
            for r in traced:
                key=(pkg,str(i),r['key']);assert canonical(r['value'])==plain[r['key']]
                values[key]=plain[r['key']];keys[key]=set(r['env_reads'])
    for r in rows(HERE/'per_check.csv'):
        pkg=r['pkg'];old=(pkg,r['old'],r['key']);new=(pkg,r['new'],r['key'])
        p,q=PROFILES[int(r['old'])],PROFILES[int(r['new'])]
        change={k for k in VARIED if p.get(k)!=q.get(k)}
        data={'changed':values[old]!=values[new],'replay':False,'same_source':True,
              'full_environment':not change,'observed_env':not (keys[old]&change)}
        assert all(bit(r[k])==bit(v) for k,v in data.items())
        data['documented_per_package']=not (pkg=='wcwidth' and 'UNICODE_VERSION' in change)
        for g in ['all',pkg,'unicode_change='+str('UNICODE_VERSION' in change)]:groups[g].append(data)
    metrics={g:{m:aggregate(rs,m) for m in ['replay','same_source','full_environment','observed_env']} for g,rs in groups.items()}
    assert metrics==read(HERE/'results.json')['groups']
    material={g:aggregate(rs,'documented_per_package') for g,rs in groups.items()}
    save(HERE/'static_key_baseline.json',{'basis':'Post hoc. A priori documented wcwidth key, no keys for other deliberately unrelated control projects. Fixed project setting and two designed env variables.', 'groups':material})
    print('Targeted env cases:',metrics['all']['replay']['n'],'source-only stale',metrics['all']['same_source']['stale_reuse'],
          'static package baseline',material['all'],'dynamic env',metrics['all']['observed_env'])
if __name__=='__main__':main()
