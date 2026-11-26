import gzip
import json
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parent
def gz(name):return json.loads(gzip.decompress((ROOT/name).read_bytes()))
def main():
    pairs=gz('pairs.json.gz');times=gz('times.json.gz')
    log=json.loads((ROOT/'run.json').read_bytes());groups={}
    modes=('direct','sqlite','ram','hull','memo')
    for panel in ('uniform','stress'):
        sub=[r for r in pairs if panel in r['parts']]
        queries=sorted({r['q'] for r in sub})
        rng=np.random.default_rng(47030);draws=rng.integers(len(queries),size=(10000,len(queries)))
        obs=[s for r in sub for s in r['tests']]
        stats={'pairs':len(sub),'queries':len(queries),'direct_checks':len(obs),'sources_overlap':sum(r['overlap']>0 for r in sub),
               'unchanged':sum(row[2]==r['zero'] for r in sub for row in r['tests']),'certified':sum(v[3] for v in obs),'plane_counts':{k:float(f([r['planes'] for r in sub])) for k,f in [('avg',np.mean),('median',np.median),('max',np.max)]},
               'timing':{}}
        for regime in ('fresh','repeat'):
            mat=np.zeros((len(queries),len(modes)));counts=np.zeros_like(mat)
            for p,g,rep,q,arm,n,ns in times:
                if (p,g)!=(panel,regime):continue
                i,j=queries.index(q),modes.index(arm);mat[i,j]+=ns;counts[i,j]+=n
            assert np.all(counts==counts[:,[0]])
            b=mat[draws].sum(axis=1);t=mat.sum(axis=0)
            ratios={}
            for a,c in [('direct','sqlite'),('hull','sqlite'),('sqlite','ram'),('sqlite','memo')]:
                i,j=modes.index(a),modes.index(c)
                ratios[a+'/'+c]=[t[i]/t[j],*np.quantile(b[:,i]/b[:,j],[.025,.975]).tolist()]
            stats['timing'][regime]={'requests':int(counts[:,0].sum()),'mean_us':dict(zip(modes,(t/counts.sum(axis=0)/1000).tolist())),'ratio_ci':ratios}
        groups[panel]=stats
    out={'panels':groups,'distinct_pairs':len(pairs),'distinct_checks':sum(len(r['tests']) for r in pairs),'rows':sum(r['planes'] for r in pairs),'unique_packets':log['packets'],'storage_bytes':log['bytes'],'build_s':log['build_ns']*1e-9}
    print(json.dumps(out))
    (ROOT/'results.json').write_text(json.dumps(out,indent=2)+'\n','utf8')
if __name__=='__main__':main()
