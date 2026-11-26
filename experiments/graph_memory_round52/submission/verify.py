"""Verify the shipped bytes, run all live endpoints, and check the manuscript and video."""
from hashlib import sha256
import json
from pathlib import Path,PurePosixPath
import subprocess
import sys
from tempfile import TemporaryDirectory
from zipfile import ZipFile
from pypdf import PdfReader
import package

def main():
    root=package.D
    with TemporaryDirectory(dir=root.parent) as tmp:
        dest=Path(tmp)
        with ZipFile(root/"candidate.zip") as z:
            names=z.namelist();assert len(names)==len(set(names))==75 and z.testzip() is None
            assert all(not PurePosixPath(k).is_absolute() and ".." not in PurePosixPath(k).parts for k in names)
            expected=json.loads(z.read("CONTENT_SHA256.json"))
            assert expected=={k:sha256(z.read(k)).hexdigest() for k in names if k!="CONTENT_SHA256.json"}
            for k in package.DOCS:assert (root/k).read_bytes()==z.read(k)
            for k in package.HISTORY:assert (root.parent/"maintenance"/"demo"/k).read_bytes()==z.read("apps/history/"+k)
            for k in package.COMPACT:assert (root.parent/"address_history"/k).read_bytes()==z.read("apps/history/"+k)
            for k in package.DIRECTORY:assert (root.parent/"directory_demo"/k).read_bytes()==z.read("apps/directory/"+k)
            z.extractall(dest)
        checks={}
        for runner in ("verify_candidate.py","apps/history/test_console.py","apps/directory/test_console.py","apps/history/test_extension.py"):
            # The first entry validates all cross-app links from the landing page.
            result=subprocess.run([sys.executable,"-B","-X","utf8",runner],cwd=dest,capture_output=True,text=True,timeout=180)
            assert result.returncode==0,(runner,result.stdout,result.stderr)
            checks[runner]=result.stdout.strip()[-550:]
        pdf=PdfReader(dest/"paper.pdf");assert len(pdf.pages)==4
        full=" ".join(p.extract_text() for p in pdf.pages)
        assert all(int(p.mediabox.width)==612 and int(p.mediabox.height)==792 for p in pdf.pages)
        for marker in ("80,314","73,261","63.13","65.55","4,592","5,822","12,000","37.30","34.74","5,989,847","4,995","3,655","OpenAI Codex"):
            assert marker in full,marker
        meta=json.loads(subprocess.check_output(["ffprobe","-v","error","-count_frames","-show_entries","stream=codec_name,nb_read_frames:format=size,duration","-of","json",dest/"walkthrough.mp4"]))
        assert [s["codec_name"] for s in meta["streams"]]==["h264","aac"]
        assert all(int(s["nb_read_frames"])>0 for s in meta["streams"])
        video=json.loads((dest/"browser-video.json").read_bytes())
        assert float(meta["format"]["duration"])==video["seconds"]<=300
        assert int(meta["format"]["size"])==video["bytes"]<=50_000_000
        subprocess.run(["ffmpeg","-v","error","-xerror","-i",dest/"walkthrough.mp4","-f","null","-"],check=True)
        outcome=dict(files=len(names),sha256=package.digest((root/"candidate.zip").read_bytes()),pages=len(pdf.pages),
              seconds=video["seconds"],video_bytes=video["bytes"],scenes=len(video["scenes"]),checks=checks)
        (root/"verification.json").write_text(json.dumps(outcome,indent=2,sort_keys=True)+"\n",encoding="utf8")
        print(json.dumps(outcome,ensure_ascii=True,indent=2))
if __name__=="__main__":main()

