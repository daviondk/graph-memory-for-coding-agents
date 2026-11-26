from contextlib import ExitStack
from pathlib import Path
import json,subprocess,sys
from playwright.sync_api import sync_playwright
D=Path(__file__).resolve().parent
def main():
    ref=json.loads((D/"reference.json").read_bytes())
    seen=[]
    with sync_playwright() as pw, ExitStack() as stack:
        proc=subprocess.Popen([sys.executable,"-B","-u",str(D/"server.py"),"--port","0"],stdout=subprocess.PIPE,text=True)
        stack.callback(proc.wait);stack.callback(proc.terminate);url=proc.stdout.readline().strip()
        browser=pw.chromium.launch(executable_path="C:/Program Files/Google/Chrome/Application/chrome.exe",headless=True)
        stack.callback(browser.close)
        page=browser.new_page(viewport={"width":1100,"height":840});errors=[]
        page.on("pageerror",lambda e:errors.append(str(e)))
        page.route("**/*",lambda r:r.continue_() if r.request.url.startswith(url+"/") else r.abort())
        page.goto(url)
        for case in ref:
            for policy in ("range","edges","local","file"):
                page.locator("#case").select_option(case);page.locator("#policy").select_option(policy)
                page.wait_for_function("(s)=>document.body.dataset.ready===s",arg=case+"/"+policy+"/2048")
                got=page.locator("#packet").inner_text()
                assert got.endswith(json.dumps(ref[case][policy],separators=(",",":")))
                page.locator("#audit").click()
                page.wait_for_function("document.querySelector('#result').textContent.includes('0 mismatches')")
                seen.append([case,policy,got,page.locator("#result").inner_text()])
                if case=="interior" and policy=="local":page.screenshot(path=D/"console.png",full_page=True)
        assert not errors
    (D/"browser-check.json").write_text(json.dumps(seen,ensure_ascii=False,indent=2)+"\n",encoding="utf8")
    print(len(seen),"verified UI outcomes")
if __name__=="__main__":main()
