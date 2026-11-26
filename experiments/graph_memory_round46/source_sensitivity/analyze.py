import gzip
import json
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parent
def main():
    data=json.loads(gzip.decompress((ROOT/'sources.json.gz').read_bytes()))
    rec=json.loads((ROOT/'run.json').read_bytes())
    grid=set(rec['grid'])
    effects={}
    def calc(label,group,filter_d):
        ids=sorted({r['tr'] for r in group})
        index={t:i for i,t in enumerate(ids)}
        mat=np.zeros((len(ids),4),dtype=int)
        for r in group:
            i=index[r['tr']]
            for d,same,sign,_,ns in r['samples']:
                if d in grid and filter_d(d):
                    mat[i]+=(1,same,sign,ns)
        rows=mat.sum(axis=0)
        macro=(mat[:,1]-mat[:,2])/mat[:,0]
        rng=np.random.default_rng(46071)
        boot=np.array([macro[rng.integers(len(ids),size=(100,len(ids)))].mean(axis=1) for i in range(100)])
        effects[label]=dict(sources=len(group),traces=len(ids),updates=int(rows[0]),same=int(rows[1]),sign_only=int(rows[2]),full_ms=float(rows[3])*1e-6,
            added_macro=float(macro.mean()),interval=np.quantile(boot,[.025,.975]).tolist())
    calc('all',data,lambda d:True)
    calc('multi',[r for r in data if r['m']>=2],lambda d:True)
    for d in sorted(grid):
        calc(str(d),data,lambda value:value==d)
    info={'groups':effects,'traces':len({r['tr'] for r in data}),'build_ms':sum(r['build_ns'] for r in data)*1e-6,'all_sources':len(data),'interval_bytes':(ROOT/'intervals.sqlite').stat().st_size,'finite_lower':sum(r['lo']!=-rec['inf'] for r in data),'finite_upper':sum(r['hi']!=rec['inf'] for r in data),'ties_at_bound':sum(r['tie_lo']+r['tie_hi'] for r in data),'no_optional_candidates':sum(r['m']==0 for r in data)}
    print(json.dumps(info))
    (ROOT/'results.json').write_text(json.dumps(info,indent=2)+'\n','utf8')
if __name__=='__main__':main()
