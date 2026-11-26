"""Unpack and verify the complete R53 artifact independently of the research worktree."""
from pathlib import Path,PurePosixPath
from tempfile import TemporaryDirectory
from zipfile import ZipFile
import json
import subprocess
import sys
import package

def command(cmd,cwd):
    out=subprocess.run(cmd,cwd=cwd,capture_output=True,text=True,encoding="utf8",errors="replace",timeout=240)
    assert out.returncode==0,(cmd,out.stdout[-900:],out.stderr[-1200:])
    return out.stdout
def main():
    d=package.D;old=package.predecessor()
    with TemporaryDirectory(dir=d.parent) as td:
        dest=Path(td)
        with ZipFile(d/"candidate.zip") as z:
            ns=z.namelist();assert len(ns)==len(set(ns))==81 and z.testzip() is None
            assert all(not PurePosixPath(n).is_absolute() and ".." not in PurePosixPath(n).parts for n in ns)
            payload={n:z.read(n) for n in ns if n!="CONTENT_SHA256.json"}
            assert json.loads(z.read("CONTENT_SHA256.json"))=={n:package.digest(v) for n,v in payload.items()}
            assert all(payload[n]==(d/n).read_bytes() for n in package.DOCS)
            assert all(payload["apps/churn/"+n]==(d.parent/"churn"/n).read_bytes() for n in package.CHURN)
            for n in old:
                if n not in package.DOCS and n!="app-inputs.json":assert payload[n]==old[n],n
            z.extractall(dest)
        apps=["verify_candidate.py","apps/churn/demo/verify_http.py","apps/directory/test_console.py","apps/history/test_console.py","apps/history/test_extension.py"]
        checks={n:command([sys.executable,"-B","-X","utf8",n],dest).strip()[-500:] for n in apps}
        meta=command(["pdfinfo","paper.pdf"],dest);assert "4" == next(l.split(":",1)[1].strip() for l in meta.splitlines() if l.startswith("Pages:"))
        for i in range(1,5):
            dims=command(["pdfinfo","-f",str(i),"-l",str(i),"paper.pdf"],dest)
            assert "612 x 792 pts" in dims
        from pypdf import PdfReader
        pages=PdfReader(dest/"paper.pdf").pages;assert len(pages)==4
        txt="\f".join(p.extract_text() for p in pages)
        for marker in ("1,112","5,989,847","2.67","2.50","5.13","512","1.34","OpenAI Codex"):
            assert marker in txt,marker
        assert len(txt.rstrip().split("\f"))==4
        video=dest/"walkthrough.mp4";v=json.loads((dest/"browser-video.json").read_bytes())
        probe=json.loads(command(["ffprobe","-v","error","-show_entries","stream=codec_name:format=duration,size","-of","json",str(video)],dest))
        assert [s["codec_name"] for s in probe["streams"]]==["h264","aac"]
        assert v["seconds"]==float(probe["format"]["duration"])==292.92
        assert v["bytes"]==int(probe["format"]["size"])==5403129 and v["video_sha256"]==package.digest(video.read_bytes())
        assert (d/"walkthrough.mp4").read_bytes()==video.read_bytes() and (d/"browser-video.json").read_bytes()==(dest/"browser-video.json").read_bytes()
        command(["ffmpeg","-loglevel","error","-xerror","-i",str(video),"-map","0:v","-map","0:a","-f","null","-"],dest)
        r=dict(files=len(ns),sha256=package.digest((d/"candidate.zip").read_bytes()),zip_bytes=(d/"candidate.zip").stat().st_size,
               previous_archive=package.PIN,video_sha256=v["video_sha256"],seconds=v["seconds"],video_bytes=v["bytes"],
               pages=4,paper_sha256=package.digest((d/"paper.pdf").read_bytes()),output_pdf="Letter 612 x 792 pt, each page",checks=checks)
        (d/"verification.json").write_text(json.dumps(r,indent=2,sort_keys=True)+"\n",encoding="utf8")
        print(json.dumps(r,ensure_ascii=True,indent=2))
if __name__=="__main__":main()
