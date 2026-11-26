"""Compare a fresh full SQLite replay against signed archive outcomes. Timing ledgers have independent hashes."""
import argparse
import json
from pathlib import Path
from hashlib import sha256

def compare(original, replay):
    def load(p,n):
        return json.loads((p/n).read_bytes())
    a=load(original,'results.json')
    b=load(replay,'results.json')
    for k in ('boundaries','traces','full_map_checks','final_reopened_maps','arms'):
        assert a[k]==b[k], k
    for arm, rows in a['physical'].items():
        for left,right in zip(rows,b['physical'][arm],strict=True):
            for k in ('before_checkpoint_total','file','max_cache_rows','objects','pair_population','shm','wal'):
                assert left[k]==right[k],(arm,k)
    databases={p.name:sha256(p.read_bytes()).hexdigest() for p in original.glob('*.sqlite')}
    for n,h in databases.items():
        assert sha256((replay/n).read_bytes()).hexdigest()==h,n
    for n in ('compact-results.json',):
        left,right=load(original,n),load(replay,n)
        assert left['objects']==right['objects'] and left['pages_bytes']==right['pages_bytes']
    statements={}
    for arm in a['arms']:
        statements[arm]={}
        for budget in ('1','4'):
            x,y=a['mean_per_pass'][budget][arm],b['mean_per_pass'][budget][arm]
            for k in ('probes','hits'):assert x[k]==y[k],(arm,k)
            statements[arm][budget]=[x['probes'],x['hits']]
    return {'boundaries':a['boundaries'],'traces':a['traces'],'full_maps_per_run':a['full_map_checks'],
            'reopened_maps_per_run':a['final_reopened_maps'],'seven_database_sha256':databases,
            'probes_and_cache_hits_by_reads':statements,'identical_compact_pages':True,
            'rerun_mean_one_read_ms':{arm:b['mean_per_pass']['1'][arm]['mean_ms'][0] for arm in a['arms']},
            'timing_ledgers_independent':a['reference_seal']!=b['reference_seal']}

if __name__=='__main__':
    par=argparse.ArgumentParser()
    par.add_argument('replay',type=Path)
    par.add_argument('--out',type=Path)
    opts=par.parse_args()
    report=compare(Path(__file__).resolve().parent/'bounded_physical',opts.replay)
    raw=(json.dumps(report,indent=2,sort_keys=True)+'\n').encode()
    if opts.out:
        if opts.out.is_file():assert opts.out.read_bytes()==raw
        else:opts.out.write_bytes(raw)
    print(report['full_maps_per_run'],len(report['seven_database_sha256']),report['identical_compact_pages'])
