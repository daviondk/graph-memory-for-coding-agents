"""Build and verify the English walkthrough from the frozen R54 demonstration."""
import argparse
from hashlib import sha256
import json
import math
from pathlib import Path
import subprocess
import wave

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from capture import WIDTH, HEIGHT, capture, digest

HERE = Path(__file__).resolve().parent
ARCHIVE = HERE.parents[1] / "graph_memory_round54/submission/candidate.zip"
FPS = 25
BAND = 116
VOICE_RATE = 22050
RGB = (11, 34, 34)


def run(*args):
    p = subprocess.run(args, capture_output=True, check=False)
    if p.returncode:
        raise RuntimeError(p.stderr.decode("utf8",errors="replace"))
    return p.stdout


def dump(path, obj):
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf8")


def timing(frames):
    ms = frames * 1000 // FPS
    return f"{ms//3600000:02d}:{(ms//60000)%60:02d}:{(ms//1000)%60:02d},{ms%1000:03d}"


def voice(work, scenes):
    items = [{"path":str(work/f"{key}.wav"), "text":line} for key, _, line in scenes]
    dump(work/"speech.json", items)
    name = run("powershell","-NoProfile","-File",str(HERE/"speak.ps1"),str(work/"speech.json")).decode().strip()
    lens = []
    lead = 4  # 160 ms before each utterance
    with wave.open(str(work/"speech.wav"),"wb") as dst:
        dst.setparams((1,2,VOICE_RATE,0,"NONE","not compressed"))
        for item in items:
            with wave.open(item["path"],"rb") as src:
                assert (src.getnchannels(),src.getsampwidth(),src.getframerate())==(1,2,VOICE_RATE)
                samples = src.getnframes()
                span = lead + math.ceil(samples / (VOICE_RATE/FPS)) + 9
                assert span > FPS
                dst.writeframes(bytes(lead*(VOICE_RATE//FPS)*2))
                dst.writeframes(src.readframes(samples))
                dst.writeframes(bytes(((span-lead)*(VOICE_RATE//FPS)-samples)*2))
                lens.append(span)
    return name, lens


def crop_to(image, region, zoom):
    if not region or zoom == 1:
        return image
    width, height = round(WIDTH/zoom), round(HEIGHT/zoom)
    x = region["x"]+region["width"]/2
    # Preserve the selected result and title just above the audit controls.
    y = region["y"] + region["height"]/2 - height * .20
    left = min(WIDTH-width,max(0,round(x-width/2)))
    top = min(HEIGHT-height,max(0,round(y-height/2)))
    return image.crop((left,top,left+width,top+height)).resize((WIDTH,HEIGHT),Image.Resampling.LANCZOS)


def artwork(work, source, chapter, text, name, region=None, zoom=1):
    face = ImageFont.truetype("C:/Windows/Fonts/segoeui.ttf",23)
    heading = ImageFont.truetype("C:/Windows/Fonts/segoeuib.ttf",19)
    with Image.open(work/source) as f:
        view = crop_to(f.convert("RGB"),region,zoom)
    canvas = Image.new("RGB",(WIDTH,HEIGHT+BAND),RGB)
    canvas.paste(view,(0,0))
    dr = ImageDraw.Draw(canvas)
    dr.rectangle((0,HEIGHT,WIDTH,HEIGHT+2),fill=(137,211,185))
    dr.text((35,HEIGHT+9),chapter,font=heading,fill=(147,220,197))
    lines = []
    for word in text.split():
        if not lines or dr.textlength(lines[-1]+" "+word,font=face) > WIDTH-70:
            lines.append(word)
        else:
            lines[-1]+=" "+word
    assert len(lines)<=2,(chapter,lines)
    for i,line in enumerate(lines):
        dr.text((35,HEIGHT+38+i*31),line,font=face,fill=(250,252,248))
    canvas.save(work/name,compress_level=3)
    return name


def compose(work, dest, captured, scenes, spans):
    playlist, timeline, cues = [], [], []
    cursor = 0
    for i, ((key, chapter, line), span) in enumerate(zip(scenes,spans)):
        files = captured["rendered_frames"][key]
        segment = []
        for j, path in enumerate(files[:-1]):
            frame = artwork(work,path,chapter,line,f"overlay-{key}-{j}.png")
            segment.append((frame,3))  # Actual mouse motion towards the next chosen control.
        region = captured["focus_bounds"].get(key)
        if region:
            for j, zoom in enumerate((1.04,1.14,1.28)):
                frame=artwork(work,files[-1],chapter,line,f"zoom-{key}-{j}.png",region,zoom)
                segment.append((frame,2))
        last=artwork(work,files[-1],chapter,line,f"final-{key}.png",region,1.45)
        remain=span-sum(n for _,n in segment)
        assert remain>FPS
        segment.append((last,remain))
        for frame,n in segment:
            playlist.extend([f"file '{frame}'",f"duration {n/FPS:.2f}"])
        cues.append(f"{i+1}\n{timing(cursor)} --> {timing(cursor+span)}\n{line}\n")
        timeline.append({"id":key,"chapter":chapter,"text":line,"start_frame":cursor,"frames":span,"steady_frames":remain,
                         "render_sha256":digest(work/last)})
        cursor+=span
    playlist.append(f"file '{last}'")
    (work/"input.txt").write_text("\n".join(playlist)+"\n",encoding="ascii")
    (dest/"captions.srt").write_text("\n".join(cues),encoding="utf8")
    # A fixed frame count ties every caption and audio cue to the same 25-fps grid.
    run("ffmpeg","-y","-loglevel","error","-f","concat","-safe","0","-i",str(work/"input.txt"),
        "-i",str(work/"speech.wav"),"-map","0:v:0","-map","1:a:0","-r",str(FPS),"-fps_mode","cfr","-frames:v",str(cursor),
        "-c:v","libx264","-preset","veryfast","-crf","19","-threads","3","-pix_fmt","yuv420p",
        "-c:a","aac","-b:a","96k","-movflags","+faststart",str(dest/"walkthrough.mp4"))
    return timeline


def verify_media(work, dest, timeline):
    media=dest/"walkthrough.mp4"
    info=json.loads(run("ffprobe","-v","error","-of","json","-show_entries",
                        "format=duration,size:stream=codec_type,codec_name,width,height,nb_frames,channels,sample_rate,pix_fmt",
                        str(media)))
    video,audio=info["streams"]
    assert (video["codec_name"],video["pix_fmt"],video["width"],video["height"])==("h264","yuv420p",WIDTH,HEIGHT+BAND)
    assert audio["codec_name"]=="aac" and int(audio["sample_rate"])==VOICE_RATE and audio["channels"]==1
    frames=sum(t["frames"] for t in timeline)
    assert frames==int(video["nb_frames"])
    assert abs(float(info["format"]["duration"])-frames/FPS)<0.06
    assert int(info["format"]["size"])<50000000 and frames/FPS<=300
    run("ffmpeg","-v","error","-xerror","-i",str(media),"-f","null","-")
    decoded=np.frombuffer(run("ffmpeg","-v","error","-i",str(media),"-map","0:a:0","-f","s16le","-"),dtype="<i2")
    with wave.open(str(work/"speech.wav"),"rb") as src:
        original=np.frombuffer(src.readframes(src.getnframes()),dtype="<i2")
    assert len(decoded)>=len(original)-VOICE_RATE//5
    measures=[]
    for t in timeline:
        i=t["start_frame"]; n=t["frames"]
        # Decode the midpoint of the steady state after its actual control action.
        at=(i+n-t["steady_frames"]/2)/FPS
        data=run("ffmpeg","-v","error","-ss",str(at),"-i",str(media),"-frames:v","1","-f","rawvideo","-pix_fmt","rgb24","-")
        actual=np.frombuffer(data,dtype=np.uint8).reshape(HEIGHT+BAND,WIDTH,3)
        target=np.asarray(Image.open(work/f"final-{t['id']}.png").convert("RGB"))
        mae=np.abs(actual.astype(np.int16)-target).mean()
        assert mae<3,(t["id"],mae)
        sl=slice(i*(VOICE_RATE//FPS),min((i+n)*(VOICE_RATE//FPS),len(decoded),len(original)))
        corr=float(np.corrcoef(original[sl],decoded[sl])[0,1])
        rms=float(np.mean(decoded[sl].astype(np.float64)**2)**.5)
        assert corr>.95 and rms>500,(t["id"],corr,rms)
        measures.append({"id":t["id"],"rgb_mean_absolute_error":round(float(mae),3),
                         "decoded_to_speech_pcm_correlation":round(corr,5),
                         "decoded_audio_rms_s16":round(rms,1)})
    return {"file_sha256":digest(media),"captions_sha256":digest(dest/"captions.srt"),"ffprobe":info,
            "decoded_full_file":True,"verified_scenes":measures}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("work",type=Path,help="Writable scratch directory outside the repository")
    p.add_argument("--archive",type=Path,default=ARCHIVE)
    p.add_argument("--output",type=Path,default=HERE)
    args=p.parse_args()
    work=args.work.resolve();work.mkdir(parents=True,exist_ok=True)
    dest=args.output.resolve();dest.mkdir(parents=True,exist_ok=True)
    scenes=json.loads((HERE/"scenes.json").read_text(encoding="utf8"))
    captured=capture(work,args.archive.resolve(),scenes)
    name,spans=voice(work,scenes)
    timeline=compose(work,dest,captured,scenes,spans)
    verified=verify_media(work,dest,timeline)
    # End-state proofs describe the application that was filmed, alongside decoded output checks.
    captured.pop("rendered_frames");captured.pop("focus_bounds")
    dump(dest/"verification.json",dict(**captured,voice=name,**verified,timeline=timeline,
         ffmpeg=run("ffmpeg","-version").decode().splitlines()[0]))
    print(f"{sum(spans)/FPS:.2f} s, {int(verified['ffprobe']['format']['size']):,} bytes, {len(scenes)} verified scenes")


if __name__=="__main__":
    main()
