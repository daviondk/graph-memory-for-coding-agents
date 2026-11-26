"""Start the offline console, verify every stored method and version, optionally exercise a real browser."""
import argparse
from contextlib import contextmanager
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request,urlopen

HERE=Path(__file__).resolve().parent
@contextmanager
def running():
    p=subprocess.Popen([sys.executable,"-B",str(HERE/"serve.py"),"--port","0"],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
    try:
        base=p.stdout.readline().strip();assert base.startswith("http://127.0.0.1:") and base.endswith("/")
        yield base
    finally:
        p.terminate();out,err=p.communicate(timeout=7);assert not out and not err,(out,err)
def fetch(url,method="GET"):
    with urlopen(Request(url,method=method),timeout=8) as r:return json.load(r)
def check(url):
    cs=fetch(url+"api/cases");count=0
    assert len(cs["examples"])==67 and len(cs["methods"])==5
    assert cs["default_q"]=="af8170e7fe43a980be55e40d"
    with sqlite3.connect((HERE/"audit.sqlite").as_uri()+"?mode=ro",uri=True) as db:
        for example in cs["examples"]:
            q=example["q"];gold={r[0] for r in db.execute("SELECT h FROM required WHERE q=?",(q,))}
            for m in cs["methods"]:
                expected=db.execute("SELECT h FROM reference WHERE q=? AND method=?",(q,m)).fetchone()[0]
                initial=None
                for version in (0,1):
                    opts=urlencode(dict(q=q,method=m,version=version));s=fetch(url+"api/state?"+opts)
                    assert s["selected"]["id"]==expected==s["ranking"][0]["id"]
                    assert len({x["id"] for x in s["ranking"]})==len(s["ranking"])
                    assert expected not in {x["id"] for x in s["archived_reads"]}
                    assert not {"gold","new_hit","total_gold","covered","recall","reference","required","complete"}.intersection(s)
                    ids={z["id"] for z in s["context"]}
                    if version==0:
                        assert s["receipt"] is None;initial=ids
                    else:
                        rc=s["receipt"];assert 1<=rc["first_line"]<=rc["last_line"] and len(bytes.fromhex(rc["text_sha256"]))==32
                        assert ids==initial|{expected} and len(ids)==len(initial)+1
                    res=fetch(url+"api/evaluate?"+opts,"POST")
                    assert res["total_gold"]==len(gold) and res["covered"]==len(ids&gold)
                    assert res["new_hit"]==bool(version and expected in gold)
                    count+=1
    for path,code in [("api/evaluate",404),("api/state?version=2",400),("api/state?method=x",400),("api/state?q=unknown",400)]:
        try:fetch(url+path)
        except HTTPError as e:assert e.code==code
        else:raise AssertionError("accepted invalid request")
    print(f"Verified {count} SQL session states and {count} explicit audits against frozen receipts across 67 archived traces in four repositories.")
def browser_test(base):
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        apps=[Path("C:/Program Files/Google/Chrome/Application/chrome.exe"),Path("C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe")]
        options={"executable_path":str(next(p for p in apps if p.exists()))} if any(p.exists() for p in apps) else {}
        with pw.chromium.launch(headless=True,**options) as browser:
            page=browser.new_page(viewport=dict(width=390,height=844));errors=[];audits=[]
            page.on("pageerror",lambda x:errors.append(str(x)))
            page.on("request",lambda req:audits.append(req.method) if "/api/evaluate" in req.url else None)
            page.goto(base);page.wait_for_function("current && current.method==='rrf'")
            assert not audits and page.locator("#audit").is_hidden()
            page.locator("#version").select_option("1");page.wait_for_function("current && current.version===1")
            assert "SHA-256" in page.locator("#receipt").inner_text()
            page.locator("#method").select_option("suggested");page.wait_for_function("current && current.method==='suggested'")
            assert not audits
            page.locator("#evaluate").click();page.wait_for_function("!document.querySelector('#audit').hidden")
            assert audits==["POST"];page.locator("#case").select_option(index=1)
            page.wait_for_function("current && current.q===document.querySelector('#case').value")
            assert page.locator("#audit").is_hidden()
            page.locator("summary").click();assert page.evaluate("document.documentElement.scrollWidth<=innerWidth") and not errors
    print("Verified visible controls, narrow layout, and consent-based annotation reveal.")
if __name__=="__main__":
    args=argparse.ArgumentParser();args.add_argument("--browser",action="store_true");opt=args.parse_args()
    with running() as url:
        check(url)
        if opt.browser:browser_test(url)
