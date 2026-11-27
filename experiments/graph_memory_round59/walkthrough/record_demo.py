"""Capture the local R59 interface, narrate the verified states, and decode the completed movie."""
import argparse
from contextlib import closing
from hashlib import sha256
from importlib.util import module_from_spec,spec_from_file_location
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from playwright.sync_api import sync_playwright,expect

HERE=Path(__file__).resolve().parent
EXP=HERE.parents[1]
PAGE=HERE.parent/"demo"/"index.html"
R58=EXP/"graph_memory_round58/walkthrough/record_demo.py"
spec=spec_from_file_location("r58_capture_module",R58)
legacy=module_from_spec(spec)
spec.loader.exec_module(legacy)
media=legacy.media
POINTER=legacy.old.POINTER


def capture(work):
    shots={};actions=[];receipts={};errors=[];remote=[]
    with sync_playwright() as pw, closing(pw.chromium.launch(channel="msedge",headless=True)) as browser:
        page=browser.new_page(viewport={"width":media.WIDTH,"height":media.HEIGHT},
                              device_scale_factor=1,reduced_motion="reduce",offline=True)
        page.add_init_script("("+POINTER+")()")
        page.on("pageerror",lambda x:errors.append(str(x)))
        page.on("request",lambda r:remote.append(r.url) if r.url.startswith(("https:","http:")) else None)
        page.goto(PAGE.as_uri())
        def perform(key,control,changes,ready,expected,focus):
            target=page.locator(control)
            target.scroll_into_view_if_needed();target.hover()
            before=f"{key}-before.png";page.screenshot(path=work/before)
            for selector,value in changes:
                ctl=page.locator(selector);ctl.hover()
                if value is None:ctl.click()
                else:ctl.select_option(value)
                actions.append([selector,value])
            expect(page.locator(ready)).to_contain_text(expected)
            point=page.locator(focus).first
            point.evaluate("e => e.scrollIntoView({block:'center',behavior:'instant'})")
            point.hover()
            after=f"{key}-after.png";page.screenshot(path=work/after)
            shots[key]=[before,after]
            receipts[key]=page.locator(ready).inner_text()
        sx="Original · sparse";tx="Transfer · sparse"
        perform("ledger","#goLedger",[("#goLedger",None),("#scope",sx),("#repo","all"),("#selection","full")],
                "#ledgerCards","34,222","#ledgerCards")
        assert page.locator("#ledgerRows tr").nth(1).locator("td").nth(7).inner_text()=="65,263"
        perform("query","#goEvent",[("#goEvent",None),("#scope",sx),("#repo","original/long/sphinx-doc/sphinx"),("#query","1")],
                "#eventState","Request 2 · sphinx/domains/cpp.py","#eventState")
        perform("evidence","#step",[("#step",None)],"#eventStatus","10 selected commit bodies first loaded (695 B)","#eventList li")
        assert page.locator("#eventList li").count()==10
        perform("rank","#step",[("#step",None)],"#answer","sphinx/domains/c.py","#answer tr")
        ranks=page.locator("#answer tr").all_text_contents()
        assert len(ranks)==8 and ranks[:2]==["sphinx/domains/c.py65","tests/test_domain_cpp.py61"]
        perform("large","#goCache",[("#goCache",None),("#scope",tx),("#repo","all"),("#h","full"),("#quota","4096")],
                "#cacheCards","11,600","#cacheCards")
        perform("small","#quota",[("#quota","1024")],"#cacheCards","921","#cacheCards")
        assert page.locator("#cacheRows tr").nth(1).locator("td").nth(3).inner_text()=="17,698"
        perform("one","#goSketch",[("#goSketch",None),("#hs","B"),("#hp","all"),("#hb","1024"),("#missing","1")],
                "#equation","Read immutable event 11 directly","#equation")
        expect(page.locator("#hout")).to_contain_text("saves 1,902 B")
        perform("two","#missing",[("#missing","2")],"#equation","Fetch the exact posting list","#equation")
        perform("holdout","#hb",[("#hb","4096")],"#hout","adds 1,814 B","#holdRows tr")
        assert not errors and not remote
    return {"rendered_frames":shots,"focus_bounds":{}},dict(actions=actions,receipts=receipts,
                   errors=errors,network_requests=remote,first_ranks=ranks[:2])


def sources():
    paths=[PAGE,HERE/"scenes.json",R58,EXP/"graph_memory_round55/demo_video/record.py",
           EXP/"graph_memory_round55/demo_video/capture.py",EXP/"graph_memory_round55/demo_video/speak.ps1"]
    return {str(p.relative_to(EXP)).replace("\\","/"):sha256(p.read_bytes().replace(b"\r\n",b"\n")).hexdigest() for p in paths}


def main():
    parser=argparse.ArgumentParser();parser.add_argument("--verify",action="store_true")
    verify=parser.parse_args().verify
    scenes=json.loads((HERE/"scenes.json").read_bytes())
    verification=HERE/"verification.json"
    current_inputs=sources()
    with TemporaryDirectory(dir=HERE,prefix="screen-") as folder:
        work=Path(folder)
        frames,behavior=capture(work)
        voice,lengths=media.voice(work,scenes)
        if verify:
            expected=json.loads(verification.read_bytes())
            timeline=expected["scenes"]
            assert expected["inputs"]==current_inputs and expected["ui"]==behavior
            assert expected["voice"]==voice and [s["frames"] for s in timeline]==lengths
            for name,title,line in scenes:
                source=frames["rendered_frames"][name][-1]
                media.artwork(work,source,title,line,"final-"+name+".png")
        else:
            timeline=media.compose(work,HERE,frames,scenes,lengths)
        checks=media.verify_media(work,HERE,timeline)
        duration=float(checks["ffprobe"]["format"]["duration"])
        assert 60<=duration<=120 and len(checks["verified_scenes"])==len(scenes)
        if verify:
            assert checks["file_sha256"]==expected["file_sha256"] and checks["captions_sha256"]==expected["captions_sha256"]
        else:
            checks.update(inputs=current_inputs,scenes=timeline,ui=behavior,voice=voice)
            verification.write_text(json.dumps(checks,indent=2)+"\n",encoding="utf-8")
    print("Verified",duration,"s,",checks["ffprobe"]["format"]["size"],"bytes,",len(scenes),"live scene captures.")


if __name__=="__main__":
    main()
