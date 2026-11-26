"""Verify every recorded source-update answer in the included SQLite projection."""
from hashlib import sha256
import json
from pathlib import Path
from sqlite3 import connect
import subprocess
import sys
from zipfile import ZipFile
D=Path(__file__).resolve().parent
sys.path.insert(0,str(D/"apps/trace"))
from observed import calculate
def main():
    digests=json.loads((D/"CONTENT_SHA256.json").read_bytes())
    ck=json.loads((D/"build-check.json").read_bytes())
    assert ck["pages"]==4 and ck["widths"]==[1040,390]
    assert sha256((D/"paper.pdf").read_bytes()).hexdigest()==ck["pdf_sha256"]
    assert sha256((D/"candidate.zip").read_bytes()).hexdigest()==ck["zip_sha256"]
    with ZipFile(D/"candidate.zip") as z:
        assert set(z.namelist())==set(digests)|{"CONTENT_SHA256.json"} and z.testzip() is None
        assert all(sha256(z.read(n)).hexdigest()==h==sha256((D/n).read_bytes()).hexdigest() for n,h in digests.items())
    with connect((D/"apps/trace/runtime/observed.sqlite").resolve().as_uri()+"?mode=ro",uri=True) as db:
        events={(q,s):(json.loads(n),json.loads(u)) for q,s,n,u in db.execute("SELECT q,step,nodes,updates FROM event")}
        assert len(events)==54
        n=0
        for q,step,cap,key,ids in db.execute("SELECT q,step,cap,subset,ids FROM chosen"):
            selected=[int(k) for k in key.split(",") if k]
            assert calculate(*events[q,step],cap,selected)==json.loads(ids)
            n+=1
        assert n==622
    video=json.loads((D/"browser-video.json").read_bytes())
    assert len(video["scenes"])==11 and "19 to 15" in video["scenes"][-1][1]
    assert video["seconds"]==169.76 and video["bytes"]==(D/"walkthrough.mp4").stat().st_size
    subprocess.run([sys.executable,"-B",str(D/"verify_candidate.py")],check=True)
    print("Recomputed 622 ordered packets from 54 observed groups and checked 11 recorded scenes.")
if __name__=="__main__":main()
