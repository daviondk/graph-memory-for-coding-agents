"""Fetch exact public artifact objects. Archive content is parsed in memory only."""
import hashlib,json,tarfile,io
from pathlib import Path
import requests
ROOT=Path(__file__).resolve().parent
REPO='JetBrains-Research/the-complexity-trap'
REV='bf15b5fb7d279679035a007ac9a81084d6b9a89a'
FILES=['auxiliary-data/experiment_instance_costs_sweagent.csv','auxiliary-data/bootstrapped_cis.csv','auxiliary-data/paired_ci_diffs_vs_raw.csv','auxiliary-data/eval_results-swe_agent.tar','sweagent/agent/history_processors.py','config/default_no_demo_N=1_M=10.yaml','LICENSE']
def main():
    asset=ROOT/'sources';asset.mkdir(exist_ok=True)
    tree=requests.get(f'https://api.github.com/repos/{REPO}/git/trees/{REV}',params={'recursive':1},timeout=30).json()['tree']
    index={x['path']:x for x in tree if x['type']=='blob'}
    received=[]
    for file in FILES:
        url=f'https://raw.githubusercontent.com/{REPO}/{REV}/{file}'
        res=requests.get(url,timeout=60);res.raise_for_status();b=res.content
        assert hashlib.sha1(b'blob '+str(len(b)).encode()+b'\0'+b).hexdigest()==index[file]['sha']
        (asset/Path(file).name).write_bytes(b)
        received.append({'path':file,'url':url,'sha256':hashlib.sha256(b).hexdigest(),'git_blob':index[file]['sha'],'size':len(b)})
    (ROOT/'receipts.json').write_text(json.dumps(received,indent=2),encoding='utf8')
if __name__=='__main__':main()
