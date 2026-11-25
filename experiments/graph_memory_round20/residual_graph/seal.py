"""Collect compact evidence, including code/stage errors and the released small native checkpoint."""
from pathlib import Path
from shutil import copyfile
import hashlib,json
ROOT=Path(__file__).resolve().parent
RUN=Path('D:/CodexResearch/x20-isetrace-residual')
TR=ROOT.parents[1]/'graph_memory_round19/trained_rank'
R18=ROOT.parents[1]/'graph_memory_round18/isetrace_official'
def sha(p):
    with p.open('rb') as fd:return hashlib.file_digest(fd,'sha256').hexdigest()
def read(p):return json.loads(p.read_bytes())
def main():
    assert (ROOT/'REPORT_RU.md').exists() and (ROOT/'topology/strata-results.json').exists() and (ROOT/'direct-embedding-audit.json').exists()
    assert sha(RUN/'best.pt')==read(ROOT/'checkpoint.json')['sha']
    assert sha(R18/'gold-spans.json.gz')==read(ROOT/'results.json')['gold_sha256']
    for p,dest in ((RUN/'best.pt',ROOT/'best.pt'),(R18/'gold-spans.json.gz',ROOT/'gold-spans.json.gz'),(TR/'split.json.gz',ROOT/'split.json.gz')):copyfile(p,dest)
    logs=ROOT/'logs';logs.mkdir(exist_ok=True)
    for p in (RUN/'logs').glob('*'):
        if p.is_file():copyfile(p,logs/p.name)
    topo=ROOT/'topology';sub={p.relative_to(topo).as_posix():sha(p) for p in sorted(topo.rglob('*')) if p.is_file() and '__pycache__' not in p.parts and p.name!='MANIFEST_SHA256.json'}
    (topo/'MANIFEST_SHA256.json').write_bytes((json.dumps(sub,sort_keys=True,indent=2)+'\n').encode())
    files={p.relative_to(ROOT).as_posix():sha(p) for p in sorted(ROOT.rglob('*')) if p.is_file() and p!=ROOT/'MANIFEST_SHA256.json' and '__pycache__' not in p.parts}
    p=ROOT/'MANIFEST_SHA256.json';p.write_bytes((json.dumps(files,sort_keys=True,indent=2)+'\n').encode())
    print('files',len(files),'sha256',sha(p))
if __name__=='__main__':main()

