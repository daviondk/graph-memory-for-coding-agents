"""Verify the actual ZIP, local SQLite processes, four-page PDF, and decoded media."""
import argparse
from hashlib import sha256
import json
from pathlib import Path, PurePosixPath
import subprocess
import sys
from tempfile import TemporaryDirectory
from zipfile import ZipFile
from pypdf import PdfReader
import package

ROOT=Path(__file__).resolve().parent

def main(scratch=None):
    with TemporaryDirectory(dir=scratch or ROOT.parent) as directory:
        dst=Path(directory)
        with ZipFile(ROOT/"candidate.zip") as z:
            names=z.namelist()
            assert len(names)==len(set(names))==60 and z.testzip() is None
            assert all(not PurePosixPath(n).is_absolute() and ".." not in PurePosixPath(n).parts for n in names)
            receipt=json.loads(z.read("CONTENT_SHA256.json"))
            assert {n:sha256(z.read(n)).hexdigest() for n in names if n!="CONTENT_SHA256.json"}==receipt
            for n in package.OVERRIDE:
                assert (ROOT/n).read_bytes()==z.read(n)
            for n in package.RUNTIME:
                assert (ROOT.parent/"policy_replay"/n).read_bytes()==z.read("apps/policies/"+n)
            z.extractall(dst)
        result=subprocess.run([sys.executable,"-B","-X","utf8","verify_candidate.py"],cwd=dst,capture_output=True,text=True,timeout=120)
        if result.returncode:
            raise RuntimeError(result.stdout+result.stderr)
        assert "all eight live SQLite consoles" in result.stdout
        pdf=PdfReader(dst/"paper.pdf")
        full=" ".join(pg.extract_text() for pg in pdf.pages)
        assert len(pdf.pages)==4 and all(int(pg.mediabox.width)==612 and int(pg.mediabox.height)==792 for pg in pdf.pages)
        for marker in ("55.72","57.62","3.18","1.86","0.70","1,335","81.19","83.07","HotpotQA","OpenAI Codex"):
            assert marker in full,marker
        video=json.loads(subprocess.check_output(["ffprobe","-v","error","-count_frames","-show_entries","stream=codec_name,codec_type,nb_read_frames:format=duration,size","-of","json",str(dst/"walkthrough.mp4")]))
        assert [s["codec_name"] for s in video["streams"]]==["h264","aac"]
        assert all(int(s["nb_read_frames"])>0 for s in video["streams"])
        assert float(video["format"]["duration"])<=300 and int(video["format"]["size"])<=50_000_000
        clip=json.loads((dst/"browser-video.json").read_bytes())
        assert clip["seconds"]==float(video["format"]["duration"]) and clip["bytes"]==int(video["format"]["size"]) and len(clip["scenes"])==17
        print(result.stdout.strip())
        print(f"Verified {len(pdf.pages)} pages, {clip['seconds']:.2f} s of H.264/AAC, {len(names)} archive members, and data attributions.")

if __name__=="__main__":
    arg=argparse.ArgumentParser(description=__doc__);arg.add_argument("--scratch",type=Path)
    main(arg.parse_args().scratch)

