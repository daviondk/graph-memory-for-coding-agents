"""Capture the two new live consoles and append their narrated segment to the prior walkthrough."""
import argparse
from hashlib import sha256
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
from threading import Thread
from contextlib import ExitStack
from http.server import ThreadingHTTPServer
import wave
import zipfile
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parent
R50=ROOT.parents[1]/"graph_memory_round50"
SPEECH=[
    "Each question permits a second read. Here the fixed mention bonus changes the selected document. The recorded answer loses accuracy. Compare both inputs before revealing the reference.",
    "Now compare the policies across twelve hundred and eighty questions. Only fifty five prompts change. The paired score difference requires one hundred and ten reader calls from an empty cache. All other questions contribute zero.",
    "Change the panel to Hotpot Q A, and compare the fixed bonus to always following the strongest visible mention. The answer score improves again. Each change remains traceable to its two actual inputs.",
    "Finally, compare two learned ranking rules in SQLite. The first includes a visible mention, while the second learns from lexical and dense scores alone. Suppress a mention to rerank the titles and inspect the recorded answer."
]

def module(path,name):
    spec=importlib.util.spec_from_file_location(name,path)
    obj=importlib.util.module_from_spec(spec);spec.loader.exec_module(obj)
    return obj

def capture(work):
    sys.path.insert(0,str(ROOT.parent/"policy_replay"))
    modules=[module(R50/"address_demo/address_server.py","addressdemo"),
             module(ROOT.parent/"policy_replay/server.py","policydemo")]
    with ExitStack() as stack:
        urls=[]
        for mod in modules:
            server=stack.enter_context(ThreadingHTTPServer(("127.0.0.1",0),mod.Handler))
            thread=Thread(target=server.serve_forever,daemon=True);thread.start()
            stack.callback(thread.join,4);stack.callback(server.shutdown)
            urls.append(f"http://127.0.0.1:{server.server_port}/")
        with sync_playwright() as pw:
            exe=next(p for p in [Path("C:/Program Files/Google/Chrome/Application/chrome.exe"),
                                 Path("C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe")] if p.exists())
            b=pw.chromium.launch(executable_path=str(exe),headless=True)
            tab=b.new_page(viewport={"width":1440,"height":810})
            errors=[];tab.on("pageerror",lambda e:errors.append(str(e)))
            tab.goto(urls[0]);tab.wait_for_selector("tr.pick")
            tab.locator("#filter").select_option("loss")
            tab.wait_for_function("current && current.selected_answer.f1 < current.baseline_answer.f1")
            tab.locator("#reveal").click()
            tab.locator("#gold").scroll_into_view_if_needed()
            tab.screenshot(path=work/"scene0.png")
            tab.goto(urls[1]);tab.wait_for_function("document.querySelector('#calls').textContent==='110'")
            tab.screenshot(path=work/"scene1.png")
            tab.locator("#panel").select_option("transfer")
            tab.locator("#start").select_option("registered");tab.locator("#end").select_option("always")
            tab.wait_for_function("document.querySelector('#diff').textContent==='+1.44 pp' || document.querySelector('#diff').textContent==='+1.45 pp'")
            tab.screenshot(path=work/"scene2.png")
            tab.goto(urls[1]+"rank");tab.wait_for_selector("tr.chosen")
            tab.locator("#panel").select_option("hotpot")
            tab.wait_for_function("document.querySelector('#summary').textContent.includes('60.89')")
            tab.locator("#case").select_option("5a7dc6945542990b8f503a8d")
            tab.wait_for_function("document.querySelector('#suppress option[value=\"7\"]') !== null")
            tab.locator("#suppress").select_option("7")
            tab.wait_for_function("document.querySelector('#cert').textContent.includes('verified')")
            tab.screenshot(path=work/"scene3.png")
            tab.locator("#method").select_option("hybrid")
            tab.wait_for_selector("tr.chosen")
            tab.goto(urls[1]);tab.wait_for_function("document.querySelector('#calls').textContent==='110'")
            tab.locator("#start").select_option("registered")
            # Check reverse and equal thresholds, the error state and usability on a narrow viewport.
            tab.set_viewport_size({"width":390,"height":844})
            tab.locator("#end").select_option("registered");tab.wait_for_function("document.querySelector('#calls').textContent==='0'")
            tab.locator("#end").select_option("custom");tab.locator("#enum").fill("-2");tab.locator("#enum").press("Tab")
            tab.wait_for_function("document.querySelector('#output').hidden")
            tab.locator("#enum").fill("0.1");tab.locator("#enum").press("Tab");tab.wait_for_function("!document.querySelector('#output').hidden")
            assert tab.evaluate("document.documentElement.scrollWidth<=innerWidth")
            tab.locator("#filter").select_option("loss");tab.screenshot(path=work/"mobile.png")
            assert not errors
            b.close()

def media(work,dest):
    with zipfile.ZipFile(R50/"submission/candidate.zip") as pack:
        (work/"prior.mp4").write_bytes(pack.read("walkthrough.mp4"))
    words=[dict(voice=str(work/f"voice{i}.wav"),text=t) for i,t in enumerate(SPEECH)]
    (work/"speech.json").write_text(json.dumps(words),encoding="utf8")
    ps="""param($Spec)
Add-Type -AssemblyName System.Speech
foreach($item in (Get-Content -LiteralPath $Spec -Raw | ConvertFrom-Json)) {
    $v = [System.Speech.Synthesis.SpeechSynthesizer]::new()
    $name = $v.GetInstalledVoices() | Where-Object { $_.Enabled -and $_.VoiceInfo.Culture.Name -eq 'en-US' } | Select-Object -First 1
    if ($null -ne $name) { $v.SelectVoice($name.VoiceInfo.Name) }
    $v.Rate=0
    $v.SetOutputToWaveFile($item.voice)
    $v.Speak($item.text)
    $v.Dispose()
}
"""
    (work/"narrate.ps1").write_text(ps,encoding="utf8")
    subprocess.run(["powershell","-NoProfile","-File",str(work/"narrate.ps1"),str(work/"speech.json")],check=True)
    durations=[]
    with wave.open(str(work/"audio.wav"),"wb") as output:
        for i in range(len(SPEECH)):
            with wave.open(str(work/f"voice{i}.wav"),"rb") as wav:
                if i==0:output.setparams(wav.getparams())
                assert wav.getframerate()==output.getframerate() and wav.getnchannels()==output.getnchannels()
                silence=wav.getframerate()//2
                output.writeframes(wav.readframes(wav.getnframes())+b"\0"*(silence*wav.getsampwidth()*wav.getnchannels()))
                durations.append((wav.getnframes()+silence)/wav.getframerate())
    (work/"frames.txt").write_text("".join(f"file 'scene{i}.png'\nduration {t:.6f}\n" for i,t in enumerate(durations))+f"file 'scene{len(durations)-1}.png'\n",encoding="ascii")
    cmd=["ffmpeg","-y","-loglevel","error"]
    subprocess.run(cmd+["-f","concat","-safe","0","-i","frames.txt","-i","audio.wav","-r","25","-c:v","libx264","-tune","stillimage","-crf","20","-pix_fmt","yuv420p","-ar","22050","-ac","1","-c:a","aac","-b:a","96k","-shortest","extension.mp4"],cwd=work,check=True)
    # Decode at the join to keep audio timestamps aligned across the two AAC streams.
    subprocess.run(cmd+["-i","prior.mp4","-i","extension.mp4","-filter_complex","[0:v:0][0:a:0][1:v:0][1:a:0]concat=n=2:v=1:a=1[v][a]","-map","[v]","-map","[a]","-c:v","libx264","-threads","3","-preset","veryfast","-crf","20","-c:a","aac","-b:a","96k","-movflags","+faststart",str(dest)],cwd=work,check=True)
    probe=json.loads(subprocess.check_output(["ffprobe","-v","error","-show_entries","format=duration,size:stream=codec_name,codec_type","-of","json",str(dest)]))
    assert 211.84<float(probe["format"]["duration"])<300 and int(probe["format"]["size"])<50_000_000
    assert [s["codec_name"] for s in probe["streams"]]==["h264","aac"]
    with zipfile.ZipFile(R50/"submission/candidate.zip") as base:
        info=json.loads(base.read("browser-video.json"))
        info["source_video_sha256"]=sha256(base.read("walkthrough.mp4")).hexdigest()
    info.update(seconds=float(probe["format"]["duration"]),bytes=dest.stat().st_size)
    info["scenes"].extend([["An address change","A recorded 2Wiki loss"],
        ["Which calls are needed?","The fixed mention bonus on 2Wiki"],
        ["A stronger simple alternative","Always-linked vs fixed bonus on HotpotQA"],
        ["The learned SQL ranker","Suppress a mention and verify the revised top title"]])
    dest.with_name("browser-video.json").write_text(json.dumps(info,indent=2)+"\n",encoding="utf8")
    print(json.dumps({"video":probe,"added_scene_seconds":durations}))

if __name__=="__main__":
    arg=argparse.ArgumentParser(description=__doc__)
    arg.add_argument("work",type=Path);arg.add_argument("--output",type=Path,default=ROOT/"walkthrough.mp4")
    opts=arg.parse_args();opts.work.mkdir(exist_ok=True,parents=True);capture(opts.work);media(opts.work,opts.output.resolve())

