"""Read public author labels and identify changed import-time function from pinned Git blobs."""
import ast
import collections
import concurrent.futures
import gzip
import hashlib
import json
from pathlib import Path
from statistics import mean
import urllib.parse
import urllib.request
import time

ROOT=Path(__file__).resolve().parent
CACHE=Path('D:/CodexResearch/x20-r17-namerts')
REV='f1acdae0f2b2d1ed6e3e2956d510db49bb7c276f'
PKG='https://raw.githubusercontent.com/ZJU-CTAG/NameRTS/'+REV+'/'
UP='https://raw.githubusercontent.com/matplotlib/matplotlib/'
PATH='lib/matplotlib/__init__.py'
SOURCE={'tasks':'dataset/commit_pairs_matplotlib.json','gold':'ground truth/gt_matplotlib.json',
        'NameRTS':'results/rq1/namerts/NameBDP_RTSTest_MA.json','EkstaP':'results/rq1/ekstap/EkstaP_RTSTest_MA.json',
        'BabelRTS':'results/rq1/babelrts/BabelRTS_matplotlib_clearn.json'}
def sha(b):return hashlib.sha256(b).hexdigest()
def save(name,x):
    b=json.dumps(x,ensure_ascii=False,separators=(',',':'),sort_keys=True).encode()
    (ROOT/name).write_bytes(gzip.compress(b,mtime=0) if name.endswith('.gz') else b)
def fetch(url,dest):
    if dest.exists():return dest.read_bytes()
    for i in range(3):
        try:
            with urllib.request.urlopen(url,timeout=30) as r:data=r.read()
            dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(data);return data
        except OSError:
            if i==2:raise
            time.sleep(i+1)
def capture(commit):
    url=UP+commit+'/'+PATH
    raw=fetch(url,CACHE/'mpl-init'/commit)
    mod=ast.parse(raw)
    matches=[x for x in mod.body if isinstance(x,ast.FunctionDef) and x.name=='_get_executable_info']
    assert len(matches)==1
    func=matches[0]
    return {"url":url,"blob_sha":sha(raw),"ast_sha":sha(ast.dump(func,include_attributes=False).encode()),"start":func.lineno,"end":func.end_lineno}
def main():
    CACHE.mkdir(exist_ok=True)
    records={};source={}
    for k,p in SOURCE.items():
        url=PKG+urllib.parse.quote(p)
        b=fetch(url,CACHE/Path(p).name)
        records[k]=json.loads(b)
        source[k]={'url':url,'sha256':sha(b),'records':len(records[k])}
    truth={r['current']:r for r in records['gold'] if r['target']}
    pred={k:{r['current']:r for r in records[k]} for k in ('NameRTS','EkstaP','BabelRTS')}
    assert len(truth)==50 and all(set(rows)==set(truth) for rows in pred.values())
    commits=sorted({r[k] for r in truth.values() for k in ('true_parent','direct_parent','current')})
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as pool:
        versions=dict(zip(commits,pool.map(capture,commits)))
    pairs=[]
    for current,r in truth.items():
        gs=set(r['tests_to_run']);total=r['total_tests'];assert len(gs)<=total
        changed={k:versions[r[k]]['ast_sha']!=versions[current]['ast_sha'] for k in ('true_parent','direct_parent')}
        methods={}
        for approach,table in pred.items():
            est=table[current]
            assert all(est[k]==r[k] for k in ('current','true_parent','direct_parent'))
            chosen=set(est['tests_to_run'])
            methods[approach]={'selected':len(chosen),'hit':len(gs&chosen),'miss':sorted(gs-chosen),'extra':len(chosen-gs),'full_size_match':len(chosen)==total,'selected_files':sorted(chosen)}
        pairs.append({'current':current,'true_parent':r['true_parent'],'direct_parent':r['direct_parent'],'changed':changed,
                     'total_test_files':total,'ground_truth':sorted(gs),'methods':methods})
    save('sources.json',source);save('versions.json.gz',versions);save('pairs.json.gz',pairs)
    subsets={'all':pairs,**{k:[x for x in pairs if x['changed'][k]] for k in ('true_parent','direct_parent')}}
    result={}
    for k,rows in subsets.items():
        result[k]={'n':len(rows),'ids':[x['current'] for x in rows],'methods':{}}
        for a in pred:
            stats=[x['methods'][a] for x in rows]
            result[k]['methods'][a]={'total_tests':sum(x['total_test_files'] for x in rows),'total_gold':sum(len(x['ground_truth']) for x in rows),
                                    'total_selected':sum(x['selected'] for x in stats),'total_miss':sum(len(x['miss']) for x in stats),
                                    'full_count':sum(x['full_size_match'] for x in stats),'safe_pairs':sum(not x['miss'] for x in stats),
                                    'avg_reduction':mean(1-s['selected']/x['total_test_files'] for s,x in zip(stats,rows))}
    save('results.json',result)
    print('versions',len(versions),'counts',[(k,v['n']) for k,v in result.items()])
    for x in subsets['true_parent']:print(x['current'],x['total_test_files'],len(x['ground_truth']),{a:(s['selected'],s['hit']) for a,s in x['methods'].items()})
if __name__=='__main__':main()
