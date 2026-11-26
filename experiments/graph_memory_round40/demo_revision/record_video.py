"""Record a narrated local demo from live Chromium states. No remote assets or services."""
import argparse
from io import BytesIO
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory
import wave

from PIL import Image, ImageDraw, ImageFont, ImageOps
from playwright.sync_api import sync_playwright

D = Path(__file__).resolve().parent
SCENES = [
    ("The budgeted evidence view", "The reader has 2,048 tokens. Each selected unit points back to an event and source range.",
     "This is a live local evidence view over recorded synthetic operating-system agent interactions. At a budget of two thousand and forty-eight tokens, every admitted unit has a source and a cost.", "#cost"),
    ("Inspect a source", "Selecting a unit reveals the exact event range, role and neighboring graph nodes.",
     "Click a unit in the packet. Its source range and typed graph connections explain where the evidence came from. The selector reads metadata alone.", "#span"),
    ("Exclude an unrelated source", "Both the selected units and the prefix boundary survive. The cached packet is safe to return.",
     "Exclude a source outside the dependency index. Both the chosen units and the prefix boundary survive, so the server can return the original packet.", "#action"),
    ("Exclude a selected source", "The reader recalculates the packet. Unit 19 replaces unit 11.",
     "Now exclude a source from the packet. The same budget gives a different answer. Unit nineteen enters, and unit eleven leaves.", "#change"),
    ("Audit the replacement", "A fresh optimization agrees. The new packet still covers all 60 annotated characters.",
     "Run the independent audit. A fresh optimization yields the same ordered packet. The second database confirms sixty of sixty annotated characters remain covered.", "#result"),
    ("Test the prefix boundary", "Removing the first source that blocked the prefix triggers the conservative fallback.",
     "In a second trace, exclude the source that blocks the protected prefix. The fast certificate triggers a recomputation even though this particular packet stays unchanged.", "#proof"),
    ("Compare maintenance plans", "Full recomputation gives the same packet. The audit opens the annotation store only on request.",
     "Switch to full recomputation and audit again. The results agree. The dependency check controls whether to rebuild, and the separate audit measures the evidence actually delivered.", "#result")
]

def voice_tracks(tmp):
    config = []
    for i, (_, _, narration, _) in enumerate(SCENES):
        config.append(dict(file=str(tmp / f'v{i}.wav'), words=narration))
    job = tmp / 'voice.json'
    job.write_text(json.dumps(config), encoding='utf-8')
    ps = tmp / 'speak.ps1'
    ps.write_text("""param($JobPath)
Add-Type -AssemblyName System.Speech
$items=Get-Content -LiteralPath $JobPath -Raw | ConvertFrom-Json
foreach($one in $items) {
    $sp=[System.Speech.Synthesis.SpeechSynthesizer]::new()
    $voice=$sp.GetInstalledVoices() | Where-Object {$_.Enabled -and $_.VoiceInfo.Culture.Name -like 'en-*'} | Select-Object -First 1
    if (-not $voice) {throw 'An offline English narration voice is required.'}
    $sp.SelectVoice($voice.VoiceInfo.Name)
    $sp.SetOutputToWaveFile($one.file)
    $sp.Speak($one.words)
    $sp.Dispose()
}
""", encoding='utf-8')
    subprocess.run(['powershell.exe','-NoProfile','-File',str(ps),str(job)],check=True)
    times=[]
    with wave.open(str(tmp/'narration.wav'),'wb') as out:
        for i in range(len(SCENES)):
            with wave.open(str(tmp/f'v{i}.wav'),'rb') as inp:
                if not i:
                    params=inp.getparams()
                    out.setparams(params)
                assert inp.getparams()[:3]==params[:3] and inp.getsampwidth()==2
                frames=inp.getnframes()
                duration=math.ceil((frames/inp.getframerate()+.45)*25)/25
                pad=round(duration*inp.getframerate())-frames
                out.writeframes(inp.readframes(frames)+b'\0'*(pad*inp.getnchannels()*2))
                times.append(duration)
    return times

def capture(tmp):
    proc=subprocess.Popen([sys.executable,'-B','-u',str(D/'launcher.py'),'--port','0'],stdout=subprocess.PIPE,text=True)
    url=proc.stdout.readline().strip()
    assert url.startswith('http://127.0.0.1:')
    try:
        with sync_playwright() as play:
            exe=os.environ.get('BROWSER_EXE') or next(str(p) for p in (Path('C:/Program Files/Google/Chrome/Application/chrome.exe'), Path('C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe')) if p.exists())
            browser=play.chromium.launch(executable_path=exe,headless=True,args=['--disable-background-networking'])
            page=browser.new_page(viewport={'width':1220,'height':690},device_scale_factor=1)
            page.route('**/*',lambda r:r.continue_() if r.request.url.startswith(url+'/') else r.abort())
            page.goto(url);page.wait_for_function("document.documentElement.dataset.ready==='q02|2048||certificate'")
            prefix=Path(os.environ['WINDIR'])/'Fonts'
            titlefont=ImageFont.truetype(str(prefix/'segoeuib.ttf'),34);captionfont=ImageFont.truetype(str(prefix/'segoeui.ttf'),23)
            for i,(title,caption,_,focus) in enumerate(SCENES):
                if i==1:
                    page.locator('#items button').nth(1).click()
                elif i==2:
                    page.click('#clean');page.wait_for_function("action.textContent==='Reuse cached packet'")
                elif i==3:
                    page.click('#hit');page.wait_for_function("change.textContent.startsWith('Added #19')")
                elif i==4:
                    page.click('#grade');page.wait_for_function("result.textContent.includes('60/60')")
                elif i==5:
                    page.click('#boundary');page.wait_for_function("guards.textContent.includes('Boundary dependency: yes')")
                    assert page.locator('#change').inner_text().startswith('Added none') 
                elif i==6:
                    page.select_option('#mode','full');page.wait_for_function("document.documentElement.dataset.ready.endsWith('|full')")
                    page.click('#grade');page.wait_for_function("result.textContent.includes('Matches full')")
                page.evaluate("""sel=>{document.querySelectorAll('[data-focus]').forEach(e=>{e.removeAttribute('data-focus');e.style.outline='';});let e=document.querySelector(sel);e.dataset.focus='yes';e.style.outline='3px solid #d98c23';e.style.outlineOffset='3px';window.scrollTo(0,0)}""",focus)
                raw=Image.open(BytesIO(page.screenshot(full_page=True))).convert('RGB')
                pic=ImageOps.contain(raw,(1420,684),Image.Resampling.LANCZOS)
                canvas=Image.new('RGB',(1440,810),'#e9eeea');canvas.paste(pic,((1440-pic.width)//2,(686-pic.height)//2))
                draw=ImageDraw.Draw(canvas);draw.rectangle((0,688,1440,810),fill='#163b36')
                draw.text((45,695),title,font=titlefont,fill='white');draw.text((47,750),caption,font=captionfont,fill='#dbeddd')
                canvas.save(tmp/f'frame{i}.png')
            browser.close()
    finally:
        proc.terminate();proc.wait(timeout=8)

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--out',type=Path,default=D/'walkthrough.mp4');args=ap.parse_args()
    if args.out.exists():raise SystemExit('Choose a new output path for the recording.')
    with TemporaryDirectory(dir=D) as td:
        tmp=Path(td);capture(tmp);durations=voice_tracks(tmp)
        listing=''.join(f"file 'frame{i}.png'\nduration {t:.2f}\n" for i,t in enumerate(durations))+f"file 'frame{len(durations)-1}.png'\n"
        (tmp/'images.txt').write_text(listing,encoding='utf-8')
        subprocess.run([shutil.which('ffmpeg'),'-loglevel','error','-f','concat','-safe','0','-i','images.txt','-i','narration.wav','-r','25','-c:v','libx264','-tune','stillimage','-crf','20','-pix_fmt','yuv420p','-c:a','aac','-b:a','96k','-shortest','-movflags','+faststart',str(args.out.resolve())],cwd=tmp,check=True)
        assert args.out.stat().st_size<50000000 and sum(durations)<300
        print(f'{sum(durations):.2f} seconds, {args.out.stat().st_size} bytes, {len(durations)} live application states')

if __name__=='__main__':main()
