"""Capture actual browser interactions and verify their encoded audio and video."""
from contextlib import closing
from importlib.util import module_from_spec, spec_from_file_location
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from playwright.sync_api import sync_playwright, expect

HERE=Path(__file__).resolve().parent
EXP=HERE.parents[1]
OLD=EXP/"graph_memory_round57/walkthrough/record_current.py"
spec=spec_from_file_location("previous_walkthrough",OLD)
old=module_from_spec(spec)
spec.loader.exec_module(old)
media=old.media


def capture(work):
    captured=old.capture(work)
    shots=captured["rendered_frames"]
    with sync_playwright() as pw, closing(pw.chromium.launch()) as browser:
        page=browser.new_page(viewport={"width":media.WIDTH,"height":media.HEIGHT},reduced_motion="reduce")
        page.add_init_script(script="("+old.POINTER+")()")
        page.goto((HERE.parent/"demo/index.html").as_uri())
        def action(name, selector, click, confirmation, expected):
            control=page.locator(selector)
            control.hover()
            before=f"{name}-before.png"
            page.screenshot(path=work/before)
            click(control)
            expect(page.locator(confirmation)).to_contain_text(expected)
            after=f"{name}-after.png"
            page.screenshot(path=work/after)
            shots[name]=[before,after]
        action("cold","#budget",lambda x:x.select_option("cold"),"#total","106,781")
        def recent(x):
            x.select_option("1024")
            page.locator("#selector").select_option("recent")
        action("recent","#budget",recent,"#total","106,186")
        action("demand","#selector",lambda x:x.select_option("demand"),"#total","82,907")
        action("negative","#negative",lambda x:x.click(),"#total","53,808")
        action("full","#budget",lambda x:x.select_option("full"),"#total","12,168")
        action("text","#goCache",lambda x:x.click(),"#cacheRows","273,243")
    return captured


def main():
    scenes=json.loads((HERE/"scenes.json").read_bytes())
    with TemporaryDirectory(dir=HERE) as scratch:
        work=Path(scratch)
        captures=capture(work)
        voice,lengths=media.voice(work,scenes)
        timeline=media.compose(work,HERE,captures,scenes,lengths)
        checks=media.verify_media(work,HERE,timeline)
    checks.update(voice=voice,scenes=timeline)
    files=[HERE.parent/"demo/index.html",HERE/"scenes.json",OLD,EXP/"graph_memory_round56/manuscript/replay.html",
           EXP/"graph_memory_round57/seed_pair/replay.sqlite",EXP/"graph_memory_round57/seed_pair/view.html"]
    checks["inputs"]={str(p.relative_to(EXP)):media.digest(p) for p in files}
    (HERE/"verification.json").write_text(json.dumps(checks,indent=2)+"\n",encoding="utf8")
    print(checks["ffprobe"]["format"])


if __name__=="__main__":
    main()
