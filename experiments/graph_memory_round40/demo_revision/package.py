"""Seal manuscript files and package them with the separately signed portable runtime."""
from pathlib import Path
from hashlib import sha256
import json,sys,zipfile
D=Path(__file__).resolve().parent
FILES=('REPORT_RU.md','REPRODUCE_RU.md','paper.tex','sources.bib','paper.pdf','visitor.png','launcher.py','console.html','check_ui.py','ui-check.json','audit.py','evidence.json','validate_pdf.py','pdf-check.json','package.py','runtime-inputs.json','verify_release.py','record_video.py','walkthrough.mp4','video-check.json')
RUNTIME=('reader.py','reader.sqlite','grader.sqlite','DATA_SOURCE.md')
def digest(data):return sha256(data).hexdigest()
def json_bytes(obj):return (json.dumps(obj,indent=2,sort_keys=True)+'\n').encode()
def seal(path,raw):
    if path.exists():assert path.read_bytes()==raw,path
    else:
        with path.open('xb') as f:f.write(raw)
if __name__=='__main__':
    root=D/'runtime' if (D/'runtime').is_dir() else D.parent/'provenance_packet_demo'
    if root==D/'runtime':
        fixed=json.loads((D/'runtime-inputs.json').read_bytes());values=fixed['files']
    else:
        origin=(root/'manifest.json').read_bytes();official=json.loads(origin)['files'];values={n:official[n] for n in RUNTIME};fixed=dict(origin_manifest=digest(origin),files=values)
    assert all(digest((root/n).read_bytes())==values[n] for n in RUNTIME)
    seal(D/'runtime-inputs.json',json_bytes(fixed));items={n:(D/n).read_bytes() for n in FILES};manifest=json_bytes(dict(files={n:digest(v) for n,v in items.items()}));seal(D/'manifest.json',manifest);items['manifest.json']=manifest
    items.update({'runtime/'+n:(root/n).read_bytes() for n in RUNTIME})
    output=Path(sys.argv[1]) if len(sys.argv)>1 else D/'ICDE-demo-revision.zip'
    with zipfile.ZipFile(output,'x') as z:
        for n,data in sorted(items.items()):
            info=zipfile.ZipInfo(n,(1980,1,1,0,0,0));info.create_system=3;info.external_attr=0o100644<<16;z.writestr(info,data,compress_type=zipfile.ZIP_DEFLATED)
    with zipfile.ZipFile(output) as z:assert len(z.namelist())==len(items) and all(z.read(n)==v for n,v in items.items())
    print('archive',digest(output.read_bytes()),output.stat().st_size,'manifest',digest(manifest),len(FILES))
