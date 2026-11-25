"""Download only frozen PROV JSON as inert data, verifying the Git blob and SHA-256."""
import concurrent.futures
import fnmatch
import hashlib
import json
import os
import subprocess
from pathlib import Path
import urllib.parse
import urllib.request

D=Path(__file__).resolve().parent
C=Path(os.environ.get('OBSERVED_FLOW_CACHE','D:/CodexResearch/x20-observed-r-flow'))
C.mkdir(parents=True,exist_ok=True)
SOURCES={
    'RDataTracker':('d4c096cbce24d7e4822e90305ee0917b52b3d172','scriptTests/*/rdt/expected_prov.json'),
    'rdtLite':('7366631621c824b6040ad144e8d8bac4f6e3804b','scriptTests/*/rdtLite/expected_prov.json'),
    'eep-usecases':('a6ef670ce838694c51a308edec7cff1ac04016e9','*ddg/ddg.json'),
    'provExplainR':('9bf40f181e24bda0ad303e467aa938efcdf62436','inst/testdata/*/prov.json'),
    'provTranslateNow':('cf35740f2810833dda4e3ce92f16cae07e3562f8','tests/*/now.json'),
}
def sha(b):return hashlib.sha256(b).hexdigest()
def dump(p,z):p.write_bytes((json.dumps(z,sort_keys=True,separators=(',',':'),ensure_ascii=False)+'\n').encode())
def read(p):return json.loads(p.read_bytes())
def fetch(url): 
    return subprocess.check_output(['curl.exe','-fsSL','--retry','3','--max-time','90',url])
def main():
    files=[]
    for repo,(rev,pattern) in SOURCES.items():
        tree=json.loads(fetch(f'https://api.github.com/repos/End-to-end-provenance/{repo}/git/trees/{rev}?recursive=1'))
        assert tree['sha']==rev and not tree['truncated']
        for row in tree['tree']:
            if row['type']=='blob' and fnmatch.fnmatchcase(row['path'],pattern):
                files.append(dict(repo=repo,rev=rev,path=row['path'],git_blob=row['sha'],bytes=row['size']))
    def one(r):
        p=C/(r['git_blob']+'.json')
        url='https://raw.githubusercontent.com/End-to-end-provenance/'+r['repo']+'/'+r['rev']+'/'+urllib.parse.quote(r['path'])
        if not p.exists():p.write_bytes(fetch(url))
        data=p.read_bytes()
        assert hashlib.sha1(b'blob '+str(len(data)).encode()+bytes([0])+data).hexdigest()==r['git_blob']
        return dict(r,sha256=sha(data))
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        entries=list(pool.map(one,files))
    dump(D/'source-lock.json',entries)
    from collections import Counter
    print('files',Counter(r['repo'] for r in entries),sum(r['bytes'] for r in entries))
if __name__=='__main__':main()

