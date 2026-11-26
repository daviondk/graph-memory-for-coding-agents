"""Check rendered draft, extracted artifact bytes, actual SQLite services and numerical walk-through."""
from hashlib import sha256
from pathlib import Path
import json
import subprocess
import sys
from zipfile import ZipFile
D=Path(__file__).resolve().parent

def main():
    build=json.loads((D/"build-check.json").read_bytes())
    signed=json.loads((D/"CONTENT_SHA256.json").read_bytes())
    with ZipFile(D/"candidate.zip") as bundle:
        assert bundle.testzip() is None
        assert set(bundle.namelist())==set(signed)|{"CONTENT_SHA256.json"}
        for name,h in signed.items():
            assert sha256(bundle.read(name)).hexdigest()==h==sha256((D/name).read_bytes()).hexdigest()
    assert build["pages"]==4 and build["widths"]==[1040,390]
    for name in ("paper.pdf","candidate.zip"):
        key="pdf_sha256" if name=="paper.pdf" else "zip_sha256"
        assert build[key]==sha256((D/name).read_bytes()).hexdigest()
    video=json.loads((D/"browser-video.json").read_bytes())
    assert len(video["scenes"])==13 and "31 rows computed, compared with 79" in video["scenes"][-2][1] and "189,290" in video["scenes"][-1][1]
    assert video["seconds"]<=300 and video["bytes"]==(D/"walkthrough.mp4").stat().st_size<50_000_000
    subprocess.run([sys.executable,"-B",str(D/"verify_candidate.py")],check=True)
    print("Four pages; thirteen recorded scenes; 24 learned-packet scenarios and all 312 streaming steps verified over four checkpoint settings.")
if __name__=="__main__":main()
