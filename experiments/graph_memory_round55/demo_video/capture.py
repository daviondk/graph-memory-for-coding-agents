"""Capture actual interactive states from the frozen demonstration candidate."""
from contextlib import ExitStack
from hashlib import sha256
import json
from pathlib import Path
import sys
from urllib.parse import urlencode
from zipfile import ZipFile

from playwright.sync_api import sync_playwright

WIDTH, HEIGHT = 1280, 700
ARCHIVE_DIGEST = "735c0cddb063a5c407a44fd573738687b5e291e6b04325d77317deb0d9f3e087"
COMMIT = "9d2a7a280ee0a084f382762a52547b4b47d0ce56"
Q = "e6b3d0834b130dd9a2b7015d"
DOC = "3e5580c00bb011ebab90acde48001122"
POINTER = """() => {
  document.addEventListener('DOMContentLoaded', () => {
    const mark = document.createElement('span');
    mark.setAttribute('aria-hidden','true');
    mark.style.cssText='position:fixed;display:none;pointer-events:none;z-index:999999;width:22px;height:22px;border:3px solid #ffb43c;border-radius:50%;box-shadow:0 0 0 1px #27332d;background:#ffda9426;transform:translate(-50%,-50%)';
    document.body.appendChild(mark);
    addEventListener('mousemove', e => {
      mark.style.left=e.clientX+'px'; mark.style.top=e.clientY+'px'; mark.style.display='block';
    });
    window.hideRecordingPointer=()=>mark.style.display='none';
  });
}"""


def digest(path):
    return sha256(path.read_bytes()).hexdigest()


def capture(work, archive, scenes):
    if digest(archive) != ARCHIVE_DIGEST:
        raise ValueError("The walkthrough requires the pinned R54 candidate ZIP.")
    bundle = work / "r54"
    with ZipFile(archive) as z:
        z.extractall(bundle)
    sys.path.insert(0, str(bundle))
    from demo import child

    frames, receipts, regions, errors, endpoints = {}, {}, {}, [], []
    with ExitStack() as stack:
        url = stack.enter_context(child(bundle / "demo.py"))
        pw = stack.enter_context(sync_playwright())
        browser = pw.chromium.launch(headless=True)
        stack.callback(browser.close)
        page = browser.new_page(viewport={"width": WIDTH, "height": HEIGHT}, device_scale_factor=1)
        page.add_init_script("(" + POINTER + ")()")
        page.on("pageerror", lambda err: errors.append(str(err)))
        page.on("request", lambda req: endpoints.append(req.url))
        page.goto(url)
        urls = page.request.get(url + "/sessions.json").json()
        page.set_default_timeout(12000)
        active = ""
        cursor = [WIDTH * .86, HEIGHT * .12]

        def snap():
            seq = frames.setdefault(active, [])
            dest = work / f"{active}-{len(seq)}.png"
            page.screenshot(path=dest, animations="disabled")
            seq.append(dest.name)

        def find(selector):
            return page.locator(selector).first

        def aim(selector):
            loc = find(selector)
            loc.scroll_into_view_if_needed()
            box = loc.bounding_box()
            if box is None:
                raise ValueError("Missing visible control " + selector)
            dest = [box["x"] + box["width"] * .52, box["y"] + min(box["height"] / 2, 18)]
            for t in (.40, .76, 1.):
                page.mouse.move(*(cursor[j] + (dest[j] - cursor[j])*t for j in range(2)))
                snap()
            cursor[:] = dest
            return loc

        def click(selector):
            aim(selector).click()

        def select(selector, value, motion=True):
            (aim(selector) if motion else find(selector)).select_option(value)

        def readtext(selector):
            return find(selector).inner_text().strip()

        def waittext(selector, expected):
            page.wait_for_function("([s,t])=>document.querySelector(s)?.textContent.includes(t)", arg=[selector, expected])

        def base(name):
            return urls[name]

        def state(name, endpoint, params, post=False):
            addr = base(name) + endpoint + "?" + urlencode(params)
            res = page.request.post(addr) if post else page.request.get(addr)
            if res.status != 200:
                raise RuntimeError(f"Replay endpoint returned {res.status}")
            return res.json()

        def grade_doc(mode, missing=False):
            params = {"q": DOC, "gate":"59", "mode":mode}
            if missing:
                params["suppress"] = "2616836"
            sel = state("directory","/api/select",params)
            aud = state("directory","/api/audit",params)
            assert "support" not in sel and sel["selected"]["title"] == readtext("#selected")
            expected = 1 if missing or mode == "literal" else 2
            assert len(aud["support"]) == 2 and len(aud["matching_titles"]) == expected
            waittext("#audit", f"Covered {expected} of 2")
            return {"selected":sel["selected"]["title"],"witness":sel["witness"],"covered":expected,"required":2}

        def code(method, version, graded=False):
            params = dict(q=Q, method=method, version=version)
            sel = state("session","/api/state",params)
            waittext("#selected",sel["selected"]["path"])
            assert readtext("#selected") == sel["selected"]["path"] and "total_gold" not in sel
            assert len(sel["context"]) == 3 + version
            if version:
                assert sel["selected"]["id"] not in {r["id"] for r in sel["archived_reads"]}
                waittext("#receipt", sel["receipt"]["text_sha256"])
                assert len(sel["receipt"]["text_sha256"]) == 64
            value = {"file":sel["selected"]["path"],"receipt":sel["receipt"],"method":method,"context":len(sel["context"])}
            if graded:
                aud = state("session","/api/evaluate",params,post=True)
                assert aud["new_hit"] == (method=="memory_rrf")
                waittext("#audit", "file: " + ("yes." if aud["new_hit"] else "no."))
                value["new_hit"] = aud["new_hit"]
            return value

        def hist(version):
            winner = [14,2] if version == 16 else [3,1]
            data = state("churn","/api/state",{"horizon":17,"version":version})
            assert data["query"]["interval"] == data["query"]["journal"] == winner
            assert data["changes_at_horizon"] == [{"from":14,"to":19,"delta":-1,"was":1,"now":0}]
            waittext("#raw",f"#{winner[0]} · score {winner[1]}")
            assert readtext("#log") == readtext("#raw")
            return {"version":version,"committed":17,"winner":winner,"receipt":data["receipt_sha256"],"plans":data["plans"]}

        def git(s, capacity):
            revision = page.locator("#source").get_attribute("href").split("/")[-1]
            expected = {"before":"6c728a9c","after":"62bd8cf9"}[s]
            assert revision.startswith(expected)
            assert page.locator(f"#l{capacity}").get_attribute("aria-pressed") == "true"
            score = int(readtext("#eighthScore"))
            classic = int(readtext("#classicRows"))
            assert score == (30 if s=="before" else 29) and classic == int(s=="after" and capacity==8)
            assert int(readtext("#partialRows")) == 0
            return {"commit":revision,"capacity":capacity,"score":score,"classic_warm_rows":classic,"bounded_warm_rows":0,
                    "outside_bound_score":int(readtext("#boundScore")),"ranking_receipt":readtext("#valid")}

        for active, _, _ in scenes:
            receipt = {}
            if active in ("home","close"):
                page.goto(url)
                waittext("h1","Source-linked evidence views")
                receipt = {"links":len(page.get_by_role("link").all())}
            elif active == "seed":
                # Directory is lower on the landing page. Open the same link programmatically
                # to start this chapter, then show the actual select control for both modes.
                page.goto(base("directory"))
                waittext("#selected","Gabriel")
                select("#mode","literal")
                waittext("#route","Literal passage mention")
                assert readtext("#selected") == "Taschereau"
                receipt = {"selected":readtext("#selected"),"question":readtext("#question")}
            elif active in ("literal_grade","href_grade"):
                click("#reveal")
                receipt = grade_doc("literal" if active=="literal_grade" else "href")
            elif active == "href":
                select("#mode","href"); waittext("#route","Verified hyperlink")
                receipt = {"selected":readtext("#selected"),"evidence":readtext("#evidence")}
                assert "Gabriel" in receipt["selected"]
            elif active == "omit":
                select("#suppress","2616836")
                waittext("#selected","Juchereau"); click("#reveal")
                receipt = grade_doc("href",True)
            elif active == "context":
                page.goto(base("session")); waittext("#selected",".")
                select("#case",Q,False); select("#method","static_four",False)
                receipt = code("static_four",0)
            elif active == "static_read":
                select("#version","1"); receipt = code("static_four",1)
            elif active == "memory_read":
                select("#method","memory_rrf"); receipt = code("memory_rrf",1)
            elif active in ("static_grade","memory_grade"):
                click("#evaluate"); receipt = code("static_four" if active=="static_grade" else "memory_rrf",1,True)
            elif active == "past":
                page.goto(base("churn")); receipt = hist(16)
            elif active in ("change","rewind"):
                version = 17 if active=="change" else 16
                loc=aim("#version"); loc.fill(str(version)); loc.dispatch_event("input")
                receipt = hist(version)
            elif active == "plans":
                click("summary[data-i=plans]"); find("#plans").scroll_into_view_if_needed()
                receipt = hist(16)
                assert "SEARCH" in readtext("#plans")
            elif active == "git_parent":
                page.goto(url+"/tox-replay"); waittext("#valid","candidate IDs ranked")
                click("#before"); receipt = git("before",8)
            elif active == "git_change":
                click("#after"); receipt = git("after",8)
            elif active == "git_detail":
                find(".cost").scroll_into_view_if_needed()
                receipt = git("after",8)
                assert "1" in readtext(".cost")
            elif active == "git_more":
                click("#l12"); receipt = git("after",12)
            else:
                raise KeyError(active)
            page.evaluate("() => window.hideRecordingPointer?.()")
            snap()
            focus = {
                'literal_grade': '#audit', 'href_grade': '#audit', 'omit': '#audit',
                'static_grade': '#audit', 'memory_grade': '#audit', 'plans': '#plans',
                'git_detail': '.cost',
            }.get(active)
            if focus:
                regions[active] = find(focus).bounding_box()
            receipts[active] = receipt
        assert not errors, errors
        assert all(addr.startswith("http://127.0.0.1:") for addr in endpoints)
        return {"source_commit":COMMIT,"source_archive_sha256":ARCHIVE_DIGEST,
                "states":receipts,"focus_bounds":regions,"rendered_frames":frames,"browser":browser.version,
                "page_errors":errors,"external_browser_requests":0}
