"""Inventory public audit inputs required to reproduce the authors' downstream QA cohort."""
from pathlib import Path
import json,subprocess,requests,hashlib
D=Path(__file__).resolve().parent
UP=Path('D:/CodexResearch/x20-isetrace-runtime/upstream')
REQUIRED=['human_quality_pass_task_ids.json','human_corrected_query_metadata.jsonl','review_packet.jsonl']
def fetch(link):
    r=requests.get(link,headers={'User-Agent':'agent-memory-research-artifact-audit'},timeout=20)
    r.raise_for_status()
    return r.json()
def run():
    tracked=subprocess.check_output(['git','ls-files'],cwd=UP,text=True).splitlines()
    commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=UP,text=True).strip()
    runner=UP/'graph_memory/datasets/isetrace/end_to_end_qa/runner.py'
    assert all(n in runner.read_text('utf8') for n in REQUIRED)
    branch=fetch('https://api.github.com/repos/xiaoqi-7/GraphMemory');b=branch['default_branch']
    current=fetch(f'https://api.github.com/repos/xiaoqi-7/GraphMemory/commits/{b}')
    tree_id=current['commit']['tree']['sha']
    tree=fetch(f'https://api.github.com/repos/xiaoqi-7/GraphMemory/git/trees/{tree_id}?recursive=1')
    assert not tree['truncated']
    remote=[x['path'] for x in tree['tree'] if x['type']=='blob']
    releases=fetch('https://api.github.com/repos/xiaoqi-7/GraphMemory/releases?per_page=100')
    release_names=[a['name'] for r in releases for a in r['assets']]
    hf={}
    for slug in ('HazeLocus/ISETrace-Memory-Queries','valiere/ISETrace'):
        metadata=fetch('https://huggingface.co/api/datasets/'+slug)
        hf[slug]=dict(revision=metadata['sha'],files=[v['rfilename'] for v in metadata['siblings']])
    found={name:[p for p in tracked+remote+release_names+[p for d in hf.values() for p in d['files']] if p.split('/')[-1]==name] for name in REQUIRED}
    out=dict(runner=str(runner.relative_to(UP)).replace('\\','/'),runner_sha=hashlib.sha256(runner.read_bytes()).hexdigest(),checkout=commit,
             tracked_files=len(tracked),default_branch=b,remote_commit=current['sha'],remote_tree=tree_id,remote_files=len(remote),checked_github_releases=len(releases),assets=release_names,huggingface=hf,required=REQUIRED,matches=found)
    print('Git tracked files',len(tracked),'public tree',len(remote),'found',found)
    (D/'source-check.json').write_text(json.dumps(out,indent=2,sort_keys=True)+'\n','utf8')
if __name__=='__main__':run()
