"""Compare frozen prior-execution policies with author outputs on identical revision pairs and test files."""
import collections
import gzip
import json
from pathlib import Path
from audit import CACHE,ROOT,REV,save,sha

def load(name):
    b=(ROOT/name).read_bytes()
    return json.loads(gzip.decompress(b) if name.endswith('.gz') else b)
def main():
    for n,h in load('transfer-seal.json').items():assert sha((ROOT/n).read_bytes())==h
    paths={'gold':'ground truth/gt_loguru.json','NameRTS':'results/rq1/namerts/NameBDP_RTSTest_LOG.json',
           'EkstaP':'results/rq1/ekstap/EkstaP_RTSTest_LOG.json','BabelRTS':'results/rq1/babelrts/BabelRTS_loguru_clearn.json'}
    raw={k:(CACHE/'NameRTS'/n).read_bytes() for k,n in paths.items()}
    sources={k:{'path':n,'sha256':sha(raw[k]),'package':REV} for k,n in paths.items()}
    save('transfer-label-sources.json',sources)
    authors={k:{p['current']:p for p in json.loads(b) if p.get('target',True)} for k,b in raw.items()}
    r=load('transfer-predictions.json.gz')
    plan=load('transfer-plan.json'); files=set(plan['files'])
    results=[]
    for pair in plan['pairs']:
        c=pair['current'];old=pair['parent'];gold=authors['gold'][c]
        assert gold['true_parent']==old and gold['direct_parent']==pair['direct_parent']
        ref=set(gold['tests_to_run']);counts=gold['total_tests']; subset=files&ref
        selected={k:files&set(v[c]['tests_to_run']) for k,v in authors.items() if k!='gold'}
        rows=[x for x in r if x['current']==c];assert len(rows)==len(files)
        for method in ('module','function','line'):
            selected[method]={x['file'] for x in rows if x['select'][method]}
        selected['all']=files
        scores={k:{'chosen':sorted(tests),'hits':sorted(tests&subset),'misses':sorted(subset-tests),'n':len(tests),
                   'reduction':1-len(tests)/len(files),'safe_on_panel':not bool(subset-tests)} for k,tests in selected.items()}
        full={k:len(v[c]['tests_to_run']) for k,v in authors.items() if k!='gold'}
        for method in ('module','function','line'):
            full[method+'+rerun_unobserved']=counts-len(files)+len(selected[method])
        results.append({'current':c,'true_parent':old,'official_n':counts,'gold_full':len(ref),'panel_n':len(files),'gold_panel':sorted(subset),
                        'clean_runs':sum(row['clean'] for row in rows),'passing_nodeids':sum(row['pass_count'] for row in rows),
                        'selected':scores,'full_selection_counts':full,'warm_elapsed_seconds':sum(row['runtime']['seconds'] for row in rows)})
    agg={k:{'selected':sum(row['selected'][k]['n'] for row in results),'hits':sum(len(row['selected'][k]['hits']) for row in results),
            'misses':sum(len(row['selected'][k]['misses']) for row in results),'safe_pairs':sum(row['selected'][k]['safe_on_panel'] for row in results)} for k in results[0]['selected']}
    save('transfer-results.json',{'pairs':results,'total':agg})
    for r in results:print(r['current'][:8],r['official_n'],r['gold_full'],len(r['gold_panel']),r['clean_runs'],r['passing_nodeids'],{k:(s['n'],len(s['misses'])) for k,s in r['selected'].items()})
    print(agg)
if __name__=='__main__':main()
