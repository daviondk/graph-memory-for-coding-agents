"""Record the current graph-memory prototype and check the finished audio and video."""
from contextlib import closing
from http.server import ThreadingHTTPServer
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from threading import Thread

from playwright.sync_api import sync_playwright, expect

HERE = Path(__file__).resolve().parent
EXP = HERE.parents[1]
sys.path.insert(0,str(EXP/"graph_memory_round55/demo_video"))
import record as media
from capture import POINTER
sys.path.insert(0,str(HERE.parent/"seed_pair"))
from demo import connect, handler, html, snapshot


def capture(work):
    root = HERE.parent/"seed_pair"
    with closing(connect(root/"replay.sqlite")) as db:
        page = html(snapshot(db))
    with ThreadingHTTPServer(("127.0.0.1",0),handler(root/"replay.sqlite",page)) as server:
        thread = Thread(target=server.serve_forever,daemon=True)
        thread.start()
        try:
            with sync_playwright() as pw, closing(pw.chromium.launch()) as browser:
                ui = browser.new_page(viewport={"width":media.WIDTH,"height":media.HEIGHT},reduced_motion="reduce")
                ui.add_init_script(script="("+POINTER+")()")
                shots = {}
                def shot(name, target=None, action=None, ready=None):
                    frames=[]
                    if target is not None:
                        target.scroll_into_view_if_needed()
                        target.hover()
                        image = f"{name}-before.png"
                        ui.screenshot(path=work/image)
                        frames.append(image)
                    if action:
                        action()
                    if ready:
                        ready()
                    image=f"{name}-after.png"
                    ui.screenshot(path=work/image)
                    frames.append(image)
                    shots[name]=frames
                ui.goto((EXP/"graph_memory_round56/manuscript/replay.html").as_uri())
                expect(ui.get_by_role("button",name="Directed generator")).to_be_visible()
                shot("owners")
                evidence=ui.locator("article:visible .evidence > summary")
                shot("receipts",evidence,evidence.click)
                ui.goto(f"http://127.0.0.1:{server.server_port}/?source=sqlite")
                expect(ui.locator("#caseInfo h2")).to_have_text("dask/dask")
                box=ui.locator("#judgment")
                box.uncheck()
                shot("dask",ready=lambda:expect(ui.locator(".hit")).to_have_count(0))
                shot("gold",box,box.check,lambda:expect(ui.locator(".hit")).to_have_count(5))
                both=ui.locator("#witnesses summary").filter(has_text="both known files").first
                shot("witness",both,both.click)
                control=ui.locator("#caseSelect")
                shot("loss",control,lambda:control.select_option("loss"),lambda:expect(ui.locator("#caseInfo h2")).to_have_text("pydata/xarray"))
                tab=ui.locator("#worldButton")
                def first_world():
                    tab.click()
                    ui.locator("#a").select_option("4")
                    ui.locator("#b").select_option("13")
                    expect(ui.locator("#third")).to_contain_text("C1.")
                shot("world",tab,first_world)
                select=ui.locator("#shift")
                shot("shift",select,lambda:select.select_option("7"),lambda:expect(ui.locator("#third")).to_contain_text("C8."))
                back=ui.locator("#realButton")
                shot("return",back,back.click,lambda:expect(ui.locator("#caseInfo h2")).to_have_text("pydata/xarray"))
                return {"rendered_frames":shots,"focus_bounds":{}}
        finally:
            server.shutdown()
            thread.join()


def main():
    scenes=json.loads((HERE/"scenes.json").read_bytes())
    with TemporaryDirectory(dir=HERE) as temp:
        work=Path(temp)
        captured=capture(work)
        voice,lengths=media.voice(work,scenes)
        timeline=media.compose(work,HERE,captured,scenes,lengths)
        checks=media.verify_media(work,HERE,timeline)
    checks["voice"]=voice
    checks["scenes"]=timeline
    checks["inputs"]={str(p.relative_to(EXP)):media.digest(p) for p in
                      [EXP/"graph_memory_round56/manuscript/replay.html",HERE.parent/"seed_pair/replay.sqlite",
                       HERE.parent/"seed_pair/view.html",HERE/"scenes.json"]}
    (HERE/"verification.json").write_text(json.dumps(checks,indent=2)+"\n",encoding="utf8")
    print(checks["ffprobe"]["format"])


if __name__=="__main__":
    main()
