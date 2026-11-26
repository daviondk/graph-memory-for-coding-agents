"""Build the standalone review package and its internal checksums deterministically."""
from hashlib import sha256
import json
from pathlib import Path
from zipfile import ZipFile, ZipInfo, ZIP_DEFLATED

D=Path(__file__).resolve().parent
DOCUMENTS=("README.md","paper.pdf","paper.tex","sources.bib","trace.png","edit.png","walkthrough.mp4",
           "demo.py","start.html","verify_candidate.py","app-inputs.json","browser-video.json")
def main():
    runtime=json.loads((D/"app-inputs.json").read_bytes())
    names=sorted(set(DOCUMENTS)|set(runtime))
    files={n:sha256((D/n).read_bytes()).hexdigest() for n in names}
    assert all(files[k]==v for k,v in runtime.items())
    name="CONTENT_SHA256.json"
    (D/name).write_text(json.dumps(files,sort_keys=True,indent=2)+"\n",encoding="utf8")
    with ZipFile(D/"candidate.zip","w") as z:
        for path in sorted([*names,name]):
            info=ZipInfo(path,(1980,1,1,0,0,0))
            info.compress_type=ZIP_DEFLATED
            info.external_attr=0o100644 << 16
            z.writestr(info,(D/path).read_bytes())
    with ZipFile(D/"candidate.zip") as z:
        assert z.testzip() is None
        assert all(sha256(z.read(p)).hexdigest()==v for p,v in files.items())
    print(len(names)+1,"members",sha256((D/"candidate.zip").read_bytes()).hexdigest())
if __name__=="__main__":
    main()
