"""Capture the R52 SQLite console locally and append a narrated clip to the complete R51 video."""
import argparse
from contextlib import contextmanager
from hashlib import sha256
from http.server import ThreadingHTTPServer
import importlib.util
import json
import math
from pathlib import Path
import subprocess
import sys
from threading import Thread
from urllib.parse import urlsplit
import wave

from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parent
PREVIOUS=ROOT.parents[1]/"graph_memory_round51/submission"
DEMO=ROOT.parent/"maintenance/demo"
SPEECH=[
    "Both versions have arrived. Read as of version one. The journal and a fresh lookup agree on Dance Girl Dance.",
    "At version two, the observed mention selects Robert Dinesen. Both queries agree. Omitting this mention restores the earlier choice."
]
def hashfile(path):
    with path.open("rb") as f:return sha256(f.read()).hexdigest()
def run(cmd,work=None):
    return subprocess.run(cmd,cwd=work,check=True,capture_output=True).stdout
def probe(path):
    args=["ffprobe","-v","error","-show_entries","format=duration,size:stream=index,codec_type,codec_name,profile,level,width,height,pix_fmt,r_frame_rate,time_base,start_pts,start_time,duration,sample_rate,channels,channel_layout,nb_frames,extradata_hash","-show_data_hash","sha256","-of","json"]
    return json.loads(run([*args,str(path)]))
def packets(path,stream):
    return json.loads(run(["ffprobe","-v","error","-select_streams",stream,"-show_packets","-show_entries","packet=data_hash,pts_time,dts_time","-show_data_hash","sha256","-of","json",str(path)]))["packets"]
def packet_digest(rows):
    return sha256(b"".join(bytes.fromhex(r["data_hash"].split(":")[1]) for r in rows)).hexdigest()
@contextmanager
def demo():
    sys.path.insert(0,str(DEMO))
    spec=importlib.util.spec_from_file_location("r52_video_demo",DEMO/"serve.py")
    mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
    with ThreadingHTTPServer(("127.0.0.1",0),mod.Handler) as http:
        thread=Thread(target=http.serve_forever,daemon=True);thread.start()
        try:yield f"http://127.0.0.1:{http.server_port}/"
        finally:http.shutdown();thread.join(timeout=2)
def capture(work):
    changes=[];errors=[]
    with demo() as base,sync_playwright() as pw:
        exe=next(path for path in [Path("C:/Program Files/Google/Chrome/Application/chrome.exe"),Path("C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe")] if path.exists())
        with pw.chromium.launch(executable_path=str(exe),headless=True) as browser:
            page=browser.new_page(viewport=dict(width=1440,height=810),device_scale_factor=1)
            page.on("pageerror",lambda e:errors.append(str(e)))
            page.goto(base+"?case=change&received=2&asof=0&mention=1")
            for i,(version,visible,winner) in enumerate([(1,16,"Dance Girl Dance"),(2,32,"Robert Dinesen")]):
                page.locator("select[name=asof]").select_option(str(version))
                page.get_by_role("button",name="Replay in SQLite").click()
                page.wait_for_url(f"**asof={version}&mention=1")
                query=urlsplit(page.url).query
                data=page.request.get(base+"api?"+query).json()
                assert data["asof"]==version and data["received"]==2 and data["asof_words"]==min(visible,data["observed_words"])
                assert data["journal_title"]==data["eligible_title"]==winner and data["case"]=="change" and data["mention"]==1
                assert winner in page.locator("section").inner_text()
                # Preserve the selectors, evidence explanation and both SQL answers in each frame.
                assert page.locator("form").is_visible() and page.locator("section").bounding_box()["y"]<690
                page.screenshot(path=work/f"version-{version}.png",animations="disabled")
                changes.append(dict(query=query,asof=version,received=2,mention=1,asof_words=data["asof_words"],journal_winner=winner,
                    eligible_winner=data["eligible_title"],counterfactual_winner=data["toggled_title"],quote_target=data["target"],
                    mention_span=data["mention_span"],image_sha256=hashfile(work/f"version-{version}.png"),narration=SPEECH[i]))
            page.locator("select[name=mention]").select_option("0")
            page.get_by_role("button",name="Replay in SQLite").click();page.wait_for_url("**asof=2&mention=0")
            verified=page.request.get(base+"api?"+urlsplit(page.url).query).json()
            assert verified["journal_title"]==verified["eligible_title"]=="Dance Girl Dance" and not errors
            return changes,dict(asof=2,received=2,mention=0,journal_winner=verified["journal_title"],eligible_winner=verified["eligible_title"])
def voice(work):
    items=[dict(voice=str(work/f"voice-{i}.wav"),text=text) for i,text in enumerate(SPEECH,1)]
    (work/"speech.json").write_text(json.dumps(items),encoding="utf8")
    powershell="""param($Spec)
Add-Type -AssemblyName System.Speech
foreach ($item in (Get-Content -LiteralPath $Spec -Raw | ConvertFrom-Json)) {
    $v=[System.Speech.Synthesis.SpeechSynthesizer]::new()
    $voice=$v.GetInstalledVoices() | Where-Object { $_.Enabled -and $_.VoiceInfo.Culture.Name -eq 'en-US' } | Select-Object -First 1
    if ($null -eq $voice){throw 'English voice is required'}
    $v.SelectVoice($voice.VoiceInfo.Name)
    $v.Rate=1
    $v.SetOutputToWaveFile($item.voice)
    $v.Speak($item.text)
    $v.Dispose()
    Write-Output $voice.VoiceInfo.Name
}
"""
    (work/"speak.ps1").write_text(powershell,encoding="ascii")
    voices=run(["powershell","-NoProfile","-File",str(work/"speak.ps1"),str(work/"speech.json")]).decode().splitlines()
    lengths=[]
    with wave.open(str(work/"combined.wav"),"wb") as dest:
        for i in range(1,3):
            with wave.open(str(work/f"voice-{i}.wav"),"rb") as src:
                if i==1:dest.setparams(src.getparams())
                hz=src.getframerate();count=src.getnframes()
                assert hz==dest.getframerate()==22050 and src.getnchannels()==1 and src.getsampwidth()==2
                # Exact common 25-fps/AAC-input boundary, with a short pause after each utterance.
                frames=math.ceil((count/hz+.24)*25)
                dest.writeframes(src.readframes(count)+bytes((frames*(hz//25)-count)*2))
                lengths.append(frames/25)
    assert sum(lengths)<=20
    return lengths,voices
def media(work,dest,changes,toggled):
    prior=PREVIOUS/"walkthrough.mp4";meta=probe(prior)
    before=float(meta["format"]["duration"]);assert abs(before-276.88)<0.0001
    ff=["ffmpeg","-y","-loglevel","error"]
    lens,voices=voice(work)
    for i,length in enumerate(lens,1):
        run(ff+["-loop","1","-framerate","25","-i",f"version-{i}.png","-frames:v",str(round(length*25)),"-c:v","libx264","-threads","3","-preset","veryfast","-crf","20","-pix_fmt","yuv420p","-profile:v","high","-level","3.2","-video_track_timescale","12800",f"still-{i}.mp4"],work)
    (work/"stills.txt").write_text("file 'still-1.mp4'\nfile 'still-2.mp4'\n",encoding="ascii")
    run(ff+["-f","concat","-safe","0","-auto_convert","0","-i","stills.txt","-i","combined.wav","-map","0:v:0","-map","1:a:0","-c:v","copy","-ar","22050","-ac","1","-c:a","aac","-b:a","96k","extension.mp4"],work)
    ext=work/"extension.mp4";info=probe(ext)
    fields=(("codec_name","profile","level","width","height","pix_fmt","r_frame_rate","time_base","extradata_hash"),
            ("codec_name","profile","sample_rate","channels","channel_layout","time_base","extradata_hash"))
    for i,keys in enumerate(fields):
        for key in keys:assert meta["streams"][i][key]==info["streams"][i][key],(i,key,meta["streams"][i][key],info["streams"][i][key])
    (work/"clips.txt").write_text(f"file '{prior.as_posix()}'\nduration {before:.6f}\nfile 'extension.mp4'\n",encoding="ascii")
    assembled=work/"assembled.mp4"
    run(ff+["-copyts","-f","concat","-safe","0","-auto_convert","0","-i","clips.txt","-map","0:v","-map","0:a","-c","copy","-avoid_negative_ts","disabled","-movflags","+faststart",str(assembled)],work)
    out=probe(assembled);sec=float(out["format"]["duration"]);size=int(out["format"]["size"])
    assert before<sec<=300 and sec-before<=20.001 and size<50_000_000
    proofs={}
    for st,sel in (("video","v:0"),("audio","a:0")):
        old=packets(prior,sel);new=packets(assembled,sel);extension=packets(ext,sel)
        assert len(new)==len(old)+len(extension)
        assert [o["data_hash"] for o in old]==[o["data_hash"] for o in new[:len(old)]]
        assert [o["data_hash"] for o in extension]==[o["data_hash"] for o in new[len(old):]]
        shift=float(new[0]["pts_time"])-float(old[0]["pts_time"])
        for prev,now in zip(old,new):
            assert abs(float(now["pts_time"])-float(prev["pts_time"])-shift)<.00015
        assert abs(shift)<.05
        proofs[st]=dict(prior_packets=len(old),prefix_payload_sha256=packet_digest(old),extra_packets=len(extension),
            extension_payload_sha256=packet_digest(extension),prior_pts_shift_seconds=shift)
    run(["ffmpeg","-loglevel","error","-xerror","-i",str(assembled),"-map","0:v:0","-map","0:a:0","-f","null","-"])
    st=float(out["streams"][0]["start_time"])+before
    cursor=st
    for i,(length,c) in enumerate(zip(lens,changes)):
        c.update(start_seconds=round(cursor,5),duration_seconds=length,voice=voices[i]);cursor+=length
    dest.write_bytes(assembled.read_bytes())
    report=json.loads((PREVIOUS/"browser-video.json").read_text(encoding="utf8"))
    report.update(seconds=sec,bytes=size,source_video_sha256=hashfile(prior),video_sha256=hashfile(dest),
        extension_sha256=hashfile(ext),prior_seconds=before,extension_seconds=round(sum(lens),4),
        capture_controls=changes,suppression_verified=toggled,streams=out["streams"],source_preservation=proofs,
        decoded_full_file=True,live_source="experiments/graph_memory_round52/maintenance/demo/serve.py",
        server_source_sha256=hashfile(DEMO/"serve.py"),scenario_sha256=hashfile(DEMO/"cases.json"))
    report["scenes"].extend([["Read as of version one","Journal and eligible-index lookup return Dance Girl Dance."],["Read as of version two","The verified mention selects Robert Dinesen. Suppressing it restores the prior winner."]])
    dest.with_name("browser-video.json").write_text(json.dumps(report,indent=2)+"\n",encoding="utf8")
    print(json.dumps(dict(seconds=sec,bytes=size,added=lens,start=st,frames=proofs)))
if __name__=="__main__":
    cli=argparse.ArgumentParser(description=__doc__)
    cli.add_argument("work",type=Path);cli.add_argument("--output",type=Path,default=ROOT/"walkthrough.mp4")
    args=cli.parse_args();folder=args.work.resolve();folder.mkdir(exist_ok=True,parents=True)
    frames,omit=capture(folder);media(folder,args.output.resolve(),frames,omit)
