import concurrent.futures,json,urllib.request
from pathlib import Path
def tree(repo):
    api='https://api.github.com/repos/'+repo
    with urllib.request.urlopen(urllib.request.Request(api,headers={"User-Agent":"agent-memory-research"}),timeout=15) as f:info=json.load(f)
    branch=info['default_branch']
    with urllib.request.urlopen(urllib.request.Request(api+'/git/trees/'+branch+'?recursive=1',headers={"User-Agent":"agent-memory-research"}),timeout=20) as f:t=json.load(f)
    Path('tree_'+repo.replace('/','_')+'.json').write_text(json.dumps(t),encoding='utf8')
    hits=[(e['path'],e.get('size',0)) for e in t['tree'] if 'locomo' in e['path'].lower() and any(v in e['path'].lower() for v in ('.json','.csv','.parquet','.gz'))]
    print(repo,branch,t['sha'],len(hits),hits[:35],flush=True)
with concurrent.futures.ThreadPoolExecutor(4) as ex:list(ex.map(tree,['snap-research/locomo','thomasfevre/agent-memory-bench','campaign-layer/memory-core','tomdif/memoria']))
