"""Record real browser states from both reviewed SQLite servers and assemble a narrated tour."""
import argparse
from contextlib import ExitStack
from io import BytesIO
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
from tempfile import TemporaryDirectory
from threading import Thread
import wave

from PIL import Image, ImageDraw, ImageFont, ImageOps
from playwright.sync_api import sync_playwright
from demo import D, HTTPServer, Landing, child, verify_assets

SCENES=[
 ("Inspect the stored view","A bounded packet links each selected unit to an execution source.","The trace console assembles the evidence packet at a budget of two thousand forty eight tokens. Each entry links directly to a recorded source range."),
 ("Exclude an unrelated source","The selected units and prefix boundary survive.","Here the excluded source does not affect the selected units or the first item that blocked the prefix. A dependency check can safely reuse the entire packet."),
 ("Exclude a selected source","Unit 19 replaces unit 11 at the same budget.","Excluding a selected source triggers optimization. Unit nineteen replaces unit eleven. A separate audit compares the resulting packet with the full calculation, then checks sixty annotated characters."),
 ("Follow a recorded code edit","Two blocks move to new addresses. All 315 bytes remain in the packet.","Switch to a real coding-agent edit. The changed lines do not intersect the two selected blocks. Their identifiers survive and their addresses move. Both file versions confirm the source lines."),
 ("Compare invalidation granularity","Two of three code blocks intersect the edit. The third supplies 74 bytes.","In another case, discarding the whole file loses everything. With range invalidation two blocks are revoked and seventy four of the original five hundred seven bytes remain."),
 ("Verify the original display","Matching packet IDs can conceal incorrect source coordinates.","In the last example the same fourteen block identifiers survive. The source audit shows three selected lines already had incorrect addresses in the old display. A display guard can reject an untrustworthy suffix before writing it to memory."),
 ("Use the editor’s own evidence","Two original blocks survive after the inner unchanged lines are aligned.","Even when an edit intersects both observed blocks, part of its replacement may be identical. Compare matching the ends with aligning the interior lines. The second block returns. A separate snapshot audit verifies the selected lines.")
]

def capture(tmp):
    verify_assets()
    with sync_playwright() as pw, ExitStack() as stack:
        server=stack.enter_context(HTTPServer(("127.0.0.1",0),Landing))
        server.scenes={k:stack.enter_context(child(D/"apps"/k/v)) for k,v in (("trace","launcher.py"),("code","app.py"),("context","server.py"))}
        worker=Thread(target=server.serve_forever,daemon=True);worker.start()
        stack.callback(server.shutdown)
        home=f"http://127.0.0.1:{server.server_port}"
        exe=next(str(p) for p in [Path("C:/Program Files/Google/Chrome/Application/chrome.exe"),Path("C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe")] if p.is_file())
        b=pw.chromium.launch(executable_path=exe,headless=True,args=["--disable-gpu","--disable-background-networking"])
        stack.callback(b.close)
        page=b.new_page(viewport={"width":1240,"height":875},device_scale_factor=1)
        allowed=[home,*server.scenes.values()]
        page.route("**/*",lambda route:route.continue_() if any(route.request.url.startswith(u+"/") for u in allowed) else route.abort())
        errors=[]
        page.on("pageerror",lambda err:errors.append(str(err)))
        page.goto(home);page.get_by_role("link",name="Execution traces",exact=False).click()
        page.wait_for_function("document.documentElement.dataset.ready==='q02|2048||certificate'")
        fonts=Path(os.environ["WINDIR"])/"Fonts"
        big=ImageFont.truetype(str(fonts/"segoeuib.ttf"),32);small=ImageFont.truetype(str(fonts/"segoeui.ttf"),24)
        history=[]
        for i,(title,caption,_) in enumerate(SCENES):
            if i==1:
                page.click("#clean");page.wait_for_function("action.textContent==='Reuse cached packet'")
            elif i==2:
                page.click("#hit");page.wait_for_function("change.textContent.startsWith('Added #19')")
                page.click("#grade");page.wait_for_function("result.textContent.includes('60/60')")
            elif i==3:
                page.goto(home);page.get_by_role("link",name="Code edits",exact=False).click()
            elif i in (4,5):
                page.select_option("#case",("changed","stale")[i-4])
            if i==6:
                page.goto(home);page.get_by_role("link",name="Edit context",exact=False).click()
                page.locator("#case").select_option("interior");page.locator("#policy").select_option("edges")
                page.wait_for_function("document.body.dataset.ready==='interior/edges/2048'")
                assert page.locator("#packet").inner_text().endswith("[0]")
                page.locator("#policy").select_option("local");page.wait_for_function("document.body.dataset.ready==='interior/local/2048'")
                assert page.locator("#packet").inner_text().endswith("[0,1]")
                page.click("#audit");page.wait_for_function("document.querySelector('#result').textContent.includes('0 mismatches')")
                actual=page.locator("#packet").inner_text()+"; "+page.locator("#result").inner_text()
            elif i>=3:
                selection=("relocated","changed","stale")[i-3]
                page.wait_for_function("(v)=>document.body.dataset.ready===v",arg=selection)
                page.click("#audit");page.wait_for_selector("#versions",state="visible")
                actual=page.locator("#result").inner_text()
                if i==3:assert "match both snapshots" in actual
                if i==4:assert "74 bytes" in page.locator("#spanIds").inner_text()
                if i==5:assert "already stale" in actual and "3 of " in page.locator("#counts").inner_text()
            else:actual=page.locator("#action").inner_text()
            history.append([title,actual])
            page.evaluate("window.scrollTo(0,0)")
            screenshot=page.screenshot(full_page=True)
            if i==2:
                page.locator("section").filter(has_text="Packet after exclusion").first.screenshot(path=D/"trace.png")
            if i==5:
                page.set_viewport_size({"width":655,"height":875})
                box=page.locator("#result").evaluate("""e=>{const a=e.closest('section').getBoundingClientRect(), b=document.querySelector('#counts').getBoundingClientRect();return {x:a.left,y:a.top+scrollY,width:a.width,height:b.bottom-a.top+8}}""")
                page.screenshot(path=D/"edit.png",clip=box,full_page=True)
                page.set_viewport_size({"width":1240,"height":875})
            pic=Image.open(BytesIO(screenshot)).convert("RGB")
            pic=ImageOps.contain(pic,(1420,682),Image.Resampling.LANCZOS)
            canvas=Image.new("RGB",(1440,810),"#eef1ee");canvas.paste(pic,((1440-pic.width)//2,(686-pic.height)//2))
            draw=ImageDraw.Draw(canvas);draw.rectangle((0,686,1440,810),fill="#163b36")
            draw.text((38,697),title,font=big,fill="white");draw.text((39,751),caption,font=small,fill="#dfeddf")
            canvas.save(tmp/f"frame{i}.png")
        assert not errors
        return history

def narrate(tmp):
    lines=[dict(words=s[2],file=str(tmp/f"voice{i}.wav")) for i,s in enumerate(SCENES)]
    (tmp/"voice.json").write_text(json.dumps(lines),encoding="utf8")
    script="""param($Spec)
Add-Type -AssemblyName System.Speech
foreach ($row in (Get-Content -LiteralPath $Spec -Raw | ConvertFrom-Json)) {
    $speech = [System.Speech.Synthesis.SpeechSynthesizer]::new()
    $voice = $speech.GetInstalledVoices() | Where-Object { $_.Enabled -and $_.VoiceInfo.Culture.Name -like 'en-*' } | Select-Object -First 1
    if (-not $voice) { throw 'An English voice is required' }
    $speech.SelectVoice($voice.VoiceInfo.Name)
    $speech.SetOutputToWaveFile($row.file)
    $speech.Speak($row.words)
    $speech.Dispose()
}
"""
    (tmp/"voice.ps1").write_text(script,encoding="utf8")
    subprocess.run(["powershell.exe","-NoProfile","-File",str(tmp/"voice.ps1"),str(tmp/"voice.json")],check=True)
    lengths=[]
    with wave.open(str(tmp/"all.wav"),"wb") as out:
        for i in range(len(lines)):
            with wave.open(str(tmp/f"voice{i}.wav"),"rb") as inp:
                if i==0:
                    params=inp.getparams()
                    out.setparams(params)
                assert inp.getparams()[:3]==params[:3]
                duration=math.ceil((inp.getnframes()/inp.getframerate()+.45)*25)/25
                out.writeframes(inp.readframes(inp.getnframes()))
                pad=round(duration*inp.getframerate())-inp.getnframes()
                out.writeframes(bytes(pad*inp.getsampwidth()*inp.getnchannels()))
                lengths.append(duration)
    return lengths

def main():
    with TemporaryDirectory(dir=D) as tmpname:
        tmp=Path(tmpname)
        record=capture(tmp)
        lengths=narrate(tmp)
        spec="".join(f"file 'frame{i}.png'\nduration {t:.2f}\n" for i,t in enumerate(lengths))+f"file 'frame{len(lengths)-1}.png'\n"
        (tmp/"images.txt").write_text(spec,encoding="utf8")
        out=tmp/"video.mp4"
        subprocess.run(["ffmpeg","-loglevel","error","-f","concat","-safe","0","-i","images.txt","-i","all.wav","-r","25","-c:v","libx264","-tune","stillimage","-crf","20","-pix_fmt","yuv420p","-c:a","aac","-b:a","96k","-shortest","-movflags","+faststart",str(out)],cwd=tmp,check=True)
        info=json.loads(subprocess.check_output(["ffprobe","-v","quiet","-show_format","-show_streams","-of","json",str(out)]))
        assert {x["codec_type"] for x in info["streams"]}=={"audio","video"} and float(info["format"]["duration"])<300 and out.stat().st_size<50_000_000
        os.replace(out,D/"walkthrough.mp4")
        report=dict(seconds=float(info["format"]["duration"]),bytes=(D/"walkthrough.mp4").stat().st_size,scenes=record)
        (D/"browser-video.json").write_text(json.dumps(report,indent=2)+"\n",encoding="utf8")
        print(report["seconds"],report["bytes"])

if __name__=="__main__":main()

