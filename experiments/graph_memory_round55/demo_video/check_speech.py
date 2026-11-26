"""Optional independent English ASR pass over the delivered audio (PocketSphinx default language model)."""
import argparse
from importlib.metadata import version
import json
import os
from pathlib import Path
import re
import subprocess
import shutil

if os.name == "nt":
    mingw = shutil.which("libgcc_s_seh-1.dll")
    if mingw:
        dll_runtime = os.add_dll_directory(str(Path(mingw).parent))

from pocketsphinx import Decoder

TOKEN = re.compile(r"[a-z]+")
HERE = Path(__file__).resolve().parent


def main():
    args = argparse.ArgumentParser(description=__doc__)
    args.add_argument("--media", type=Path, default=HERE/"walkthrough.mp4")
    args.add_argument("--timeline", type=Path, default=HERE/"verification.json")
    args.add_argument("--output", type=Path, default=HERE/"speech-check.json")
    args = args.parse_args()
    refs = json.loads(args.timeline.read_text(encoding="utf8"))["timeline"]
    audio = subprocess.check_output(["ffmpeg","-v","error","-i",str(args.media),"-map","0:a:0",
                                     "-ac","1","-ar","16000","-f","s16le","-"])
    decoder = Decoder(samprate=16000)
    matched, total, rows = 0, 0, []
    for scene in refs:
        off, end = (scene["start_frame"]*1280,(scene["start_frame"]+scene["frames"])*1280)
        decoder.start_utt()
        decoder.process_raw(audio[off:end],False,True)
        decoder.end_utt()
        recog = decoder.hyp()
        text = recog.hypstr if recog else ""
        ref = set(TOKEN.findall(scene["text"].lower()))
        got = ref & set(TOKEN.findall(text.lower()))
        # Token overlap is a sanity check for audible scene content. Arbitrary proper
        # names and numbers are out of vocabulary. Report the unedited hypothesis.
        rows.append({"scene":scene["id"],"recognition":text,"distinct_reference_words":len(ref),
                     "matched_distinct_words":len(got)})
        total+=len(ref)
        matched+=len(got)
    result = {"engine":"PocketSphinx " + version("pocketsphinx"),
              "input":"Final AAC audio, decoded and resampled to 16 kHz",
              "decoder":"Bundled general US English acoustic and n-gram models. No supplied transcript or vocabulary.",
              "scenes_with_nonempty_transcript":sum(bool(r["recognition"]) for r in rows),
              "matched_distinct_words_sum":matched,"distinct_reference_words_sum":total,"scenes":rows}
    args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf8")
    print(result["scenes_with_nonempty_transcript"],matched,total)


if __name__=="__main__":
    main()
