"""Check all asset digests and run the original live HTTP/SQLite tests after isolated extraction."""
from hashlib import sha256
from pathlib import Path,PurePosixPath
from tempfile import TemporaryDirectory
from zipfile import ZipFile
import argparse,json,os,subprocess,sys
D=Path(__file__).resolve().parent
def h(b):return sha256(b).hexdigest()
def run(temp_base=None,render=False):
    manifest=D/"manifest.json"
    if manifest.is_file():
        assert all(h((D/n).read_bytes())==v for n,v in json.loads(manifest.read_bytes())["files"].items())
    with TemporaryDirectory(dir=temp_base) as folder:
        tmp=Path(folder)
        with ZipFile(D/"candidate.zip") as z:
            names=z.namelist()
            assert len(names)==len(set(names))==51 and z.testzip() is None
            assert all(not PurePosixPath(n).is_absolute() and ".." not in PurePosixPath(n).parts for n in names)
            hashes=json.loads(z.read("CONTENT_SHA256.json"))
            assert {n:h(z.read(n)) for n in names if n!="CONTENT_SHA256.json"}==hashes
            for n in ("paper.pdf","paper.tex","sources.bib","demo.py","start.html","verify_candidate.py","README.md"):assert z.read(n)==(D/n).read_bytes()
            z.extractall(tmp)
        output=subprocess.run([sys.executable,"-B",str(tmp/"verify_candidate.py")],cwd=tmp,capture_output=True,text=True,check=True,timeout=120)
        assert "all seven live SQLite consoles" in output.stdout
        if render:
            from pypdf import PdfReader
            pdf=PdfReader(str(tmp/"paper.pdf"));assert len(pdf.pages)==4
            pages=[page.extract_text() for page in pdf.pages];text=" ".join(pages)
            words=("Anonymous authors","83.07","81.19","83.00","82.94","82.98","25.7","130.8","1.77","1.16","50","Pisinger","Ganguly","108,204","960","901","697","649","42.70","41.62","1,280","42.58","0.49","1.71")
            assert all(w in text for w in words)
            manuscript=(tmp/"paper.tex").read_text(encoding="utf8")
            for claim in ("After pilot exclusion, 901 remained", "649 of 697", "refitting with typed degrees",
                          "Both timings start after embedding, graph construction and native ranking"):
                assert claim in manuscript
            assert all(int(pg.mediabox.width)==612 and int(pg.mediabox.height)==792 for pg in pdf.pages)
            streams=json.loads(subprocess.check_output(["ffprobe","-v","error","-count_frames","-show_entries","stream=codec_name,codec_type,nb_read_frames","-show_entries","format=duration,size","-of","json",str(tmp/"walkthrough.mp4")]))
            assert [s["codec_type"] for s in streams["streams"]]==["video","audio"]
            assert all(int(s["nb_read_frames"])>0 for s in streams["streams"])
            print(json.dumps({"pages":len(pages),"text_chars":[len(t) for t in pages],"video":streams},ensure_ascii=False))
        print(output.stdout.strip())
if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--temp-dir",type=Path);p.add_argument("--layout",action="store_true")
    a=p.parse_args();run(a.temp_dir,a.layout)

