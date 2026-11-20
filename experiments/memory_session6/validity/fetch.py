"""Fetch only public version-control data. Do not check out or execute any project code."""
from pathlib import Path
import concurrent.futures,subprocess,json,hashlib,time
ROOT=Path(__file__).resolve().parent
REPOS='pallets/click pydantic/pydantic marshmallow-code/marshmallow agronholm/typeguard python-jsonschema/jsonschema python-attrs/attrs pallets/jinja tkrajina/gpxpy arrow-py/arrow mahmoud/boltons pyparsing/pyparsing mido/mido'.split()
def git(path,*args):
    return subprocess.check_output(['git','-c','core.autocrlf=false','-C',str(path),*args],stderr=subprocess.PIPE,timeout=170)
def fetch(repo,pin=None):
    p=ROOT/'mirrors'/repo.replace('/','__');p.parent.mkdir(parents=True,exist_ok=True)
    if not p.exists():subprocess.run(['git','clone','--bare','--depth=52','--single-branch','--no-tags','https://github.com/'+repo+'.git',str(p)],capture_output=True,timeout=230,check=True)
    if pin:
        try:git(p,'cat-file','-e',pin+'^{commit}')
        except subprocess.CalledProcessError:git(p,'fetch','--depth=52','origin',pin)
    commits=git(p,'rev-list','--first-parent','--max-count=43',pin or 'HEAD').decode().splitlines()[::-1]
    print(repo,len(commits),flush=True);return repo,{'head':commits[-1],'commits':commits,'url':'https://github.com/'+repo}
def main():
    dest=ROOT/'source_lock.json';prev=json.loads(dest.read_bytes()) if dest.exists() else {}
    with concurrent.futures.ThreadPoolExecutor(6) as pool:
        fs=[pool.submit(fetch,r,prev.get(r,{}).get('head')) for r in REPOS]
        out=dict(f.result() for f in fs)
    if prev:assert prev==out
    else:dest.write_text(json.dumps(out,indent=1))
if __name__=='__main__':main()
