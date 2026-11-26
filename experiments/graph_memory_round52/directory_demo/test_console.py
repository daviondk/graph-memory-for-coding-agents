"""Check HTTP choices against frozen outputs; optionally exercise a real narrow browser."""
import argparse
from contextlib import contextmanager
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import urlopen

ROOT=Path(__file__).resolve().parent
@contextmanager
def running():
    proc=subprocess.Popen([sys.executable,"-B",str(ROOT/"serve.py"),"--port","0"],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
    try:
        base=proc.stdout.readline().strip()
        assert base.startswith("http://127.0.0.1:") and base.endswith("/")
        yield base
    finally:
        proc.terminate();output,errors=proc.communicate(timeout=8)
        assert not errors and not output

def get(base,path,params=None):
    uri=base+path+("?"+urlencode(params) if params else "")
    with urlopen(uri,timeout=10) as handle:return json.load(handle)

def check(base):
    source=json.loads((ROOT/"audit.json").read_text(encoding="utf8"))
    with sqlite3.connect((ROOT/"directory.sqlite").as_uri()+"?mode=ro",uri=True) as db:
        db.row_factory=sqlite3.Row
        catalog={q:[dict(r) for r in db.execute("SELECT * FROM candidates WHERE q=?",(q,))] for q in source}
    cases=get(base,"api/cases");assert len(cases["examples"])==len(catalog)==8
    assert cases["directory_size"]==5989847 and cases["default_q"] in catalog
    assert get(base,"api/select")["q"]==cases["default_q"]
    checks=0;counter=0;flips=0;routes=set()
    for q,candidates in catalog.items():
        for gate,prefix in [("off",None),("0","two_words"),("59","primary"),("5989","loose")]:
            for mode,suffix in [("href","href"),("literal","text"),("none","free")]:
                cfg=dict(q=q,gate=gate,mode=mode)
                arm=(prefix+"_"+suffix if prefix else {"href":"href_first","text":"text_first","free":"free"}[suffix])
                row=get(base,"api/select",cfg);grades=get(base,"api/audit",cfg)
                wanted=source[q]["expected"][arm];assert wanted==row["selected"]["id"]==grades["expected_id"]
                assert grades["support"]==sorted(source[q]["support"]) and grades["exact_support"]==(grades["support_recall"]==1)
                assert set(row).isdisjoint({"support","support_recall","expected_id","scenario","gold","exact_support","selected_match"})
                assert row["question"] and row["prefix"] and row["witness"]["text"]
                assert row["route"]!="href" or row["witness"]["text"]==row["selected"]["anchor"]
                routes.add(row["route"]);checks+=1
                # Independent Python scoring on the complete shipped projection for each possible single-edge removal.
                def choose(omit):
                    direct=[c for c in candidates if gate!="off" and (c["direct_words"]>=2 or c["direct_words"]==1 and 0<c["df"]<=int(gate))]
                    edge=[c for c in candidates if mode!="none" and c[mode] and c["id"]!=omit]
                    pool=direct or edge or [c for c in candidates if c["base"]]
                    return min(pool,key=lambda c:(-c["score"],c["page"],c["id"]))["id"]
                assert choose(-1)==wanted
                for edge in row["edges"]:
                    target=edge["id"];new=get(base,"api/select",cfg|dict(suppress=target))
                    assert new["selected"]["id"]==choose(target) and new["eligible_counts"]["links"]==row["eligible_counts"]["links"]-1
                    counter+=1;flips+=int(new["selected"]["id"]!=wanted)
                if row["edges"]:
                    omit=row["edges"][0]["id"];aug=get(base,"api/audit",cfg|dict(suppress=omit))
                    assert aug["expected_id"] is None and aug["selected_id"]==choose(omit)
    assert routes=={"href","literal","question","directory"} and checks==96 and flips>0
    bad=[("api/select",{"gate":"123"}),("api/select",{"suppress":"-1"}),("api/select",{"mode":"gold"}),("api/select",{"q":"missing"}),("api/select",{"mode":"none","suppress":"2"})]
    for endpoint,params in bad:
        try:get(base,endpoint,params)
        except HTTPError as exc:assert exc.status==400
        else:raise AssertionError("Malformed request unexpectedly accepted")
    print(f"Verified {checks} frozen choices and {counter} single-edge counterfactuals ({flips} changed choices).")

def browser_check(base):
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        system=[Path("C:/Program Files/Google/Chrome/Application/chrome.exe"),Path("C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe")]
        path=next((str(v) for v in system if v.exists()),None)
        kw=dict(executable_path=path) if path else {}
        b=p.chromium.launch(headless=True,**kw)
        try:
            page=b.new_page(viewport={"width":390,"height":844});errors=[]
            page.on("pageerror",lambda e:errors.append(str(e)))
            page.goto(base);page.wait_for_function("state!==null && state.mode==='href'")
            assert page.locator("#selected").inner_text() and page.locator("#audit").is_hidden()
            assert page.evaluate("document.documentElement.scrollWidth<=innerWidth")
            page.locator("#reveal").click();page.wait_for_function("!document.querySelector('#audit').hidden")
            edge=page.evaluate("state.selected.id");page.locator("#suppress").select_option(str(edge))
            page.wait_for_function(f"state!==null && state.suppress==={edge}")
            assert page.locator("#audit").is_hidden()
            page.locator("#mode").select_option("none");page.wait_for_function("state!==null && state.mode==='none'")
            assert page.locator("#suppress").is_disabled()
            page.locator("#gate").select_option("off");page.wait_for_function("state!==null && state.gate==='off'")
            page.locator("summary").click();assert page.locator("tr.selected").is_visible()
            assert page.evaluate("document.documentElement.scrollWidth<=innerWidth")
            page.locator("#example").select_option(index=3);page.wait_for_function("state!==null && state.q===document.querySelector('#example').value")
            page.set_viewport_size({"width":1440,"height":810});assert not errors
        finally:b.close()
    print("Verified narrow browser, example, route, suppression, reveal and ranking controls.")
if __name__=="__main__":
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument("--browser",action="store_true");args=ap.parse_args()
    with running() as url:
        check(url)
        if args.browser:browser_check(url)
