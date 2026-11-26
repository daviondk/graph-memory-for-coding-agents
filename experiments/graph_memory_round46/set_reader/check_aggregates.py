"""Verify points from compact outcomes and reproduce the primary paired cluster interval."""
from pathlib import Path
from collections import Counter,defaultdict
from math import isclose
import gzip,hashlib,json,sys
import numpy as np

D=Path(__file__).resolve().parent
def get(path):
    raw=path.read_bytes()
    return json.loads(gzip.decompress(raw) if path.suffix=='.gz' else raw)
def main():
    if '--export' in sys.argv:
        p=D.parents[1]/'graph_memory_round45/qwen_panel214';old=get(p/'panel.json')
        assert hashlib.sha256((p/'panel.json').read_bytes()).hexdigest()==get(p/'manifest.json')['files']['panel.json']
        panel={k:old[k] for k in ('order','remaining','pilot')}
        (D/'panels.json').write_text(json.dumps(panel,sort_keys=True,indent=1)+'\n',encoding='utf8')
    splits=get(D/'panels.json');o=get(D/'outcomes.json.gz');summary=get(D/'results.json')['panels']
    assert len(set(splits['remaining'])&set(splits['pilot']))==0 and set(splits['remaining']+splits['pilot'])==set(o)
    groups={'outside204':splits['remaining'],'all214':splits['order'],'pilot10':splits['pilot'],'neural12':get(D/'small-panel.json')}
    groups.update({k:[q for q in splits['remaining'] if bool(o[q]['seen'])==yes] for k,yes in [('outside204_seen',True),('outside204_unseen',False)]})
    checks=0
    for group,qs in groups.items():
        p=summary[group];repo_count=Counter(o[q]['repo'] for q in qs)
        assert p['states']==len(qs) and p['repos']==len(repo_count)
        for name,data in p['arms'].items():
            for i in range(9):
                vals=[o[q]['arms'][name]['metric'][i] for q in qs]
                sum_repos=sum(x/repo_count[o[q]['repo']] for q,x in zip(qs,vals))
                for key,v in [('mean',sum(vals)/len(qs)),('sum',sum(vals)),('macro',sum_repos/len(repo_count))]:
                    assert isclose(data[key][i],v,abs_tol=1e-10)
                    checks+=1
            for key in ('tokens','items'):
                for i in range(6):
                    measured=sum(o[q]['arms'][name][key][i] for q in qs)/len(qs)
                    assert isclose(measured,data[key][i],abs_tol=1e-10)
                    checks+=1
        for label,stats in p['paired'].items():
            a,b=label.split(' minus ')
            for i,d in enumerate(stats['micro']):
                diff=[o[q]['arms'][a]['metric'][i]-o[q]['arms'][b]['metric'][i] for q in qs]
                assert isclose(d,sum(diff)/len(qs),abs_tol=1e-12)
                assert stats['wins'][i]==sum(v>1e-10 for v in diff) and stats['loss'][i]==sum(v< -1e-10 for v in diff)
                checks+=3
    qs=groups['outside204'];blocks=defaultdict(list)
    for q in qs:
        obs=o[q];a=obs['arms'];blocks[obs['repo']].append(a['dpp']['metric'][0]-a['qwen']['metric'][0])
    keys=sorted(blocks);n=len(keys);rng=np.random.default_rng(4621406)
    prob=np.repeat(1./n,n);sums=np.array([sum(blocks[k]) for k in keys]);lengths=np.array([len(blocks[k]) for k in keys])
    # Iterate scalar ratios for each bootstrap sample; original analysis forms a two-dimensional matrix product.
    micro=[];macro=[]
    for counts in rng.multinomial(n,prob,size=20000):
        micro.append(np.dot(counts,sums)/np.dot(counts,lengths));macro.append(np.dot(counts,sums/lengths)/n)
    target=summary['outside204']['paired']['dpp minus qwen']
    for name,draws in [('ci',micro),('macro_ci',macro)]:
        assert np.allclose(np.percentile(draws,[2.5,97.5]),[z[0] for z in target[name]],atol=1e-14)
    print(f'Confirmed {checks} arm/paired statistics over six panels and both primary intervals with 20,000 repository draws.')
if __name__=='__main__':main()

