"""Check only public source provenance and the installed runtime in the unmodified official OCI image."""
from pathlib import Path
from time import perf_counter
from hashlib import sha256
import json,subprocess,sys
D=Path(__file__).resolve().parent
IMAGE='swerebenchv2/pallets-click@sha256:0f0434c582fd1c89647777b4250bb3c579e2d42577a3ca4d251f556445f9b666'
SCRIPT="""from pathlib import Path
from hashlib import sha256
import subprocess,json,sys,importlib.metadata as md
p=Path.cwd()
names=subprocess.check_output(['git','ls-files','-z']).decode().strip('\\0').split('\\0')
records={n:[(p/n).stat().st_size,sha256((p/n).read_bytes()).hexdigest()] for n in names}
print(json.dumps(dict(commit=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),tree=subprocess.check_output(['git','rev-parse','HEAD^{tree}'],text=True).strip(),clean=not subprocess.check_output(['git','status','--porcelain','--untracked-files=no']),files=len(records),bytes=sum(v[0] for v in records.values()),content_sha256=sha256(json.dumps(records,sort_keys=True,separators=(',',':')).encode()).hexdigest(),python=sys.version.split()[0],pytest=md.version('pytest'))))
"""
def main():
    public=Path(sys.argv[1]);src=json.loads((public/'source.json').read_bytes())
    img=json.loads(subprocess.check_output(['docker','image','inspect',IMAGE]))[0]
    start=perf_counter()
    got=json.loads(subprocess.check_output(['docker','run','--network','none','--rm','-i','-w','/click',IMAGE,'python','-c',SCRIPT],timeout=90))
    elapsed=perf_counter()-start
    assert got['commit']==src['base'] and got['files']==src['files'] and got['content_sha256']==src['source_content_sha256'] and got['clean']
    info=dict(image=IMAGE,image_id=img['Id'],size_bytes=img['Size'],arch=img['Architecture'],os=img['Os'],layers=len(img['RootFS']['Layers']),source=src,image_provenance=got,unmodified_smoke=True,elapsed_seconds=round(elapsed,3))
    print(json.dumps(info))
    if len(sys.argv)>2:
        dest=Path(sys.argv[2])
        data=(json.dumps(info,sort_keys=True,indent=2)+'\n').encode()
        if not dest.exists():dest.write_bytes(data)
if __name__=='__main__':main()
