import concurrent.futures,collections,subprocess
from extract import D,get,save
from objects import CACHE,ENV,git
def history(group):
    repo,rows=group;p=CACHE/"history"/(repo.replace("/","__")+".git");p.parent.mkdir(exist_ok=True)
    def run(*args):return subprocess.run(["git","-C",str(p),*args],capture_output=True,env=ENV,timeout=140)
    if not p.exists():
        subprocess.run(["git","init","--bare",str(p)],capture_output=True,check=True);assert run('remote','add','origin','https://github.com/'+repo+'.git').returncode==0
    ids=sorted({r[f] for r in rows for f in ('official','parent')})
    fetch=run('fetch','--no-tags','--depth=512','--filter=tree:0','origin',*ids)
    for row in rows:
        if fetch.returncode:row['relation']='unknown_fetch';continue
        q=run('merge-base','--is-ancestor',row['official'],row['parent'])
        row['relation']='earlier_ancestor' if q.returncode==0 else 'ancestry_unproven'
        row['ancestry_depth_limit']=512;row['ancestry_rc']=q.returncode
    return rows
if __name__=='__main__':
    m=get(D/'task_meta_panel.json');meta=get(D/'pr_metadata.json');objs={r['repo']:r for r in get(D/'objects.json')};rows=[];groups=collections.defaultdict(list)
    for pr in meta:
        c=objs[pr['repo']]['commits'][pr['merge']];old=m[pr['iid']]['base_commit'];p=c['parents'][0]
        x={**pr,**c,'official':old,'parent':p,'relation':'direct' if p==old else 'unknown'};rows.append(x)
        if c['old_time']>c['new_time']:x['relation']='inverted_time'
        elif p!=old:groups[pr['repo']].append(x)
    with concurrent.futures.ThreadPoolExecutor(4) as pool:
        for _ in pool.map(history,groups.items()):pass
    save('revision_pairs.json',rows)
    print(collections.Counter(v['relation'] for v in rows))
