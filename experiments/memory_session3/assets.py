"""Capture the two original simulation releases and small source snapshots, stored on drive D."""
from pathlib import Path
import hashlib,json,shutil,subprocess
ROOT=Path(__file__).resolve().parent;BASE=ROOT.parents[2];dest=ROOT/'upstream'
def main():
    dest.mkdir(exist_ok=True)
    downloads={'json_2.1.3_tw-pddl.zip':('x20-session3-alfworld.zip','https://github.com/alfworld/alfworld/releases/download/0.4.2/json_2.1.3_tw-pddl.zip'),
        'json_2.1.1_json.zip':('x20-session3-alfmeta.zip','https://github.com/alfworld/alfworld/releases/download/0.2.2/json_2.1.1_json.zip')}
    sources={}
    for dst,(name,url) in downloads.items():
        shutil.copy2(BASE/name,dest/dst);sources[dst]={'url':url}
    for repo,slug,rev,files in [('x20-session3-quixbugs','jkoppel/QuixBugs','4257f44b0ff1181dedaedee6a447e133219fcebf',[]),
        ('x20-session3-alfworld','alfworld/alfworld','aaba6870f86c5be6a08a491f32a50b906227bc3e',['README.md','LICENSE','requirements.txt','alfworld/agents/environment/alfred_tw_env.py','alfworld/agents/utils/misc.py','alfworld/gen/goal_library.py','scripts/alfworld-download','configs/base_config.yaml'])]:
        assert subprocess.check_output(['git','-C',str(BASE/repo),'rev-parse','HEAD']).decode().strip()==rev
        name=repo.split('-')[-1]+'-source.zip'
        subprocess.run(['git','-C',str(BASE/repo),'archive','--format=zip','-o',str(dest/name),rev,*files],check=True)
        sources[name]={'url':'https://github.com/'+slug+'/tree/'+rev,'paths':files or 'full repository'}
    wheels=dest/'wheels';wheels.mkdir(exist_ok=True)
    for manifest in ('validity/sources.json','validity/external_validation/sources.json'):
        for item in json.loads((ROOT/manifest).read_bytes()):
            if item.get('skip'):continue
            name=item['filename'];key='wheels/'+name
            src=BASE/'x20-validity-releases'/'wheels'/name
            assert hashlib.sha256(src.read_bytes()).hexdigest()==item['sha256'];shutil.copy2(src,wheels/name)
            sources[key]={'url':item['url']}
    for name,r in sources.items():
        path=dest/name;r['sha256']=hashlib.sha256(path.read_bytes()).hexdigest();r['bytes']=path.stat().st_size
    (dest/'sources.json').write_text(json.dumps(sources,indent=1))
    print(len(sources),'upstream artifacts')
if __name__=='__main__':main()
